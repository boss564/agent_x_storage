# QA-Prüfergebnisse — 01.08.2026

## Orchestrator v2.4.0 — Lending-Modul-Integration

### Critical-Fix (behoben)
- `module_at_risk` summierte nur `liquidatable + warning` — `critical` wurde übergangen
- Behoben: `module_at_risk = liquidatable + critical + warning`
- Warnungen von 8 auf 4 reduziert

### Invarianz- & Testgrenzen-Hinweis (v2.4.0)
- **Klassifikation & Pipeline:** Die Test-Suite validiert die Datenfluss-Kette der B-Lending-Module und deren Einfluss auf das CHI-Stress-Signal
- **Synthetische Snapshots:** `BlockSnapshot`-Generatoren rekonstruieren Collateral-Mengen algebraisch aus `target_hf`. Die HF-Formel wird zirkulär gespiegelt und nicht unabhängig geprüft
- **Ausblick v2.5.0:** Erweiterung der `BlockSnapshot`-Generatoren um reale Positions-Arrays für echte HF-Formel-Tests

### Backtest-Ergebnis
- Gesamtnote: B (82/100), $2.310M, 2 FP / 2 FN
- 4 verbleibende Inkonsistenz-Warnungen (Klassifikationsunterschiede an Zonengrenzen — erwartet)

---

## 1. Sektions-Amplituden-Audit

Alle 5 Stimmen über S0, S3, S5 geprüft.

| Stimme   | S0 (dB) | S3 (dB) | S5 (dB) | Status |
|----------|---------|---------|---------|--------|
| Kick     | -6.2    | -6.2    | **0.0** | FAIL   |
| Snare    | -8.0    | -8.0    | -8.0    | OK     |
| Hi-Hat   | -12.5   | -12.5   | -12.5   | OK     |
| Bass     | -10.0   | -10.0   | -10.0   | OK     |
| Pad      | -14.0   | -14.0   | -14.0   | OK     |

## 2. Kick-S5-Befund

- **64 Kicks in Sektion 5 verloren**
- Ursache: `sec_amps[5] = 0.0` — Kick-Amplitude für S5 hart auf 0 gesetzt
- Position: `composition_v2.py:312` — `sec_amps`-Array-Initialisierung
- Effekt: Kick-Spur in S5 stumm, alle 64 Kick-Events werden nicht gerendert

## 3. v2-Code-Review (4 Punkte)

| # | Punkt | Ergebnis |
|---|-------|----------|
| 1 | `KICK_STOP_BAR` definiert | DEFINIERT (Bar 128), aber nicht wirksam |
| 2 | Velocity-Normalisierung | OK — Range 0-127 eingehalten |
| 3 | MIDI-Channel-Zuweisung | OK — Channel 10 für Drums korrekt |
| 4 | Note-Off-Event nach Note-On | OK — kein Hängenbleiben |

**Detail zu Punkt 1:** `KICK_STOP_BAR = 128` ist als Konstante gesetzt, wird aber in `render_kick()` nicht ausgewertet. Die Kick-Spur läuft über Bar 128 hinaus weiter.

## 4. Offen

- [ ] Cut-Implementierung (Kick-Stop bei Bar 128 wirksam machen)
- [ ] Re-MD5 nach Cut-Implementierung
- [ ] Re-Verifikation Punkt 1 (nach MD5-Neuberechnung)
