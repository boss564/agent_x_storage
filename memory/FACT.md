# Workflow: CLAUDE.md Änderungen

**Why:** Mehrfaches Editieren und Stagen während Wave-Implementierung führt zu MM/AM-Zuständen, bei denen der Index eine veraltete Fassung enthält und der Hook falsch-negative "0 Abweichungen" meldet.

**How to apply:**
1. Vor jedem Hook-Lauf: `git add -A` ausführen, damit der Index mit dem Arbeitsbaum übereinstimmt
2. `git status --short` als ersten Check — MM und AM zeigen genau das Problem an
3. Nach jedem CLAUDE.md-Edit sofort `git add CLAUDE.md`
4. Neue Test-Skripte immer in `check_claude_md.py` → `TEST_SCRIPTS` registrieren (Output-Regex mit 2 Gruppen + Doku-Regex)
5. Neue Wellen-Verzeichnisse und Test-Dateien vollständig stagen, bevor der Hook läuft

**Checker-Formeln für Konsistenz:**
- 23 Hauptwellen × 9 = 207 Agenten (aus Tabelle abgeleitet)
- + Wave 3.5 (+9) + 25 Compliance = 241 total (als Erläuterung daneben)
- Version-Zeile: "207 agents in 23 waves plus Wave 3.5 and 25 compliance agents — 241 total"

[[wave-implementation-checklist]]