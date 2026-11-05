#!/usr/bin/env bash
# D5-H2-DRILL — lebende WAL-Quelle, Online-Backup in Staging, no-clobber.
#
# Aufruf: d5_drill_v2.sh <phase>
#   vorlauf | last | last-restore | same-name | restore | abbruch | alles
#
# Jede Phase benennt ihren Exit-Code.
#   0 = Messung abgeschlossen UND Kernbedingung belegt
#   1 = Befund (Pruefung rot, aber durchgelaufen)
#   2 = INFRASTRUKTUR / Kernbedingung NICHT hergestellt — der Lauf zaehlt nicht
#
# KORREKTUR 2026-11-01 (Auftrag): Ein Lauf ist nur gueltig, wenn die Schreiblast
# NACHWEISLICH stattgefunden hat. Fruehere Fassung startete den Writer und
# wartete 6 s — ein Writer, der mit SyntaxError oder EX_TEMPFAIL abbrechen
# HAETTE, waere nie aufgefallen; der Wrapper meldete trotzdem Erfolg.
# Deshalb: bereites Signal VOR der Sicherung, Pruefung NACH der Sicherung,
# und jeder Writer-Fehler reisst den ganzen Lauf mit (RC 2).
set -u
set -o pipefail

DATA=/var/lib/newsagent
IMAGE=localhost/newsagent:latest
RUN=/tmp/d5_run
SND=/tmp/d5_sound
RST=/tmp/d5_restore
LAST=/tmp/d5_last
PHASE="${1:-last}"
START_TS=0
WRITER_PID=
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

hr() { printf '%s\n' "------------------------------------------------------------"; }
say() { printf '  %s\n' "$*"; }

pydump() {  # JSON-Zeilen als Spalten ausgeben
  python3 -c '
import json, sys
codes = []
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    if not line.startswith("{"):
        print("  " + line)
        continue
    for k, v in json.loads(line).items():
        if k == "code":
            codes.append(v)
        print(f"   {k:20s} {v}")
if codes:
    print(f"   FACHGRUND           {codes[0]}")'
}

# =============================================================== 0) VORLAUF
vorlauf() {
  hr; echo "0) H2-VORLAUF (fail-closed — jeder Verstoss bricht ab)"
  local out

  [ -d "$DATA" ] || { say "[H2-FAIL] $DATA fehlt"; return 2; }
  local n; n=$(ls -1A "$DATA" | wc -l)
  [ "$n" -gt 0 ] || { say "[H2-FAIL] $DATA leer — leere Quelle ist NIE ein leerer Bestand"; return 2; }
  say "[ok] Quelle sichtbar, $n Eintraege"

  if findmnt "$DATA" >/dev/null 2>&1; then
    say "[H2-FAIL] $DATA ist ein eigener Mountpunkt"; return 2
  fi
  say "[ok] Verzeichnis auf / (fs=$(stat -c %D "$DATA")), Inode=$(stat -c %i "$DATA")"

  local f="$DATA/drafts.db" sz
  [ -f "$f" ] || { say "[H2-FAIL] $f fehlt"; return 2; }
  sz=$(stat -c %s "$f")
  [ "$sz" -ge 1048576 ] || { say "[H2-FAIL] $f $sz B (< 1 MiB)"; return 2; }
  [ "$(head -c 15 "$f")" = "SQLite format 3" ] || { say "[H2-FAIL] Header ungueltig"; return 2; }
  say "[ok] drafts.db $sz B, Header gueltig"

  out=$(podman run --rm --network=none -v "$DATA:/data" --security-opt label=disable \
    -v "$DIR/d5_meta.py:/m.py:ro" "$IMAGE" /opt/venv/bin/python /m.py 2>&1)
  echo "$out" | grep -q '"journal_mode": "wal"' \
    || { say "[H2-FAIL] journal_mode laut DB nicht wal:"; echo "$out" | sed 's/^/      /'; return 2; }
  say "[ok] journal_mode laut DB = wal"

  command -v jq >/dev/null 2>&1 && {
    local tabs; tabs=$(echo "$out" | jq -r '.tables // [] | join(" ")')
    for t in drafts run_metrics cycles generation_state; do
      case " $tabs " in *" $t "*) ;; *) say "[H2-FAIL] Pflicht-Tabelle '$t' fehlt (siehe: $tabs)"; return 2 ;; esac
    done
    local seq; seq=$(echo "$out" | jq -r '.last_written_seq // 0')
    [ "$seq" -ge 1 ] 2>/dev/null || { say "[H2-FAIL] Wasserstand '$seq' unplausibel"; return 2; }
    say "[ok] Pflicht-Tabellen $tabs; Wasserstand last_written_seq=$seq"
  } || { say "[H2-FAIL] jq fehlt auf dem Host — Vorlauf nicht auswertbar"; return 2; }
  hr
  return 0
}

# =============================================================== 1) SCHREIBER
# Der Writer laeuft in einem BENANNTEN Container aus einer EIGENEN DATEI
# (`d5_writer.py`), nicht als Inline-Python. Er schreibt seine Phasen nach
# /snd/writer_log.jsonl (bereit / while / done) und beendet sich mit 0.
fail_infra() {
  say "[INFRASTRUKTUR] $*"
  say "KERNBEDINGUNG NICHT HERGESTELLT — dieser Lauf zaehlt NICHT als Messung."
  podman rm -f d5w >/dev/null 2>&1
  return 2
}

start_schreiber() {
  podman rm -f d5w >/dev/null 2>&1
  mkdir -p "$RUN" "$LAST"
  # `--user 0` wie bei der Sicherung: /data gehoert UID 10001 mit 0750 und
  # ist root-gesehen nicht durchquerbar, wenn der Container als 10001 laeuft
  # und das Verzeichnis als root erbt. Root im Container ist auf dieser Box
  # der Standard-Modus aller Drill-Skripte (siehe backup_newsagent.sh).
  # `--tmpfs /snd` entfaellt: die Last laeuft gegen /data (siehe d5_writer.py).
  local out
  # Bewusste Trennung: `podman run` im Hintergrund (PID in WRITER_PID), kein
  # `-d`-Container. `podman run -d` kehrt erst nach dem ersten Start des
  # Containers zurueck und blockierte hier, weil der Containerprozess zu
  # diesem Zeitpunkt noch im SQLite-Aufbau stand. Ein Hintergrundprozess
  # gibt sofort die Kontrolle zurueck, sein RC steht danach in `wait`.
  # stdout landet in einer Datei (`podman run` schreibt die Container-ID
  # dorthin, sobald er zurueckkehrt), stderr im Hintergrund-Protokoll.
  # WICHTIG: keine Kommentarzeilen zwischen den Fortsetzungs-Backslashes —
  # eine Zeile "# ..." beendet den Befehl, und die folgenden `-v` werden als
  # eigenes Kommando ausgefuehrt ("-v: command not found", gemessen).
  podman run --rm --network=none \
    -v "$DATA:/data" \
    -v "$DIR/d5_writer.py:/writer.py:ro" --security-opt label=disable \
    --user 0 "$IMAGE" /opt/venv/bin/python /writer.py \
    >"$RUN/writer.out" 2>"$RUN/writer.err" &
  WRITER_PID=$!
  return 0
}

writer_log() {
  if [ -n "${DRILL_WRITER_LOG:-}" ]; then
    cat "$DRILL_WRITER_LOG" 2>/dev/null
    return 0
  fi
  # WICHTIG: nicht `podman exec … cat`. Der `podman start`-Prozess haelt den
  # Container, und ein `--rm`-Container ist beendet. Die Datei liegt auf einer
  # Bind-Mount (/data) und ist vom Host direkt lesbar — genau der Zweck.
  cat "$DATA/d5_schreiblast.log.jsonl" 2>/dev/null
  return 0
}

live_log() {
  if [ -n "${DRILL_WRITER_LOG:-}" ]; then
    cat "${DRILL_WRITER_LOG%.jsonl}.live.jsonl" 2>/dev/null
    return 0
  fi
  cat "$DATA/d5_schreiblast.live.jsonl" 2>/dev/null
  return 0
}

writer_phase() {  # letzte Zeile mit dieser phase -> rohe JSON-Zeile
  writer_log | grep "\"phase\": \"$1\"" | tail -1
}

# Wartet, bis der Writer "bereit" meldet — max ~20 s. Ein Writer, der
# stattdessen stirbt, ist ein Infrastrukturfehler, kein "noch nicht so weit".
warten_bereit() {
  # `podman container exists` ist podman-Version-abhaengig und antwortete hier
  # auch fuer einen BEREITS ENTFERNTEN Container mit 0. Diese Abfrage war
  # damit ein Kanarienvogel, der nie singt. Ersatz: `podman inspect` — das
  # liefert 1/125, wenn es den Container nicht gibt (auf dieser Box gemessen).
  # Stale-Protokoll ausschliessen: eine 'bereit'-Zeile aus einem FRUEHEREN
  # Lauf darf diesen Lauf nicht bestaetigen. Merkmal: jeder Lauf baut die
  # Drill-DB neu auf, also beginnt ein frisches Protokoll mit seq<=5. Die
  # Zeile muss ALSO GENAU seq 5 tragen. Zeilen mit hoeherem seq stammen aus
  # einem Lauf, der diese (jetzt ersetzte) Datei nicht neu aufgebaut hat.
  # ZEITANKER (Befund 2026-11-01): der Writer-Container braucht ~1-2 s fuer
  # Start + DB-Aufbau. lag START_TS auf "vor dem Prozessstart", so fiel die
  # 'bereit'-Zeile VOR das Fenster und die Auswertung sah "kein bereit",
  # obwohl der Schreiber lief. Der Anker ist deshalb nicht mehr der
  # Prozessstart, sondern der Moment, in dem 'bereit' (seq 5) GESEHEN wurde.
  local i=0 n
  while [ "$i" -lt 400 ]; do
    n=$(writer_log | jq -r 'select(.phase=="bereit" and .seq==5) | .t' 2>/dev/null | tail -1)
    if [ -n "$n" ]; then
      START_TS=$(writer_log | jq -r 'select(.phase=="bereit" and .seq==5) | .t' 2>/dev/null | tail -1)
      say "Writer bereit (seq 5) erkannt, Zeitanker START_TS=$START_TS"
      return 0
    fi
    if ! kill -0 "$WRITER_PID" 2>/dev/null; then
      fail_infra "Writer-Prozess endete vor 'bereit' (stderr: $(tail -2 "$RUN/writer.err" | tr '\n' ' '))" >&2
      return 2
    fi
    i=$((i + 1)); sleep 0.05
  done
  fail_infra "Writer meldet nach 10 s kein 'bereit' (Log: $(writer_log | tail -2 | tr '\n' ' '))" >&2
  return 2
}

# Prueft, ob der Writer waehrend der Sicherung tatsaechlich committet hat.
pruefe_last() {
  local stamp="$1" t_start="${2:-0}" t_end="${3:-0}" bereit done_ wrc
  # Zeitbezug: START_TS ist der Laufbeginn. Das Writer-Protokoll liegt auf
  # einer Bind-Mount und ueberlebt Laeufe — ohne diesen Filter waere die
  # 'bereit'-Zeile eines Vorlaufs ein falsches Gruen (Fehlerklasse 596733,
  # nur auf der Pruefseite).
  #
  # ROLLENTRENNUNG DER BELEGE (gemessen 2026-11-01, zwei Falsch-Rot-Laeufe):
  #  - 'bereit'/'done' belegen nur den RAHMEN (vor und nach der Sicherung).
  #  - 'while' ist KEIN Beleg fuer "waehrend": der Writer schreibt es erst,
  #    wenn sein Zyklus (WRITER_DAUER) abgelaufen ist. Die Sicherung dauert
  #    ~1 s. Eine Abfrage von 'while' direkt nach dem Backup scheitert
  #    strukturell — dieser Fehler stand zuerst im Skript.
  #  - "waehrend" belegen: (a) abgeschlossene Live-Commits mit Zeitstempel im
  #    Fenster [t_start, t_end], (b) der Artefakt-Zeitstempel der Sicherung.
  #  - Auswertung ERST nach `wait` — vorher ist der Live-Strom unvollstaendig
  #    (zweiter Falsch-Rot: 0 Treffer, weil jq vor dem ersten Commit las).
  local ts="${START_TS:-0}"
  # 'bereit' dieses Laufs = letzte seq-5-Zeile; 'done' muss NACH der
  # Sicherung entstanden sein (t >= t_end) — das ist die Lauf-Signatur,
  # unabhaengig von der Prozessstart-Latenz.
  bereit=$(writer_log | jq -c -s 'map(select(.phase=="bereit" and .seq==5)) | last // empty' 2>/dev/null)
  done_=$(writer_log | jq -c --argjson e "${t_end:-0}" \
          'select(.phase=="done" and .t >= $e)' 2>/dev/null | tail -1)
  [ -n "$bereit" ] || { fail_infra "kein 'bereit' ab Laufbeginn $ts im Writer-Log" >&2; return 2; }
  [ -n "$done_" ] || { fail_infra "kein 'done' im Writer-Log — Writer lief nach der Sicherung nicht weiter" >&2; return 2; }
  local b_c d_c b_s d_s
  b_c=$(echo "$bereit" | jq -r .commits); b_s=$(echo "$bereit" | jq -r .seq)
  d_c=$(echo "$done_" | jq -r .commits);   d_s=$(echo "$done_" | jq -r .seq)
  say "Commits: bereit=$b_c (seq $b_s) · done=$d_c (seq $d_s)"
  [ "$b_c" -ge 5 ] || { fail_infra "nur $b_c Commits vor der Sicherung (<5) — keine Last" >&2; return 2; }
  [ "$d_c" -gt "$b_c" ] || { fail_infra "kein Commit nach 'bereit' ($b_c -> $d_c)" >&2; return 2; }
  [ "$b_s" -lt "$d_s" ] || { fail_infra "Wasserstand nicht gestiegen (seq $b_s -> $d_s)" >&2; return 2; }

  # Unabhaengig vom Log: WAL-Groesse (Writer-Seite) und Quelldatei-Groesse.
  local sz1 dbsz
  sz1=$(walstand)
  dbsz=$(stat -c %s "$DATA/d5_schreiblast.db" 2>/dev/null || echo 0)
  say "WAL der Quelle: $sz1 B · Quelldatei $dbsz B"

  # EXITSTATUS DES WRITERS — hier NICHT geprueft. `pruefe_last` wird ueber
  # Command-Substitution aufgerufen, laeuft also in einer Subshell; dort gibt
  # es den Hintergrundprozess nicht ("not a child of this shell", RC 127).
  # RC 127 ist Infrastruktur, kein Befund — die Pruefung in der Subshell war
  # selbst der Fehler. Der RC wird im aufrufenden `lauf` eingesammelt
  # (Variable WRC, gesetzt von warten_writer) und hier nur quittiert.
  local wrc="${WRC:-<nicht erhoben>}"
  say "Writer-Exitstatus (im Aufrufer erhoben): $wrc"

  # JETZT ist der Live-Strom vollstaendig. Jeder Treffer im Fenster ist ein
  # abgeschlossener Commit WAEHREND der Sicherung.
  local live t_bk ts_live=0 ts_bk=0
  live=$(live_log)
  t_bk=$(jq -r 'select(.code==0) | .t' "$RUN/backup.json" 2>/dev/null | tail -1)
  say "Live-Messzeilen gesamt: $(echo "$live" | grep -c .) · Artefakt-Zeit: ${t_bk:-<keine>}"
  ts_live=$(echo "$live" | jq -s --argjson a "$t_start" --argjson b "$t_end" \
    '[.[] | select(.t >= $a and .t <= $b)] | length' 2>/dev/null)
  if [ -n "$t_bk" ] && [ "$t_end" != "0" ]; then
    ts_bk=$(jq -n --argjson a "$t_start" --argjson b "$t_end" --argjson t "$t_bk" \
      'if ($t >= $a and $t <= $b) then 1 else 0 end' 2>/dev/null)
  fi
  say "Commits im Backup-Fenster [$t_start .. $t_end]: ${ts_live:-0}"
  say "Artefakt-Zeitstempel im Fenster: ${ts_bk:-0}"
  [ "${ts_live:-0}" -ge 1 ] || { fail_infra "kein sauberer Commit im Backup-Zeitfenster — Last fand nicht waehrend der Sicherung statt" >&2; return 2; }
  [ "${ts_bk:-0}" = "1" ] || { fail_infra "Artefakt-Zeitstempel ${t_bk:-<keine>} ausserhalb [$t_start .. $t_end]" >&2; return 2; }
  TS_LIVE="${ts_live:-0}"
  printf '%s\n' "IM_FENSTER=${ts_live:-0} ARTEFAKT_IM_FENSTER=${ts_bk:-0}"

  # Beleg als Datei: die Messzeilen selbst.
  mkdir -p "$LAST"
  writer_log > "$LAST/writer-${stamp}.jsonl"
  live_log > "$LAST/live-${stamp}.jsonl"
  cp "$SND"/d5sql-"$stamp".sqlite "$LAST/" 2>/dev/null || true
  cp "$SND"/d5sql-"$stamp".meta "$LAST/" 2>/dev/null || true
  cp "$SND"/d5sql-"$stamp".seqproof "$LAST/" 2>/dev/null || true
  say "Beleg abgelegt: $LAST/{writer,live}-${stamp}.jsonl (+ Artefakt, Meta, Seqproof)"
  printf '%s\n' "BACKUP_SEQ=$(jq -r .source_seq "$SND/d5sql-$stamp.meta" 2>/dev/null) FENSTER=${TS_LIVE:-0}"
  return 0
}

walstand() { stat -c %s /data/d5_schreiblast.db-wal 2>/dev/null || echo 0; }

# Beendet den Drill-Schreiber sauber. Idempotent: mehrfacher Aufruf ist
# harmlos. Ein `wait` auf einen bereits abgeraeumten PID ist kein Fehler.
stop_schreiber() {
  [ -n "${WRITER_PID:-}" ] || return 0
  podman kill -s TERM d5w >/dev/null 2>&1 || true
  wait "$WRITER_PID" 2>/dev/null || true
  WRITER_PID=
  podman rm -f d5w >/dev/null 2>&1 || true
  return 0
}

# Wartet auf 'done' und sammelt den Writer-Exitstatus EINMAL, im richtigen
# Shell-Kontext (Kindprozess von `lauf`, nicht von einer Subshell).
# Setzt WRC. Ein Writer-Fehler ist Infrastruktur -> RC 2.
warten_writer() {
  local wd=${WRITER_DAUER:-25} i=0
  while [ "$i" -lt $((wd * 40)) ]; do
    if writer_log | jq -e -c --argjson e "${1:-0}" \
         'select(.phase=="done" and .t >= $e)' >/dev/null 2>&1; then break; fi
    i=$((i + 1)); sleep 0.05
  done
  WRC=0
  if [ -n "$WRITER_PID" ]; then
    wait "$WRITER_PID"; WRC=$?
    WRITER_PID=
  fi
  say "Writer-Exitstatus: $WRC (0 = sauber beendet)"
  case "$WRC" in
    0) return 0 ;;
    125|127) fail_infra "Writer-Exitstatus $WRC = Container/Werkzeug-Fehler (125/127), kein Fachbefund" >&2; return 2 ;;
    *) fail_infra "Writer endete mit $WRC — Schreiblast nicht belegt, Lauf ungueltig" >&2; return 2 ;;
  esac
}

lauf() {
  local etikett="$1"
  hr; echo "1) LAUF '$etikett' — Schreiber laeuft VOR, WAEHREND und NACH der Sicherung"
  start_schreiber || return 2
  warten_bereit || { podman rm -f d5w >/dev/null 2>&1; return 2; }
  sleep 3   # mehr Commit-Zyklen vor der Sicherung
  local w1 t_start t_end
  t_start=$(date +%s.%N)
  START_TS="$t_start"
  w1=$(walstand)
  say "WAL der Drill-Quelle vor dem Backup: $w1 Bytes"

  STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$etikett"
  mkdir -p "$RUN"
  local rc
  podman run --rm --network=none \
      -v "$DATA:/data" -v "$SND:/sound" \
      -v "$DIR/d5_last_backup.py:/backup.py:ro" \
      --security-opt label=disable --user 0 -e STAMP="$STAMP" \
      "$IMAGE" /opt/venv/bin/python /backup.py \
      >"$RUN/backup.json" 2>"$RUN/backup.err"
  rc=$?
  t_end=$(date +%s.%N)
  echo "  Backup-RC=$rc  (0=veroeffentlicht, 10..43=benannter Fehlgrund, 125/127=Infrastruktur)"
  cat "$RUN/backup.json" | pydump
  [ -s "$RUN/backup.err" ] && say "stderr: $(tail -2 "$RUN/backup.err" | tr '\n' ' ')"

  # Backup-Status zuerst trennen: Infrastruktur vs. Fachbefund.
  case "$rc" in
    0) : ;;
    10|11|12|21|22|23|24|31|41|42|43) : ;;
    125|127) podman rm -f d5w >/dev/null 2>&1; fail_infra "Backup-Container RC=$rc" >&2; return 2 ;;
    *) podman rm -f d5w >/dev/null 2>&1; fail_infra "Backup unerwartet RC=$rc" >&2; return 2 ;;
  esac

  # NACH der Sicherung etwas laufen lassen: der Writer committet
  # WRITER_DAUER=20 s lang. Das Fenster ist kurz — 12 s Nachlauf garantieren,
  # dass 'while' und 'done' geschrieben wurden, BEVOR gewertet wird.
  # Ohne diese Wartezeit wurde 'kein while' gemessen, obwohl der Writer
  # normal weiterlief — ein Pruefungsfehler, der wie ein Befund aussah.
  # ERST den Writer beenden und seinen RC einsammeln (Kind dieser Shell),
  # DANN pruefen. Reihenfolge ist bindend: RC 127 in einer Subshell, ein
  # noch wachsender Live-Strom und eine 'bereit'-Zeile ausserhalb des
  # Fensters haben am 2026-11-01 drei Falsch-Rot-Laeufe erzeugt.
  warten_writer "$t_end" || return 2
  local pret
  pret=$(pruefe_last "$STAMP" "$t_start" "$t_end"; echo "SUBSHELL_RC=$?")
  echo "$pret" | sed 's/^/  /'
  case "$pret" in
    *SUBSHELL_RC=0*) : ;;
    *) return 2 ;;
  esac

  [ "$rc" = "0" ] || { say "Backup endete mit Fachgrund $rc — Lauf bleibt rot, aber die Last ist belegt."; return 1; }
  say "KERNBEDINGUNG BELEGT: Schreiber committete vor, waehrend und nach der Sicherung."
  return 0
}

# =============================================================== 3) SAME-NAME
same_name() {
  hr; echo "3) SAME-NAME: derselbe STAMP ein zweites Mal"
  local f; f=$(ls -1t "$SND"/drafts-*.sqlite 2>/dev/null | head -1)
  [ -n "$f" ] || { say "[BELEG-FEHLT] kein Artefakt — erst lauf1"; return 1; }
  local v n st
  v=$(sha256sum "$f" | cut -c1-16)
  st=$(basename "$f" .sqlite); st="${st#drafts-}"
  local res rc
  res=$(podman run --rm --network=none \
      -v "$DATA:/data" -v "$SND:/sound" \
      -v "$DIR/d5_backup_part.py:/backup.py:ro" \
      --security-opt label=disable --user 0 -e STAMP="$st" \
      "$IMAGE" /opt/venv/bin/python /backup.py 2>&1)
  rc=$?
  n=$(sha256sum "$f" | cut -c1-16)
  echo "  RC=$rc (41 = Ziel existiert bereits)"
  echo "$res" | pydump
  say "Artefakt vorher $v / nachher $n → $([ "$v" = "$n" ] && echo UNVERAENDERT || echo UEBERSCHRIEBEN)"
  say "Artefakte im Staging: $(ls -1 "$SND"/drafts-*.sqlite 2>/dev/null | wc -l) (darf nicht gewachsen sein)"
  hr
}

# =============================================================== 4) RESTORE
restore() {
  hr; echo "4) RESTORE an fremdem Ort (read-only, immutable)"
  local f; f=$(ls -1t "$SND"/d5sql-*.sqlite 2>/dev/null | head -1)
  [ -n "$f" ] || { say "[BELEG-FEHLT] kein Artefakt"; return 1; }
  # Die ERWARTUNG "identisch" ist fuer einen Online-Backup falsch: die Quelle
  # laeuft weiter, waehrend die Sicherung steht. Geprueft wird der
  # WIEDERHERSTELLUNGSWERT (integrity + Wasserstand <= Quelle), nicht
  # Byte-Gleichheit — sonst misst Phase 4 ihren eigenen Aufbau.
  rm -rf "$RST"; mkdir -p "$RST"
  # ORTSRECHTE (gemessen 2026-11-01 im ersten Drill): /tmp ist 1777 root:root.
  # `cp` legt die Datei als root:root 0644 an — der Restore-Container laeuft
  # als 10001 und darf das VERZEICHNIS nicht betreten ("unable to open
  # database file"). Ein Restore-Beweis als root sieht diesen Fehler nie.
  # Deshalb: ausdrueckliche Ortsrechte, dann der Beweis als fremder User.
  cp "$f" "$RST/restored.db"
  chmod 0755 "$RST"; chmod 0644 "$RST/restored.db"
  say "wiederhergestellt nach $RST/restored.db (aus $(basename "$f"))"
  say "Ortsrechte: $(stat -c '%A %U:%G %n' "$RST" "$RST/restored.db" | tr '\n' ' ')"
  podman run --rm --network=none -v "$RST:/rest:ro" -v "$DATA:/data:ro" \
    -v "$DIR/d5_restore_part.py:/r.py:ro" \
    --security-opt label=disable --user 0 "$IMAGE" /opt/venv/bin/python /r.py 2>&1 | sed 's/^/  /'
  hr
}

# =============================================================== 5) ABBRUCH
abbruch() {
  hr; echo "5) ABBRUCH im Fenster ZWISCHEN Artefakt und Quittung"
  start_schreiber; sleep 3
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)-abbruch"
  local art="$SND/drafts-$STAMP.sqlite" meta="$SND/drafts-$STAMP.meta"
  # Haltepunkt IM ERZEUGER statt Zeitrennen auf der Hostseite (gemessen
  # 2026-11-01: ein Kill nach fester Schlafzeit traf entweder vorher oder
  # nachher; beide Male hiess das Ergebnis "1 Artefakt" bei verschiedener
  # Ursache). Der Erzeuger haelt 45 s nach erfolgreichem os.link() an; der
  # Kill trifft damit genau das Fenster, das gemessen werden soll.
  podman run --rm --name d5k --network=none \
    -v "$DATA:/data" -v "$SND:/sound" \
    -v "$DIR/d5_backup_part.py:/backup.py:ro" \
    --security-opt label=disable --user 0 \
    -e STAMP="$STAMP" -e HALT_MODE=after_link -e HALT_SEC=45 \
    "$IMAGE" /opt/venv/bin/python /backup.py >/dev/null 2>&1 &
  local n=0
  while [ "$n" -lt 500 ]; do
    [ -e "$art" ] && break
    n=$((n + 1)); sleep 0.02
  done
  say "Artefakt nach $n Polls sichtbar: $([ -e "$art" ] && echo ja || echo nein)"
  say "Fenster: artefakt=$([ -e "$art" ] && echo ja || echo nein) meta=$([ -e "$meta" ] && echo ja || echo nein) metatmp=$([ -e "$SND/drafts-$STAMP.meta.part" ] && echo ja || echo nein)"
  podman kill -s KILL d5k 2>&1 | sed 's/^/  kill: /'
  podman rm -f d5k >/dev/null 2>&1 || true
  sleep 1
  if [ -e "$art" ]; then
    say "Was im Fenster liegt: das Artefakt SELBST wird geprueft"
    podman run --rm --network=none -v "$SND:/sound:ro" \
      --security-opt label=disable --user 0 -e ART="drafts-$STAMP.sqlite" \
      "$IMAGE" /opt/venv/bin/python -c "
import os, sqlite3
c = sqlite3.connect('file:/sound/' + os.environ['ART'] + '?mode=ro&immutable=1', uri=True)
print('  integrity:', c.execute('pragma integrity_check').fetchone()[0])
print('  drafts:', c.execute('select count(*) from drafts').fetchone()[0])
c.close()" 2>&1 | sed 's/^/  /'
  fi
  say "Meta vorhanden: $([ -e "$meta" ] && echo ja || echo NEIN)"
  say ".part-Reste: $(ls -1 "$SND" | grep -c '\.part$' || true)"
  stop_schreiber
  hr
}

# =============================================================== 6) NEGATIV
# GEGENPROBE: Die Pruefung muss einen FEHLENDEN Schreibstrom erkennen. Ohne
# diesen Fall waere "Kernbedingung belegt" eine Zusicherung, die nie rot wird.
negativ() {
  hr; echo "6) GEGENPROBE — Writer, der NICHT schreibt, MUSS als Infrastruktur gelten"
  podman rm -f d5w >/dev/null 2>&1
  local log="$LAST/writer-gegenprobe.jsonl.log"
  : > "$log"
  if DRILL_WRITER_LOG="$log" pruefe_last "gegenprobe" >/dev/null 2>&1; then
    say "GEGENPROBE ROT: ein leerer Writer-Log wurde als Schreiblast akzeptiert."
    hr; return 1
  fi
  # Zweite Gegenprobe: Log mit 'bereit', aber ohne jeden Commit danach —
  # genau der Fall 596733 (Writer gestartet, nie geschrieben).
  local stumm="$LAST/writer-gegenprobe2.jsonl"
  printf '%s\n' '{"phase": "bereit", "commits": 5, "seq": 5, "rows": 305}' > "$stumm"
  if DRILL_WRITER_LOG="$stumm" pruefe_last "gegenprobe2" 0 0 >/dev/null 2>&1; then
    say "GEGENPROBE 2 ROT: 'bereit ohne Schreibstrom' wurde akzeptiert."
    hr; return 1
  fi
  say "GEGENPROBE 2 GRUEN: 'bereit ohne Schreibstrom' -> Infrastrukturfehler."
  say "GEGENPROBE GRUEN: leerer Log -> Infrastrukturfehler (RC 2), wie verlangt."
  hr
  return 0
}

# =============================================================== 7) LAST-RESTORE
# Restore des UNTER LAST erzeugten Artefakts an fremdem Ort und Vergleich mit
# dem Writer-Strom. Ein Artefakt, das VOR dem Schreibfenster liegt, waere ein
# stiller Beweis gegen die Kernbedingung — dieser Zweig macht ihn laut.
last_restore() {
  hr; echo "7) RESTORE des Last-Artefakts an fremdem Ort + Wasserstandsvergleich"
  local art
  art=$(ls -1t "$SND"/d5sql-*-last.sqlite 2>/dev/null | head -1)
  [ -n "$art" ] || { say "[BELEG-FEHLT] kein Last-Artefakt"; return 1; }
  local st; st=$(basename "$art" .sqlite); st="${st#d5sql-}"
  [ -f "$LAST/writer-$st.jsonl" ] || { say "[BELEG-FEHLT] Writer-Log fehlt"; return 1; }
  rm -rf "$RST"; mkdir -p "$RST"
  cp "$art" "$RST/restored.db"
  chmod 0755 "$RST"; chmod 0644 "$RST/restored.db"
  say "Ort: $RST (0755), Datei 0644, Leser: fremder User"
  say "Quelle: $(basename "$art") aus $SND"
  podman run --rm --network=none -v "$RST:/rest:ro" -v "$LAST:/log:ro" \
    -v "$DIR/d5_last_restore.py:/r.py:ro" \
    --security-opt label=disable --user 0 "$IMAGE" /opt/venv/bin/python \
    /r.py /rest/restored.db "/log/writer-$st.jsonl" "/log/d5sql-$st.meta" 2>&1 | sed 's/^/  /'
  local rrc=${PIPESTATUS[0]}
  local bau="$LAST/rst-bau.log"
  : > "$bau"
  podman run --rm --network=none -v "$RST:/rest:ro" -v "$LAST:/log:ro" \
    -v "$DIR/d5_last_restore.py:/r.py:ro" \
    --security-opt label=disable --user 0 "$IMAGE" /opt/venv/bin/python \
    /r.py /rest/restored.db "/log/writer-$st.jsonl" "/log/d5sql-$st.meta" > "$bau" 2>&1
  local rrc=$?
  sed 's/^/  /' "$bau"
  say "Restore-Prüfung RC=$rrc (0=alle Aussagen erfüllt, 1=Befund, 2=Beleg unbrauchbar)"
  hr
  return $rrc
}

case "$PHASE" in
  vorlauf)      vorlauf; exit $? ;;
  last)         mkdir -p "$SND" "$LAST"; lauf last ;;
  last-restore) last_restore ;;
  same-name)    same_name ;;
  restore)      restore ;;
  abbruch)      abbruch ;;
  negativ)      negativ ;;
  alles)        vorlauf || exit 2; mkdir -p "$SND" "$LAST"; lauf last || exit 2; negativ || exit 1; last_restore; same_name; restore; abbruch ;;
  *)            echo "unbekannte Phase: $PHASE"; exit 64 ;;
esac
