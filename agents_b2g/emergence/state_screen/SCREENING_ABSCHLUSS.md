# Zustandsraum-Screening — Abschluss (diagnostischer Vorlauf)

**Status:** abgeschlossen · **kein Studien-Verdict** · HARKing-Sperre aktiv  
**Runner:** `scripts/run_emergence_state_screen.py` · Modul `state_space_screen.py`  
**Artefakte:** dieses Verzeichnis · `/tmp/emergence_state_screen/`

## Ergebnis

| Feld | Wert |
|------|------|
| Outcome-Label | `NONE_CLOSE` |
| Dimensionen | 18 |
| Kandidaten | 0 |
| Laufzeit | ≈ 1 s |
| Seeds / Fenster | 20260901 · warmup=32 · cycles=64 · κ=0 |

**Zentralbefund:** Keine der 18 knotenbezogenen Zustandsdimensionen erfüllt die
I1-Voraussetzung für Partnerselektivität (MAE unter Permutation + Nicht-Globalität).

Das entspricht **Ausgang 3:** Im aktuellen knotenbasierten Zustandsraum `S_i ∈ ℝ^d`
existiert keine partnerselektive Kopplungsgröße in belastbarer Form.

## Einordnung (append-only)

| Dimension | Kurz |
|-----------|------|
| `honor` | Roh-σ hoch, \|ρ\|≈0.99 — fast global; MAE_scaled knapp unter/an Schwelle |
| `inbox_len` | nicht global (\|ρ\|≈0.044), unter Permutation blind (MAE≈0.013) |
| `s_honor` | gesättigt / statisch im Fenster |
| Konfig-Dims | zeitlich statisch — keine Dynamik |
| übrige Dynamik | hohe \|ρ\|, niedrige MAE_scaled |

## HARKing-Sperre

- Keine Hypothese auf **diesen** Daten testen.
- Keine Nachjustierung an `KOPPLUNG_REPUTATION_v1` (`I1_FAILED`) oder der Queue-Studie (`KOPPLUNG_INVALID`).
- Screening liefert nur Charakterisierung; Kandidaten für eine **neue** Pre-Reg bräuchten neue Läufe.

## Protokoll — mögliche DRAFT-Richtungen (nicht freigegeben)

1. Knotenbasierte Rettung (Rang/z-Score/Differenzen) — Risiko: erneute Blindheit bei Sync.  
2. **Kantenbasiert** `E_ij ∈ ℝ^k`, `κ_ij = f(E_ij)` — strukturell nächste Konsequenz.  
3. Hybrid: Kante primär, Knoten als Kovariate.

Fortsetzung nur nach expliziter Freigabe als **neuer DRAFT**.

---

## Tracking (Ruhezustand)

```text
Status: RUHEZUSTAND → AUFGELÖST (Pfad 1)
Phase: DRAFT 1 (E_ij Pre-Registration) — docs/KOPPLUNG_EIJ_v1_PREREG.md
HARKing-Sperre: strikt aktiv (state_screen / kopplung_full / reputation_i1 gesperrt)
Board: DRAFT offen · BINDEND / Adapter / I1 nur nach expliziter Freigabe
```

**Runner (Screening, historisch):** `scripts/run_emergence_state_screen.py`  
**Architektur-Referenz:** [`../ARCHITEKTUR_REFERENZ_EIJ.md`](../ARCHITEKTUR_REFERENZ_EIJ.md)  
**DRAFT 1:** [`../../../docs/KOPPLUNG_EIJ_v1_PREREG.md`](../../../docs/KOPPLUNG_EIJ_v1_PREREG.md)

### Methodische Abgrenzung: Dynamic Worker Spawning

Master-Worker / Fan-Out–Fan-In skaliert **Verarbeitungskapazität** (Throughput/Latency),
nicht die Topologie des gemessenen Zustandsraums `S_i`. Ephemere Sub-Agenten
(Chunk-Verarbeitung, deterministisch) sind verlängerte Werkbank des Primäragenten —
keine persistenten Schwarmknoten mit eigener Historie. BHO-Nullsumme (Δ=0,00 €)
sichert Konsistenz, erzeugt per Design keine partnerselektive Emergenz zwischen den
Primäragenten. Das Screening (`NONE_CLOSE` / Ausgang 3) bleibt davon unberührt.
