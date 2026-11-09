R29 check_claude_md WIP-Park (D28 Option B + Park)

Ursache der Hook-Umgehung bei Commit 1 (36a4c7d7) und Commit T (7a7824b8):
WT-Stufe-2-Akte-WIP in scripts/check_claude_md.py (+169/-2 vs HEAD)
scheitert auf dem Hook-Index-TMP (mktemp + checkout-index) mit exit:1
(unvollstaendig / kein .git im TMP). HEAD-Checker: exit:0.

Entscheidung D28: Option B + Park
- Arbeitsbaum: HEAD-Stand wiederhergestellt (Standard-Hook ohne Umgehung)
- WIP nicht vernichtet: Diff hier geparkt fuer spaetere Finalisierung (eigenes Gate)
- Option C (dauerhafte Umgehung) abgelehnt

Anwenden spaeter: Diff auf HEAD portieren, Index-TMP-Lauf muss exit:0 liefern,
dann eigener Commit — nicht mit Commit 2 (Exit-2) vermischen.
