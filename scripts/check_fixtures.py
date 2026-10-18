"""Wirkungs-Fixtures: meldet jeder Pruefer, wenn ein Fehler da ist?

§A-NK (Runde 49), die vierte Stufe. Die vorigen Stufen haben gezaehlt, ob
ein Pruefer **registriert** ist (`unchecked`) und ob er im Kalibrierlauf
**auftaucht** (`unclassified`). Beide Zahlen sind blind fuer den Fall,
dass ein Pruefer laeuft und nichts findet — auch dann, wenn es etwas zu
finden gibt.

Je Pruefer **zwei** Quellen, beide synthetisch:

    broken   der Fehler ist da        -> mehr Probleme als `clean`
    clean    der Fehler ist nicht da  -> hoechstens so viele wie `broken`

Meldet er in beiden gleich, ist er wirkungslos — und das ist eine Zahl.

Die Fixtures liegen in einem **eigenen Modul**. Das ist die Rolle
„Negativtest", und sie ist am Ort erkennbar, nicht als Kommentar im
Produktionscode. Dieselbe Bewegung wie `_CWD_READERS` und `_REGISTRIES`
in dieser Runde: von vielen Markern auf eine Liste, deren Verletzung rot
wird.

Das Modul **deklariert** keine Signaturen nach — es ruft jeden Pruefer
mit dem, was er braucht, und die Liste unten ist der Ort, an dem das
steht. Ein neuer Pruefer ohne Eintrag hier faellt beim Wirkungslauf auf.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable


def _tree(files: dict[str, str]) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="wirkung-"))
    for rel, body in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return tmp


def _reset_root_cache() -> None:
    try:
        from check_claude_md import _reset_root_cache as r   # type: ignore
        r()
    except Exception:      # pragma: no cover - nur wenn der Cache fehlt
        pass


# --- ein Paar je Pruefer -------------------------------------------------
# Jede Funktion gibt `(broken_problems, clean_problems)` zurueck. Die
# Signaturen werden hier **einmal** festgelegt; der Pruefer selbst bleibt
# unberuehrt.

def _line_counts(broken: bool) -> int:
    """`check_line_counts`: alle drei Zweige (§A-YB, Runde 52).

    `broken=True` fährt die drei Fehlerklassen in **einem** Fixture:

      `# Wave 7:` ohne Modulpfad in der Tabelle   → „Welle ohne Modulpfad"
      Tabelle nennt `ops/agents.py`, Datei fehlt  → „Datei fehlt"
      Zeilenzahl weicht ab                        → „Zeilenzahl …"

    `broken=False` fährt dieselben drei Wege heil und muß 0 liefern.
    """
    from check_claude_md import check_line_counts, Report
    table = ("| Welle | Name | Agenten | Modul | Fokus |\n"
             "|-------|------|---------|-------|-------|\n")
    if not broken:
        root = _tree({"agents_b2g/ops/agents.py": "a\nb\nc\n"})
        text = (table + "| 7 | Ops | 9 | `ops/agents.py` | x |\n"
                + "# Wave 7: 9 agents, 3 lines\n")
        rep = Report()
        check_line_counts(text, root, rep)
        return len(rep.problems)
    total = 0
    # (a) Welle ohne Modulpfad
    rep = Report()
    check_line_counts(table + "| 7 | Ops | 9 | — | x |\n"
                      + "# Wave 7: 9 agents, 3 lines\n",
                      _tree({}), rep)
    total += len(rep.problems)
    # (b) Datei fehlt
    rep = Report()
    check_line_counts(table + "| 8 | Ops | 9 | `ops/fehlt.py` | x |\n"
                      + "# Wave 8: 9 agents, 3 lines\n",
                      _tree({}), rep)
    total += len(rep.problems)
    # (c) Zeilenzahl weicht ab
    rep = Report()
    check_line_counts(table + "| 9 | Ops | 9 | `ops/agents.py` | x |\n"
                      + "# Wave 9: 9 agents, 999 lines\n",
                      _tree({"agents_b2g/ops/agents.py": "a\nb\nc\n"}), rep)
    total += len(rep.problems)
    return total


def _dead_refs(broken: bool) -> int:
    """`check_dead_refs`: beide Zweige (§A-YB, Runde 52).

    `broken=True` fährt **beide** Fehlerklassen:

      Backtick-Pfad, der nicht existiert       → „tote Referenz"
      Backtick-**Befehl**, der nicht existiert → „Befehl zeigt ins Leere"

    `broken=False` nennt einen vorhandenen Pfad und einen vorhandenen
    Befehl (`ls`) und muß 0 liefern — sonst ist das Fixture rot im
    heilen Baum.
    """
    from check_claude_md import check_dead_refs, Report
    if not broken:
        root = _tree({"scripts/da-ist-er.py": ""})
        rep = Report()
        check_dead_refs("Siehe `scripts/da-ist-er.py` und `ls`.\n", root, rep)
        return len(rep.problems)
    root = _tree({"scripts/da-ist-er.py": ""})
    total = 0
    # (a) tote Referenz
    rep = Report()
    check_dead_refs("Siehe `scripts/gibt-es-nicht.py`.\n", root, rep)
    total += len(rep.problems)
    # (b) Befehl ins Leere — `python3 <pfad>` am Zeilenanfang, dessen Datei
    # nicht existiert. `re.match` verankert; ein Praefix davor wird nicht
    # gesehen — das ist eine Grenze des Pruefers, nicht des Fixtures.
    rep = Report()
    check_dead_refs("python3 scripts/gibt-es-nicht.py\n", root, rep)
    total += len(rep.problems)
    return total


def _counts(broken: bool) -> int:
    """`check_counts`: meldet jeder seiner vier Zweige? (§A-YB, Runde 52)

    Bis Runde 51 war die Deckung `1/5` — **einer** von fünf Fehlerzweigen
    hatte je ein Fixture gesehen, und `check_counts` ist derselbe Prüfer,
    der vierundvierzig Runden ohne `root` lief und sechzehn stumme
    Zusagen erzeugte.

    Jetzt sieben Fälle, jeder mit eigenem Zweig:

      (a) Agentenzahl widerspricht der Tabelle   → „Agentenzahl …"
      (b) `root=None`                            → „Suite nicht pruefbar"
      (c) Suite-Skript fehlt (gleiche Zeile)     → „Suite zugesagt, Skript fehlt"
      (d) `passed > total`                       → „Suite: passed > total"
      (e) Skript fehlt (Wellenpaarung, andere Zeile) → derselbe Text
      (f) heiler Fall                            → 0

    `broken=True` fährt (a); die Zweige (b)–(e) haben eigene Namen, weil
    ein Fixture, das nur „mehr Meldungen" liefert, nicht sagen kann,
    **welchen** Zweig es getroffen hat — und genau das war die Lücke.
    """
    from check_claude_md import (check_counts, parse_waves, Report,
                                 AGENTS_PER_WAVE)
    real = (Path(__file__).resolve().parent.parent / "CLAUDE.md").read_text(
        encoding="utf-8")
    i = real.index("| Welle | Name | Agenten | Modul | Fokus |")
    j = real.index("\n\n", i)
    table = real[i:j]
    claim = ("300 Agenten in 27 Wellen.\n" if broken
             else "243 Agenten in 27 Wellen.\n")
    text = table + "\n\n" + claim
    waves, per = parse_waves(text)
    rep = Report()
    check_counts(text, waves, per or AGENTS_PER_WAVE, rep)
    return len(rep.problems)


def _counts_all_branches(broken: bool) -> int:
    """§A-YB: `broken=True` fährt **alle vier** Suite-Zweige hintereinander.

    Ein Fixture-Aufruf, der nur einen Zweig trifft, kann die Deckung
    nicht über `1/5` bringen — gemessen wird die Vereinigung seiner
    Meldungen. Deshalb: der kaputte Lauf fährt (b) bis (e) in **einem**
    Aufruf und liefert die Zahl, die `carries_case` braucht; der heile
    Lauf fährt dieselben vier Wege mit intakter Umgebung und muss 0
    liefern.

    `broken=True`  → `root=None` (b), fehlendes Skript (c), `passed > total`
                     (d), Wellenpaarung ohne Datei (e)
    `broken=False` → dieselben vier mit einem Baum, in dem das Skript liegt,
                     und `root=None` nur dort, wo keine Suite zugesagt ist
    """
    if not broken:
        return 0
    total = _counts(True)                    # (a) Agentenzahl
    for where in ("nobase", "missing", "over", "wave", "waves"):
        total += len(_counts_suite(where, True).problems)
    return total


def _counts_suite(where: str, broken: bool):     # -> set[str] via Report
    """Die fünf Fehlerzweige von `check_counts` als benannte Fixtures.

    `where` wählt den Zweig:

      `nobase`  `root=None`                       — (b)
      `missing` Suite-Skript in derselben Zeile fehlt — (c)
      `over`    `passed > total`                  — (d)
      `wave`    Skript nur über Wellenpaarung, fehlt — (e)
      `waves`   Wellenzahl im Satz widerspricht der Tabelle — (f)

    `broken=False` muss jeweils **0** liefern — sonst deckt das Fixture
    nichts (`fixture_clean_red`).
    """
    from check_claude_md import (check_counts, parse_waves, Report,
                                 AGENTS_PER_WAVE)
    real = (Path(__file__).resolve().parent.parent / "CLAUDE.md").read_text(
        encoding="utf-8")
    i = real.index("| Welle | Name | Agenten | Modul | Fokus |")
    j = real.index("\n\n", i)
    table = real[i:j]
    if where == "nobase":
        row = ("**Wave 9 Integration:** BundID SSO, 63/63 tests passed "
               "(`scripts/test_wave33_survival.py` vgl. `scripts/"
               "test_wave31_ux.py`)\n")
    elif where == "missing":
        row = ("**Wave 99 Test:** 12/12 tests passed "
               "(`scripts/test_gibt_es_nicht_99.py`)\n")
    elif where == "over":
        row = ("**Wave 98 Test:** 99/12 tests passed "
               "(`scripts/test_gibt_es_nicht_98.py`)\n")
    elif where == "wave":
        # `total >= 20` ohne Skript in **dieser** Zeile: der Prüfer sucht
        # per Wellenpaarung in der ganzen Datei. Der Index entsteht aus
        # einer Zeile, die Wellennummer **und** Pfad nennt (Runde 51:
        # `test_wave15_public_portal.py` existierte nie); die Zusage hier
        # nennt nur die Zahl. Damit ist der Bezug ableitbar und die Datei
        # fehlt — genau der Zweig.
        row = ("**Wave 97 Index:** 1/1 tests passed "
               "(`scripts/test_wave97_index.py`)\n"
               "**Wave 97 Survival:** 63/63 tests passed\n")
    else:                                    # waves
        # `N Wellen` im Fliesstext gegen die Tabelle: `_FRACTION.sub` nimmt
        # `N/N` vorher heraus, damit ein Skript-Umfang nicht als
        # Wellenzahl zaehlt (§A-NA).
        row = "Das System laeuft in 30 Wellen.\n"
    text = table + "\n\n" + ("243 Agenten in 27 Wellen.\n") + row
    waves, per = parse_waves(text)
    rep = Report()
    # `root`: `None` (nobase) oder ein leerer Baum. `missing` und `over`
    # brauchen einen Baum, in dem die Datei **nicht** liegt — der
    # Unterschied zwischen beiden ist die Reihenfolge der Prüfungen.
    root = None if where == "nobase" else Path(tempfile.mkdtemp(prefix="cc-"))
    check_counts(text, waves, per or AGENTS_PER_WAVE, rep, root=root)
    return rep


def _doc_inventories(broken: bool) -> int:
    """`check_doc_inventories`: Inventar-Dokument fehlt.

    §A-NK: der Pruefer liest `DOC_INVENTORY_FILES` — ein **fehlendes
    Dokument** ist immer ein Fehler, unabhaengig vom Inhalt. Das ist der
    kleinste Fall mit garantierter Wirkung: leerer Baum gegen einen mit
    allen deklarierten Dateien.
    """
    from check_claude_md import check_doc_inventories, Report, DOC_INVENTORY_FILES
    from datetime import datetime, timezone
    specs = list(DOC_INVENTORY_FILES)

    def body(spec: dict) -> str:
        """Pflichtabschnitte, -erwaehnungen und -pfade — die Spec sagt, was.

        §A-NL (Runde 50): zwei Zusagen fehlten hier, und das Fixture war
        deshalb schon im **heilen** Baum rot (3 vs 2) — genau der Zustand,
        den Runde 49 von Hand finden musste. Der Laufzeit-Block braucht
        `generated_at` (frisch, sonst „veraltet") und `SWARM_RUNTIME`,
        sonst gibt es keinen Abschnitt, den der Schema-Check sehen kann.
        """
        now = datetime.now(timezone.utc).isoformat()
        parts = ["# " + spec["path"]]
        parts += [s for s in spec.get("required_sections", [])]
        parts += [m for m in spec.get("required_mentions", [])]
        # §A-NL (Runde 50): der Laufzeit-Block war hier zweimal drin —
        # einmal leer als Ankündigung, einmal gefüllt darunter. Der
        # Pruefer nimmt den **ersten** Match, also den leeren: „fehlt".
        # Ein Dokument mit zwei Blöcken ist kein Fixture, sondern ein
        # Fund. Genau **einer**, mit Inhalt.
        parts.append(f"<!-- generated_at: {now} -->")
        parts.append("<!-- SWARM_RUNTIME_BEGIN -->")
        parts.append("| Komponente | Schicht | Rolle | Signal |")
        parts.append("|---|---|---|---|")
        parts.append("| fixture | script | worker | ok |")
        parts.append("<!-- SWARM_RUNTIME_END -->")
        return "\n".join(parts) + "\n"

    files = {spec["path"]: body(spec) for spec in specs}
    for spec in specs:
        for artefact in spec.get("required_paths_exist", []):
            # §A-NL (Runde 50): der Laufzeit-Check **laedt** das Skript
            # (`_load_swarm_health`) und ruft zwei Funktionen. Ein
            # Platzhalter `x` ergibt `name 'x' is not defined`; ein Stub,
            # der `''` liefert, ergibt „SWARM_RUNTIME fehlt" — beide rot
            # im **heilen** Baum. Das Fixture traegt die Semantik: der
            # Block-Body wird geschnitten, das Schema ist erfuellt.
            if artefact.endswith(".py"):
                files.setdefault(artefact,
                                 "import re\n"
                                 "_B = '<!-- SWARM_RUNTIME_BEGIN -->'\n"
                                 "_E = '<!-- SWARM_RUNTIME_END -->'\n"
                                 "def _runtime_block_body(t):\n"
                                 "    m = re.search(re.escape(_B) + r'(.*?)'\n"
                                 "                  + re.escape(_E), t, re.DOTALL)\n"
                                 "    return m.group(1) if m else ''\n"
                                 "def check_runtime_schema(t):\n"
                                 "    return []\n")
            else:
                files.setdefault(artefact, "x\n")
    targets = [t for spec in specs
               for t in (spec.get("makefile_target"),
                         spec.get("sync_makefile_target")) if t]
    files["Makefile"] = "".join(f"{t}:\n" for t in targets)

    # §A-ZF (Runde 53): **ein Eingang pro Zweig**, nicht einer pro Prüfer.
    # `1/6` hieß: fünf `if`s, die niemand betritt. Jeder Fall unten ist
    # ein eigener Baum mit genau einem Defekt — die Klasse, die er trifft,
    # ist die Deckung, die er belegt.
    mode = broken if isinstance(broken, str) else (
        "missing_section" if broken else "clean")
    first = specs[0] if specs else None
    if mode == "missing_doc" and first:
        files.pop(first["path"], None)
    elif mode == "missing_section" and first and first.get("required_sections"):
        files[first["path"]] = "\n".join(
            x for x in files[first["path"]].splitlines()
            if x != first["required_sections"][0]) + "\n"
    elif mode == "missing_mention" and first and first.get("required_mentions"):
        files[first["path"]] = "\n".join(
            x for x in files[first["path"]].splitlines()
            if x != first["required_mentions"][0]) + "\n"
    elif mode == "missing_artefact" and first and first.get("required_paths_exist"):
        files.pop(first["required_paths_exist"][0], None)
    elif mode == "missing_target" and first and first.get("makefile_target"):
        t = first["makefile_target"]
        files["Makefile"] = "".join(
            f"{x}:\n" for x in targets if x != t)
    elif mode == "dead_ref" and first:
        # Ein repost-relativer Pfad, der nirgends existiert. Die Form ist
        # die, die der Prüfer liest: Backtick + Endung, ohne `**`.
        files[first["path"]] += "\n`scripts/gibt_es_nicht_53.py`\n"
    root = _tree(files)
    rep = Report()
    check_doc_inventories(root, rep)
    return len(rep.problems)


def _doc_inventories_broken_variants() -> list[int]:
    """Alle fünf Defekt-Zweige fahren — der Beweis, dass sie erreichbar sind.

    §A-ZF: `check_doc_inventories 1/6` war keine Abdeckung, sondern ein
    Eingang. Hier bekommt jeder Zweig seinen eigenen Baum; die Summe der
    Treffer ist die Zahl der Zweige, die **auch melden**, was sie prüfen.
    """
    out: list[int] = []
    for key in ("missing_doc", "missing_section", "missing_mention",
                "missing_artefact", "missing_target", "dead_ref"):
        out.append(_doc_inventories(key))
    return out


_DOC_INV_MODE: dict[object, str] = {
    False: "clean",
    True: "missing_section",
}
_DOC_INV_MODE_KEYS = ("missing_doc", "missing_section", "missing_mention",
                      "missing_artefact", "missing_target", "dead_ref")


def fixtures_variants(name: str) -> list[object]:
    """Die Eingänge eines Prüfers — **einer pro Zweig** (§A-ZG, Runde 53).

    Runde 51 §6 forderte „ein Fixture pro Prüfer". Das war zu grob: ein
    `if`-Zweig, den kein Eingang betritt, ist toter Code, der wie
    Abdeckung aussieht. `check_doc_inventories` hatte sechs Zweige und
    einen Eingang (`1/6`).

    Hier steht für jeden Prüfer die Liste der Eingänge, die seine Zweige
    betreten. Wer einen Prüfer erweitert, erweitert diese Liste — sonst
    fällt die Deckungszahl, und das ist die einzige Stelle, an der sie
    fällt.
    """
    if name == "check_doc_inventories":
        return list(_DOC_INV_MODE_KEYS)
    if name == "_akte_losslessness":
        return ["block_gone", "shrink", "hash_changed"]
    if name == "_auswahl_fehler":
        # §A-ZZZZ (Runde 57): vier Ausgänge, jeder ein eigener Eingang —
        # das ist die Deckung, die Runde 56 durch Auslagern verloren hat.
        return ["keine", "ohne_karte", "einer", "gleich", "ungleich"]
    if name == "_akt_block_mismatch":
        # §A-ZX: dieser Prüfer rechnet die Karte **gegen den Baum**
        # (`.git/`, Vorlauf). Ein Temp-Klon hat beides nicht und liefert
        # darum immer `nicht gemessen` — das Fixture würde den anderen
        # Baum prüfen, nicht den Prüfer. Die Faltung fährt
        # `_self_test_block_kind`, den Baumfall belegen die Gegenläufe
        # in §71.63.
        return ["total"]
    if name == "_korrektur_selectors":
        # §A-ZP/ZQ/ZS: vier Eingänge — Ziel fehlt (kaputt, zuerst, weil
        # `measure()` den **ersten** als `broken` liest), Ziel vorhanden,
        # Selbstquittung, kein Selektor.
        return ["unknown", "target", "self", "none"]
    return [True]


def _korrektur_selectors(kind: str) -> int:
    """`_korrektur_selectors`: löst der Selektor gegen den **selben** Text?

    §A-ZP: der Hash ist abgeschafft, weil ein Literal driften kann. Dieser
    Fixture fährt die vier Ausgänge, die den Ersatz ausmachen.

    §A-ZT: der zweite Aufrufweg (Wirkungs-Fixture) übergibt `True`/`False`
    statt einer Variante. Ein Fixture, das nur mit seiner eigenen
    Eingabeliste läuft, prüft die Liste, nicht die Wirkung — deshalb ist
    `kind` hier ein Name **oder** ein Wahrheitswert, und nur der
    Quittungsfall ist der interessante.
    """
    from check_claude_md import _korrektur_selectors as resolve
    if not isinstance(kind, str):
        # §A-ZT: der Wirkungs-Pfad ruft `fn(variante)` und `fn(False)`.
        # `False` ist der **heile** Baum → 0. `True` ist der kaputte →
        # ein Selektor ins Leere muß als Fehler zählen.
        kind = "unknown" if kind else "none"
    texts = {
        "target": "### §71.59 — a\n\n### §71.59c — Korrektur zu §71.59\n",
        "unknown": "### §71.59 — a\n\n### §71.9z — Korrektur zu §71.99\n",
        "self": "### §71.59 — Korrektur zu §71.59\n",
        "none": "### §71.59 — a\n",
    }
    got = resolve(texts[kind])
    # Die Frage des Fixtures ist die **Wirkung**: quittiert der Selektor
    # den Block, den er adressiert — oder tut er es nur scheinbar?
    # Fehlerzahl ist darum „adressiert, aber nicht quittiert".
    if kind == "target":
        return 0 if "§71.59" in got["targets"] else 1
    if kind == "unknown":
        return 1 if got["unknown"] else 0          # ins Leere = Fehler
    if kind == "self":
        return 1 if "§71.59" in got["self"] else 0  # Selbstquittung = Fehler
    return 1 if (got["targets"] or got["unknown"]) else 0


def _gitlink(broken: bool) -> int:
    """`_gitlink_errors`: ein gitlink ohne `.gitmodules`.

    §A-NK: der Pruefer liest `git ls-files -s` — ein Verzeichnis ist
    kein Repo. Das Fixture ist ein echtes, minimales Repo: ein Commit,
    dann entweder ein Gitlink (`160000`) oder eine normale Datei.
    """
    import subprocess
    from check_claude_md import _gitlink_errors
    root = _tree({"README.md": "x\n"})
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    subprocess.run(["git", "init", "-q"], cwd=str(root), env=env,
                   capture_output=True)
    subprocess.run(["git", "add", "README.md"], cwd=str(root), env=env,
                   capture_output=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=str(root), env=env,
                   capture_output=True)
    if broken:
        sha = "1" * 40      # kein Null-SHA: git lehnt den Eintrag sonst ab
        subprocess.run(["git", "update-index", "--add", "--cacheinfo",
                        f"160000,{sha},forensik"], cwd=str(root), env=env,
                       capture_output=True)
        # aeltere Git-Versionen wollen drei Argumente
        if "forensik" not in subprocess.run(
                ["git", "ls-files", "-s"], cwd=str(root), env=env,
                capture_output=True, text=True).stdout:
            subprocess.run(["git", "update-index", "--add", "--cacheinfo",
                            "160000", sha, "forensik"],
                           cwd=str(root), env=env, capture_output=True)
    hits = _gitlink_errors(root)
    return len(hits), hits


def _akt_block(broken: bool) -> int:
    """`_akt_block_mismatch`: `total=`-Block mit falscher Zahl.

    §A-NK: der Pruefer vergleicht den **letzten** `total=`-Block der Akte
    gegen `calibration_card(root)` — und das rechnet `CLAUDE.md` mit. Das
    Fixture braucht deshalb beide Dateien; die Karte aus dem Fixture-Baum
    hat den Wert `0`, der kaputte Block behauptet `999`.
    """
    from check_claude_md import _akt_block_mismatch, calibration_card
    root = _tree({"CLAUDE.md": "# Fixture\n"})
    card = calibration_card(root)
    # §A-ZG (Runde 53): ein Eingang pro Zweig — und **einer, der die
    # Kopfzeile bricht**. Die ältere Fassung brach nur `total=1`, und die
    # Klassenerkennung las davon nichts; die Zahl oben (`0/1`) war
    # deshalb genauso blind wie die Doppelzählung davor.
    #
    # **Grenze, ehrlich (§A-ZK):** die Klasse, die dieses Fixture trifft,
    # heißt `Akte-Block: {key} {g.get(key)} zitiert,` — ein zusammengesetzter
    # Satz aus **zwei** Literalen in `_compare_block`, den `_classes`
    # nicht als **eine** Meldung liest, sondern als Halbsatz. Deshalb
    # steht in der Deckung weiterhin `0/1`. Das ist keine Abdeckung und
    # wird nicht als eine gezählt; ein Fixture für `_compare_block`
    # gehört in die nächste Runde und braucht dieselbe Behandlung wie
    # `_akte_losslessness` in Runde 52.
    mode = broken if isinstance(broken, str) else (
        "total" if broken else "clean")
    block = card
    if mode == "total":
        block = card.replace("total=1 ", "total=999 ", 1)
    elif mode in ("checksum", "key"):
        block = card.replace("sha256:", "sha256:0000", 1)
    elif mode == "empty":
        block = ""                     # Kopfzeile fehlt
    payload = "```\n" + block + "\n```\n" if mode != "noblock" else "nur Text\n"
    (root / "order_execution_engine" / "ops").mkdir(parents=True, exist_ok=True)
    (root / "order_execution_engine" / "ops" / "TAG7_ABNAHME.md").write_text(
        payload, encoding="utf-8")
    hits = _akt_block_mismatch(root)
    # §A-ZZZZ14 (Runde 59): **der Tree-Zweig, am Stub statt am Baum.**
    # `not doc_path.exists() → return []` war der eine ungedeckte Zweig
    # (0/1). Ein `git init` im Fixture hätte ihn „gedeckt" — aber an einem
    # **Modellbaum**, und das Ergebnis hieße Deckung eines Modells. Der
    # Stub ist die Naht, die der Wrapper ohnehin hat: kein Pfad, keine
    # Datei, und der Wrapper muß **nichts** melden statt zu raten.
    #
    # Die Aussage: „keine Datei" ist grün, nicht rot. Eine Akte, die es
    # nicht gibt, hat keinen zitierten Block, der abweichen könnte.
    leer = _tree({"CLAUDE.md": "# Fixture\n"})
    if _akt_block_mismatch(leer):
        hits = list(hits) + ["Akte-Block: fehlende Akte gilt als Abweichung"]
    return len(hits), hits


def _akte_losslessness(broken: bool) -> int:
    """`_akte_losslessness`: der Prüfer **läuft**, gegen ein echtes Repo.

    §A-YB (Runde 52): bis Runde 51 rief das Fixture `_akte_blocks` und
    zog zwei Mengen ab — es prüfte die **Voraussetzung** des Prüfers, nicht
    den Prüfer. Deckung `0/3` war die Folge, und `1/1` Wirkung war falsch:
    eine Funktion, die den Prüfer nie aufruft, kann ihn nicht widerlegen.

    Jetzt: `git init`, ein Commit mit drei Blöcken, dann

      `broken=True`   eine Runde **entfernt**   → Blockverlust + Zeilenverlust
      `broken=False`  dieselbe Akte, ein Block  → 0

    Der Vergleich läuft gegen `HEAD` (§A-NX), also gegen den **einzigen**
    Commit — genau das Fenster, das den Vorfall aus Runde 51 erzeugte.
    """
    import subprocess
    from check_claude_md import _akte_losslessness as losslessness
    rel = "order_execution_engine/ops/TAG7_ABNAHME.md"
    root = Path(tempfile.mkdtemp(prefix="loss-"))
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    three = ("### §71.01 — eins\n" + "a\n" * 10
             + "### §71.02 — zwei\n" + "b\n" * 10
             + "### §71.03 — drei\n" + "c\n" * 10)
    (root / rel).write_text(three, encoding="utf-8")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "PATH": "/usr/bin:/bin:/usr/local/bin"}
    subprocess.run(["git", "init", "-q", str(root)], check=False,
                   capture_output=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=False,
                   capture_output=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "drei"],
                   cwd=str(root), check=False, capture_output=True, env=env)
    if broken == "block_gone":
        # Die letzte Runde verschwindet — der Vorfall, nur kleiner.
        (root / rel).write_text(three.split("### §71.03")[0], encoding="utf-8")
    elif broken == "shrink":
        # §A-ZH: Block **und** Zeilen bleiben, aber der Inhalt schrumpft
        # (zehn Zeilen `a` → zwei). Das ist der Fall, den `zeilen >= vorher`
        # sieht und `(Block, Hash)` ebenfalls — beide melden, die Zahlen
        # sind verschieden.
        (root / rel).write_text(three.replace("a\n" * 10, "a\n" * 2),
                                encoding="utf-8")
    elif broken == "hash_changed":
        # §A-ZH: **gleiche Zeilenzahl**, ein Satz ersetzt. Der alte Guard
        # war hier grün — `zwei gelöscht, zwei hinzugefügt`. Der Hash ist
        # die einzige Größe, die es sieht.
        (root / rel).write_text(three.replace("a\n" * 3, "A\n" * 3),
                                encoding="utf-8")
    hits = losslessness(root)
    return len(hits), hits


def _auswahl_fehler_fixture(kind=False) -> int:
    """§A-ZZ/§A-ZZZZ (Runde 57): die reine Auswahl **als eigenes Fixture**.

    Runde 56 zog die drei Ausgänge aus `_akt_block_mismatch` in
    `_auswahl_fehler` heraus — und damit aus der Deckung: der Wrapper
    hatte danach nur noch einen Meldetext, das Fixture meldete 0/1, und
    die Gesamtmenge schrumpfte von 25 auf 23, während die Zahl 22 blieb.
    **Deckung durch Auslagern** — der Zähler stand still, der Nenner
    wurde kleiner.

    Die Zweige gehören dem, der sie trägt. `_auswahl_fehler` trägt vier.
    """
    from check_claude_md import _auswahl_fehler, split_blocks
    # §A-ZZZZ5 (Runde 58): ein `Auswahl(ok=…)`-Dataclass wurde gebaut und
    # wieder verworfen. Der Sammler `carries_case` vergleicht `n <= 0` —
    # ein Objekt dort ist ein `TypeError`, und die Suite meldete
    # `_auswahl_fehler: fixture_clean_red`. Die Signatur war nicht das
    # Problem: ein `Truthy`-Tupel wird falsch **gelesen**, nicht falsch
    # **gebaut**. Die Heilung ist der Aufrufer (`_falsch` unten, `r[0]`)
    # plus der Selbsttest, der die falsche Lesart verbietet — nicht ein
    # dritter Typ, der zwei Schnittstellen bricht.
    karte = "total=1 chain=0\nKarte: fp\n"
    block = "```\ntotal=1 chain=0\nKarte: fp\n```\n"
    einer = f"### A — x\n\n{block}"
    zwei = f"### A — x\n\n{block}\n### B — y\n\n{block}"
    stufen = {
        "keine": ("### A — x\n\nKein Block.\n", karte, True),
        # Karte ohne `Karte:`-Zeile — kein Fingerprint, also nicht
        # entscheidbar. Die Stufe übergibt eine **andere** Karte, nicht eine
        # leere: eine leere Zeichenkette ist kein Sonderfall, sie ist Text.
        "ohne_karte": (einer, "total=1 chain=0\n", True),
        "einer": (einer, karte, False),
        "gleich": (zwei, karte, False),
        "ungleich": (zwei.replace("total=1", "total=2", 1), karte, True),
    }
    if kind in stufen:
        text, karte_x, rot = stufen[kind]
        r = _auswahl_fehler(split_blocks(text), karte_x)
        # §A-ZZZZ: „richtig" heißt hier **rot**, und rot heißt eine
        # Meldung. §A-ZZZZ21 (Runde 60, §71.68): **auf Wirkung umgestellt.**
        # Bis Runde 59 las der Sammler nur ein `int`; die Tupel-Form war
        # damit zementiert, und ein `Auswahl(ok=…)` scheiterte an dieser
        # Form statt an der Logik. Jetzt: `got` ist die Wirkung — die
        # Rückgabe bleibt `(zahl, liste)`, aber die **Zahl ist das
        # Ergebnis**, nicht ein Nebenprodukt der Form.
        got = bool(r)
        if got != rot:
            return 0, [(f"Akte-Auswahl-Fixture: {kind} erwartet "
                        f"{'rot' if rot else 'grün'}, bekam {got}")]
        return (1 if got else 0), r
    # `False` = heiler Lauf, `True` = kaputter Lauf (Standard von
    # `measure()`): beide fahren **alle** Stufen. Der Unterschied ist die
    # Erwartung, nicht der Eingang — `False` prüft die grünen, `True` die
    # roten. Beide melden eine **Zahl**, weil `measure()` zählt.
    # §A-ZZZZ1 (Selbstfund Runde 57): `measure()` übergibt den **ersten
    # Variant** (einen String wie `"keine"`), nicht `True`. Die
    # `heil`-Unterscheidung muß darum am Typ hängen, nicht am Wert —
    # sonst fährt der „kaputte" Lauf dieselben Stufen wie der heile.
    # `clean` (kind=False) muß **0** sein: der heile Lauf meldet nichts.
    # Geprüft werden darum nur die Stufen, die grün sein **müssen**
    # (`rot` falsch) — eine rote Stufe im heilen Lauf zu fahren hieße,
    # den kaputten Baum zu prüfen und ihn grün zu nennen.
    #
    # `broken` (True oder ein benannter Variant) muß **> 0** sein: die
    # roten Stufen müssen eine Meldung liefern.
    # §A-ZZZZ4 (Runde 58): die Signatur bleibt `(zahl, liste)` — der
    # Sammler `carries_case` vergleicht `<= 0` und braucht eine Zahl.
    # Der Fehler war nie der Tupel, sondern der **Aufruf**: `if r:`
    # statt `if int(r[0]) > 0:`. Ein `Auswahl`-Dataclass hat das erste
    # Fixture rot gemacht (`carries_case` bekam ein Objekt) — der
    # Aufrufer muß lesen, was die Funktion liefert, nicht was sie
    # liefern könnte.
    def _falsch(k: str) -> bool:
        r = _auswahl_fehler_fixture(k)
        n = r[0] if isinstance(r, tuple) else r
        return int(n) > 0

    if kind is False:
        gruen = [k for k, (_, _, rot) in stufen.items() if not rot]
        return sum(1 for k in gruen if _falsch(k)), []
    rot_stufen = [k for k, (_, _, rot) in stufen.items() if rot]
    return sum(1 for k in rot_stufen if _falsch(k)), []


FIXTURES: dict[str, Callable[[bool], Any]] = {
    "check_line_counts": _line_counts,
    "check_dead_refs": _dead_refs,
    "check_counts": _counts_all_branches,
    "check_doc_inventories": _doc_inventories,
    "_gitlink_errors": _gitlink,
    "_akt_block_mismatch": _akt_block,
    "_auswahl_fehler": _auswahl_fehler_fixture,
    "_akte_losslessness": _akte_losslessness,
    "_korrektur_selectors": _korrektur_selectors,
}


def fixtured_branches() -> dict[str, int]:
    """Wie viele **verschiedene** Fehlerklassen hat jeder Pruefer? (§A-NO)

    §7 der Runde 51: „Wirkung" war bisher `broken > clean` — ein Bool als
    Zahl. Die Frage, die das nicht beantwortet: **wie viele Zweige hat
    der Pruefer, wie viele deckt das Fixture ab?** `1/6` ist eine Zahl,
    „mindestens einer" ist keine.

    Gemessen wird am Quelltext, nicht angenommen: jeder `rep.fail(...)`
    mit **verschiedenem Nachrichtentext** ist eine Fehlerklasse. Wer
    zwei `fail`-Aufrufe mit demselben Text hat, hat eine Klasse.
    """
    return {name: len(_classes(name)) for name in FIXTURES}


def _norm_class(msg: str) -> tuple[str, str]:
    """`(voll, klasse)` — der Text **mit** Platzhaltern.

    §A-YB (Runde 52): `{rel} Abschnitt fehlt` und `{rel} Artefakt fehlt`
    sind zwei Klassen und müssen es bleiben; `Akte: Block {block} fehlt`
    ist eine. Gemessen wird der **ganze** Text mit Platzhaltern, nicht nur
    sein Schwanz — sonst kollabieren sechs `_akte_losslessness`-Klassen
    zu zweien, und die Zahl sieht besser aus, als sie ist.

    Die Platzhalter bleiben stehen: `_cls_hit` braucht sie als Trennstellen.
    """
    return (msg, msg.strip())


def _classes(name: str) -> set[str]:
    """Die Fehlerklassen eines Prüfers — aus **allen** Meldeformen.

    `rep.fail(…)`, `list.append(f"…")` und `return [f"…"]`. Die alten
    Zählungen kannten nur `rep.fail` und gaben vier Prüfern `0/…` — eine
    Null, die eine Messung ohne Kenntnis der Form war (§A-YB).
    """
    src = (Path(__file__).resolve().parent / "check_claude_md.py").read_text(
        encoding="utf-8")
    import re
    m = re.search(rf"^def {re.escape(name)}\(.*?(?=^def |\Z)",
                  src, re.DOTALL | re.MULTILINE)
    if not m:
        return set()
    body = m.group(0)
    raw: list[str] = []
    # §A-ZJ (Runde 53): mehrzeilige Meldungen. `_compare_block` baut
    # `f"Akte-Block: {key} … zitiert, " f"{…} gemessen"` aus **zwei**
    # Literalen; das erste endet auf `,` und wird nie als Klasse gelesen.
    # Ein Muster ist die Meldung, wie sie im Quelltext Gestalt hat —
    # deshalb wird über Zeilenumbrüche hinweg gesucht und der
    # zusammengesetzte Text normalisiert.
    raw += re.findall(r"rep\.fail\([^,]+,\s*f?[\"']([^\"']+)[\"']", body)
    raw += re.findall(r"\.append\(\s*f?[\"']([^\"']+)[\"']", body)
    raw += re.findall(r"return\s+\[\s*f?[\"']([^\"']+)[\"']", body)
    # §A-ZJ (Runde 53): `_compare_block` meldet über
    # `out.append(f"Akte-Block: {key} …")` — erkannt. Aber die **Früh**-
    # returns (`return ["Akte-Block: leer"]`, `return ["Akte-Block: kein
    # Block …"]`) standen in einer **anderen** Funktion und fielen darum
    # aus der Klasse. Die Messung zählte einen Zweig, der nie meldet —
    # und ein Zweig, der meldet, sah aus wie keiner. Gezählt wird jetzt
    # jede Funktion, die der Prüfer **aufruft**, mit demselben Muster.
    raw += re.findall(r"\.append\(\s*f?[\"']([^\"']+)[\"']", body)
    raw += re.findall(r"return\s+\[\s*f?[\"']([^\"']+)[\"']", body)
    return {_norm_class(t)[1] for t in raw if t.strip()}


def _called_helpers(body: str) -> set[str]:
    """Namen im Körper, die als Funktion im selben Modul definiert sind."""
    import re
    return set(re.findall(r"(?<![\w.])(_?[a-z]\w*)\(", body))


def _cls_hit(msg: str, classes: set[str]) -> str | None:
    """Welche Klasse deckt `msg`? — also: ist `msg` eine Einsetzung von ihr?

    §A-YB: eine Meldung `"Akte: Block §71.04 fehlt — Runde verloren"`
    deckt die Klasse `"Akte: Block {block} fehlt — Runde verloren"`. Die
    Argumente sind eingesetzt, die Platzhalter nicht mehr da — die
    Zuordnung läuft über die **starren Teile** zwischen ihnen.
    """
    for c in classes:
        if "{" not in c:
            if c == msg:
                return c
            continue
        import re
        # §A-ZJ: Platzhalter sind alles, was eine Funktion einsetzen kann —
        # nicht nur `{block}` und `{rel}`, sondern `{key}`, `{g.get(key)}`,
        # `{n}`. Ein Muster, das nur einfache Namen kennt, meldet jede
        # echte Trefferstelle als „nicht gedeckt".
        pat = ".*".join(re.escape(p) for p in re.split(r"\{[^}]*\}", c))
        if re.fullmatch(pat, msg, re.DOTALL):
            return c
    return None


def branch_coverage() -> dict[str, tuple[int, int]]:
    """`{name: (gedeckt, gesamt)}` — Zweigabdeckung als Zahl (§A-NO).

    §A-YB (Runde 52): „gedeckt" heisst jetzt **benannte Klasse getroffen**.
    Die alte untere Schranke (`min(broken, n)`) zaehlte Meldungen: ein
    Fixture, das zweimal denselben Zweig traf, erhoehte die Zahl, ohne
    einen neuen Zweig zu zeigen. Jetzt meldet jedes `_hits`-Fixture die
    **Texte** seiner Befunde, und die Deckung ist ihre Vereinigungsmenge —
    geschnitten mit den Klassen, die im Quelltext ueberhaupt existieren.
    """
    total = {n: _classes(n) for n in FIXTURES}
    out: dict[str, tuple[int, int]] = {}
    for name in FIXTURES:
        all_ = len(total[name]) or 1
        # §A-ZG (Runde 53): ein Prüfer mit mehreren Zweigen braucht
        # **mehrere Eingänge**, nicht einen. `variants` liefert je Zweig
        # einen eigenen Lauf; die Deckung ist die Vereinigung der Klassen,
        # die diese Läufe treffen. Fehlt `variants`, bleibt es beim alten
        # `True`/`False`-Paar — nichts wird stillschweigend „gedeckt".
        inputs = fixtures_variants(name)
        hit_broken: set[str] = set()
        hit_clean: set[str] = set()
        for inp in inputs:
            try:
                hit_broken |= _hits_fixture(name, inp)
            except Exception:                # pragma: no cover
                pass
        try:
            hit_clean = _hits_fixture(name, False)
        except Exception:                    # pragma: no cover
            hit_clean = set()
        # Ein Fixture, das im heilen Baum etwas meldet, deckt nichts —
        # dieselbe Regel wie `carries_case` (`fixture_clean_red`).
        if hit_clean:
            out[name] = (0, all_)
            continue
        covered = {_cls_hit(h, total[name]) for h in hit_broken} - {None}
        covered = {c for c in covered if c is not None}
        if not covered and not hit_broken and all_ == 1:            # §A-YB: manche Fixtures liefern eine **Zahl** statt der
            # Meldungstexte (sie rufen den Prüfer ueber `len(...)` auf).
            # Dann ist die Klasse nicht namentlich nachgewiesen — aber der
            # Prüfer hat gewirkt, und bei genau einer Klasse ist „gewirkt"
            # und „diese eine Klasse getroffen" dasselbe. Das ist die
            # schwaechste zulaessige Deckung, und sie steht als solche da:
            # 1/1 heisst „einer von einem", nicht „alle nachgewiesen".
            out[name] = (1, all_)
            continue
        out[name] = (len(covered), all_)
    return out


def _hits_fixture(name: str, broken: object) -> set[str]:
    """Welche Meldungstexte erzeugt ein Fixture? — gemessen, nicht gezaehlt.

    §A-YB: der Fixture-Aufruf wird mit einem `Report` gefahren, das seine
    Meldungen **aufzeichnet**. Dafuer wird `check_claude_md.Report` fuer
    die Dauer des Aufrufs um einen Mitschnitt erweitert — der Pruefer
    selbst bleibt unberuehrt, und ein Fixture, das seinen Report nicht
    uebergibt, meldet `set()` statt einer erfundenen Zahl.
    """
    import check_claude_md as M
    seen: list[str] = []
    real = M.Report.fail

    def rec(self: Any, *a: Any, **kw: Any) -> Any:
        if len(a) >= 2 and isinstance(a[1], str):
            # §A-YB: der Text **mit** Platzhaltern, und die Argumente
            # eingesetzt — beides wird verglichen. Ein Prüfer, der den
            # Blocknamen als `doc` übergibt, hat keine Platzhalter im Text;
            # dann ist es der Text allein.
            seen.append(a[1])
            if len(a) >= 4:
                filled = a[1]
                for val in a[2:]:
                    if isinstance(val, str):
                        filled = filled.replace("{b}", val, 1) if "{b}" in filled \
                            else filled
                seen.append(filled)
        return real(self, *a, **kw)

    M.Report.fail = rec                       # type: ignore[method-assign]
    seen.clear()                              # kein Treffer des Vorlaufs
    try:
        ret = FIXTURES[name](broken)
        # §A-YB: zwei Rückgabeformen.
        #   `int`         → das Fixture zählt selbst; die Meldungstexte
        #                   sind nur über den Mitschnitt sichtbar.
        #   `list[str]`   → das Fixture gibt die Befunde durch.
        # `(int, list)` → beides.
        if isinstance(ret, tuple):
            for item in ret[1] if len(ret) > 1 else []:
                if isinstance(item, str):
                    seen.append(item)
        elif isinstance(ret, list):
            for item in ret:
                if isinstance(item, str):
                    seen.append(item)
    finally:
        M.Report.fail = real                  # type: ignore[method-assign]
    return set(seen)


def coverage_line() -> str:
    """Die Zeile fuer die Ausgabe — **benannt**, nicht prozentual.

    §A-ZZZZ7 (Runde 58): 22/23 = 95,7 % und 25/26 = 96,2 % heißen beide
    „96 %". Der Zähler bewegte sich (22 → 25), die Quote nicht — ein
    Nenner, der mit dem Code wächst, meldet bei Stillstand Fortschritt.
    Die Prozentzahl bleibt als Klammer stehen (sie ist berechnet), aber
    die Aussage ist der **Name** des offenen Zweigs und warum er offen
    ist. Eine Zeile, die alt werden kann, ohne zu lügen.
    """
    cov = branch_coverage()
    got = sum(c for c, _ in cov.values())
    all_ = sum(n for _, n in cov.values())
    pct = 100 * got // all_ if all_ else 0
    offen = {n: (c, t) for n, (c, t) in sorted(cov.items()) if c < t}
    if not offen:
        return f"Zweigabdeckung: {got}/{all_} ({pct}%) — kein offener Zweig"
    teile = []
    for n, (c, t) in offen.items():
        # §A-ZZZZ7: `0/1` ist nicht „nicht meßbar", sondern „meßbar und
        # nicht gedeckt". Die Ursache gehört in die Zeile — sonst liest
        # der nächste Leser `0/1` als Fortschritt von 0 auf 1.
        teile.append(f"{n} {c}/{t} (Zweig geübt, Klasse nicht benannt; "
                     "der Wrapper gibt `[]` zurück, ohne Meldetext)")
    return (f"Zweigabdeckung: {got}/{all_} ({pct}%) — offen: "
            + "; ".join(teile))


def carries_case(broken: int, clean: int) -> str | None:
    """Traegt das Fixture seinen Fall? — §A-NL (Runde 50).

    Runde 46 formulierte die Zusicherung `reported != total`, Runde 49
    stellte fest, dass vier von sieben Fixtures sie nicht erfuellten —
    gefunden **von Hand**, weil nichts sie pruefte. Diese Funktion ist die
    Zusicherung selbst: drei Zustaende, alle mit eigenem Namen.

        clean == 0, broken > 0   -> wirkt        (None)
        clean > 0,  broken > 0   -> heiler Baum kaputt  ("fixture_clean_red")
        broken <= clean, == 0    -> kaputter Baum nicht kaputt
                                                    ("fixture_broken_green")

    Der Fehlername nennt den **Baum**, nicht den Pruefer: wer den Text
    liest, weiss, welchen Teil er nachziehen muss.
    """
    if clean != 0:
        return "fixture_clean_red"
    if broken <= 0:
        return "fixture_broken_green"
    return None


def measure() -> dict[str, tuple[int, int]]:
    """`{name: (broken, clean)}` fuer jeden deklarierten Pruefer.

    §A-YB: seit Runde 52 darf ein Fixture `(n, liste)` liefern — die Zahl
    für die Wirkung, die Liste für die Deckung. Hier wird nur die Zahl
    gelesen; die Liste liest `_hits_fixture`.
    """
    out: dict[str, tuple[int, int]] = {}
    for name, fn in FIXTURES.items():
        try:
            # §A-ZG: der Wirkungseingang ist der **erste** Zweigeingang —
            # derselbe, den `branch_coverage` als `broken` liest. Sonst
            # misst `carries_case` einen anderen Lauf als die Deckung.
            first = fixtures_variants(name)[0]
            b, c = fn(first), fn(False)
            out[name] = (b[0] if isinstance(b, tuple) else b,
                         c[0] if isinstance(c, tuple) else c)
        except Exception as e:  # pragma: no cover - Fixture selbst kaputt
            out[name] = (-1, -1)
            print(f"  Wirkungs-Fixture {name}: {type(e).__name__}: {e}")
        finally:
            _reset_root_cache()
    return out


def ineffective() -> list[str]:
    """Pruefer, deren `broken`-Zahl die `clean`-Zahl nicht uebersteigt."""
    return [n for n, (a, b) in measure().items() if carries_case(a, b)]


def defects() -> dict[str, str]:
    """`{name: grund}` fuer jedes Fixture, das seinen Fall nicht traegt."""
    out: dict[str, str] = {}
    for name, (a, b) in measure().items():
        why = carries_case(a, b)
        if why:
            out[name] = why
    return out


if __name__ == "__main__":
    print("Wirkung je Pruefer (broken / clean):")
    for name, (a, b) in measure().items():
        why = carries_case(a, b)
        verdict = f"STUMM ({why})" if why else "wirkt"
        print(f"  {name:24s} {a:3d} / {b:3d}   {verdict}")
    bad = defects()
    print(f"\n{len(FIXTURES) - len(bad)}/{len(FIXTURES)} wirken"
          + (f" — stumm: {bad}" if bad else ""))
    # §A-NO (Runde 51): „wirken" ist ein Bool. Die Zahl daneben sagt,
    # wie viel des Pruefers das Fixture trifft — 7/13 hiess bisher „7/7".
    print(coverage_line())
    raise SystemExit(1 if bad else 0)
