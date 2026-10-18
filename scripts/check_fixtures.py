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
    """`check_line_counts`: Zeile `# Wave N: k agents, l lines`."""
    from check_claude_md import check_line_counts, Report
    table = ("| Welle | Name | Agenten | Modul | Fokus |\n"
             "|-------|------|---------|-------|-------|\n"
             "| 7 | Ops | 9 | `ops/agents.py` | x |\n")
    claimed = 999 if broken else 3
    root = _tree({"agents_b2g/ops/agents.py": "a\nb\nc\n"})
    text = table + f"# Wave 7: 9 agents, {claimed} lines\n"
    rep = Report()
    check_line_counts(text, root, rep)
    return len(rep.problems)


def _dead_refs(broken: bool) -> int:
    """`check_dead_refs`: ein Backtick-Pfad, der nicht existiert."""
    from check_claude_md import check_dead_refs, Report
    ref = "scripts/gibt-es-nicht.py" if broken else "scripts/da-ist-er.py"
    root = _tree({"scripts/da-ist-er.py": ""})
    rep = Report()
    check_dead_refs(f"Siehe `{ref}` fuer Details.\n", root, rep)
    return len(rep.problems)


def _counts(broken: bool) -> int:
    """`check_counts`: eine Agentenzahl, die der Tabelle widerspricht.

    §A-NK: `parse_waves` liest die **Tabelle**, nicht den Satz. Ein
    Fixture ohne Tabelle misst `0` gegen `243` und meldet zwei — das ist
    kein Fehler des Pruefers, sondern ein Fixture, das den Fall nicht
    enthaelt. Die Tabelle kommt daher aus der echten Datei, nur der Satz
    wechselt.
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


def _doc_inventories(broken: bool) -> int:
    """`check_doc_inventories`: Inventar-Dokument fehlt.

    §A-NK: der Pruefer liest `DOC_INVENTORY_FILES` — ein **fehlendes
    Dokument** ist immer ein Fehler, unabhaengig vom Inhalt. Das ist der
    kleinste Fall mit garantierter Wirkung: leerer Baum gegen einen mit
    allen deklarierten Dateien.
    """
    from check_claude_md import check_doc_inventories, Report, DOC_INVENTORY_FILES
    specs = list(DOC_INVENTORY_FILES)

    def body(spec: dict) -> str:
        """Pflichtabschnitte, -erwaehnungen und -pfade — die Spec sagt, was."""
        parts = ["# " + spec["path"]]
        parts += [s for s in spec.get("required_sections", [])]
        parts += [m for m in spec.get("required_mentions", [])]
        return "\n".join(parts) + "\n"

    files = {spec["path"]: body(spec) for spec in specs}
    for spec in specs:
        for artefact in spec.get("required_paths_exist", []):
            files.setdefault(artefact, "x\n")
    targets = [t for spec in specs
               for t in (spec.get("makefile_target"),
                         spec.get("sync_makefile_target")) if t]
    files["Makefile"] = "".join(f"{t}:\n" for t in targets)
    # Kaputt: **ein** Pflichtabschnitt fehlt in **einem** Dokument.
    if broken and specs and specs[0].get("required_sections"):
        first = specs[0]
        files[first["path"]] = "\n".join(
            x for x in files[first["path"]].splitlines()
            if x != first["required_sections"][0]) + "\n"
    root = _tree(files)
    rep = Report()
    check_doc_inventories(root, rep)
    return len(rep.problems)


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
    return len(_gitlink_errors(root))


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
    # Der Block ist die **Karte selbst** — bis auf eine Zahl im kaputten Fall.
    block = card if not broken else card.replace("total=1 ", "total=999 ", 1)
    (root / "order_execution_engine" / "ops").mkdir(parents=True, exist_ok=True)
    (root / "order_execution_engine" / "ops" / "TAG7_ABNAHME.md").write_text(
        "```\n" + block + "\n```\n", encoding="utf-8")
    return len(_akt_block_mismatch(root))


def _akte_losslessness(broken: bool) -> int:
    """`_akte_losslessness`: ein Rundenblock weniger (Mengeninklusion).

    `broken` heisst hier: der Block **fehlt** — verglichen wird gegen
    `HEAD~1`, und das Fixture hat keinen. Nachgestellt wird das ueber die
    Blockmenge direkt, weil ein temporaeres Repo mit Vorgaenger-Commit
    mehr Aufwand als Aussage waere.
    """
    from check_claude_md import _akte_blocks
    two = "### §71.1 — Runde 1\nx\n### §71.2 — Runde 2\ny\n"
    one = "### §71.1 — Runde 1\nx\n"
    gone = _akte_blocks(two) - _akte_blocks(one if broken else two)
    return len(gone)


FIXTURES: dict[str, Callable[[bool], int]] = {
    "check_line_counts": _line_counts,
    "check_dead_refs": _dead_refs,
    "check_counts": _counts,
    "check_doc_inventories": _doc_inventories,
    "_gitlink_errors": _gitlink,
    "_akt_block_mismatch": _akt_block,
    "_akte_losslessness": _akte_losslessness,
}


def measure() -> dict[str, tuple[int, int]]:
    """`{name: (broken, clean)}` fuer jeden deklarierten Pruefer."""
    out: dict[str, tuple[int, int]] = {}
    for name, fn in FIXTURES.items():
        try:
            out[name] = (fn(True), fn(False))
        except Exception as e:  # pragma: no cover - Fixture selbst kaputt
            out[name] = (-1, -1)
            print(f"  Wirkungs-Fixture {name}: {type(e).__name__}: {e}")
        finally:
            _reset_root_cache()
    return out


def ineffective() -> list[str]:
    """Pruefer, deren `broken`-Zahl die `clean`-Zahl nicht uebersteigt."""
    return [n for n, (a, b) in measure().items() if a <= b]


if __name__ == "__main__":
    print("Wirkung je Pruefer (broken / clean):")
    for name, (a, b) in measure().items():
        verdict = "wirkt" if a > b else "STUMM"
        print(f"  {name:24s} {a:3d} / {b:3d}   {verdict}")
    bad = ineffective()
    print(f"\n{len(FIXTURES) - len(bad)}/{len(FIXTURES)} wirken"
          + (f" — stumm: {bad}" if bad else ""))
