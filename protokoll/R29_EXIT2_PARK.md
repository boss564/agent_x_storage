R29 Exit-2 Park (Option A)

Diese Diffs sind der Exit-Semantik-Anteil des ehemaligen WT-WIP,
bewusst AUS Commit 1 (reiner Neu8-Format-Flip).

Inhalt:
- R29_EXIT2_PARK_einwurf.diff  — exit_aus_zeilen VERWERFEN→rc=2, _flag_wert, strom_ohne_wert/…
- R29_EXIT2_PARK_vertrag.diff  — projection_mapping, flag_wert, _kommentar, …

Anwenden spaeter (eigenes Gate / Commit Exit-2 + test_projektion-Update):
  # NICHT blind auf aktuellen Baum — Basis war Pre-Reduktion-WIP.
  # Besser: aus diesen Diffs die Exit-Hunks erneut auf HEAD+Neu8 portieren.

Gemessen: ohne diese Hunks bleibt test_projektion 5/5 gruen auf R+Neu8.

