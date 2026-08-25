# Hebel 4 — Plastizität (Smart-Grid Meta-Stabilität, Pre-Registration)

**Status:** Pre-Registration — bestätigt 2026-08-17 (Scope / Null-0.4 / Verdict /
IUT). Spec: `docs/HEBEL4_PLASTIZITAET_SPEC.md`
**Datum:** 2026-08-17
**Freigabe:** Nach Hebel-1–3-Zwischenbilanz; Hebel 1 Follow-up abgeschlossen
(strukturell gelöst, funktional datenabhängig).
**Bezug:** `docs/SMART_GRID_PREREG.md`, `docs/SMART_GRID_ERGEBNIS.md`
(H1 falsifiziert — Plastizitäts-Hebel = Stubs).
**Charakter:** Vorab registriert. Keine Regel-Justage nach Daten-Sichtung.

---

## Bestätigungen (2026-08-17)

1. **Scope:** nur Class-B-Dispatch. Schattenpreise / Hebb / Aktive Inferenz =
   **bewusst ausgeklammert** (Folgestudie), nicht vergessen.
2. **Null:** inkl. passiver `PASSIVE_FLEX_FRACTION = 0.4` (Stub-Annahme).
   Dossier: Annahme + Caveat (Befund vs. Stub, nicht vs. reales Flex-Modell).
3. **Verdict:** nur Leitungsausfall-H1. Bewölkung/Spitzenlast deskriptiv.
   Dossier: Generalisierungs-Vorbehalt (dieser Störfall ≠ alle Störfälle).
4. **IUT:** H1 = H1a (ΔR_grid) **UND** H1b (ΔW_dyn) — gleiche Konjunktions-
   Struktur wie Smart Grid. Kein einseitiger Wilcoxon-only. Eingefroren.

---

## 0. Warum Hebel 4 jetzt

Die Effizienz-Hebel 1–3 lieferten keine klaren Produktions-Durchsatzgewinne.
Smart Grid zeigte die **fehlende Vorbedingung** für Meta-Stabilität: `_unit_act`
ist `pass`; Flexibilität (Batterie / EV / Wärmepumpe) reagiert nicht auf Defizite.
Hebel 4 testet, ob **Implementierung der Plastizitäts-Hebel** die vorregistrierte
H1-Konjunktion (R_grid↓ UND W_dyn≥0) auf dem einzigen phasenwirksamen Stress
(Leitungsausfall) bestätigt.

Dies ist **kein** Nachjustieren der Smart-Grid-Studie und **kein** HARKing:
dieselbe H1-Regel, neues Treatment (Dispatch live vs. Stub).

---

## 1. Hypothese

**H1 (wie SMART_GRID_PREREG):** Unter Leitungsausfall gilt die Konjunktion

- **H1a:** median(ΔR_grid) < 0 (einseitiger Wilcoxon, α=0.01)
- **H1b:** median(ΔW_dyn) ≥ 0 UND ≥ 7/10 Seeds mit ΔW_dyn ≥ 0

wobei ΔR_grid = R_stress − R_normal, ΔW_dyn = W_stress − W_normal.

**Hebel-4-Zusatzhypothese:** Mit aktivem Flexibilität-Dispatch (Treatment)
gilt H1 für Leitungsausfall; mit Stubs (Null) gilt H1 **nicht**
(Replikation des SMART_GRID_ERGEBNIS-Befunds).

---

## 2. Nullmodell vs. Treatment

| Arm | `_unit_act` | Flex in Leistungsbilanz |
|---|---|---|
| **Null (Stubs)** | `pass` (Status quo) | wie heute: Class B trägt **passiv** `0.4 × power_capacity` bei, **unabhängig** vom Defizit |
| **Treatment** | Class-B-Dispatch live | Flexbeitrag reagiert auf Defizit-Signal (siehe Scope), bis Kapazitäts-/SoC-Grenzen |

**Wichtig (ehrlich vorab):** Im Null-Arm ist Flex bereits passiv in
`_compute_power_balance` enthalten. Treatment muss unter Stress **über** diesen
Baseline-Beitrag hinaus kompensieren, sonst kann H1b nicht besser werden als
im Stub-Lauf. Das ist Absicht — kein Nachjustieren der Null-Definition nach Datenblick.

### Scope dieser Runde (minimal, fixiert)

**In Scope (Treatment):**

1. **Flexibilität-Dispatch (Class B)** — notwendig und hinreichend für diese Pre-Reg:
   - `battery_storage`: Entladen bei Defizit (SoC-Modell, einfache Bilanz)
   - `ev_mobility`: Ladeverschiebung / Entladebeitrag bei Defizit
   - `heat_pump`: Drosselung (Lastreduktion) bei Defizit

**Out of Scope (bewusst ausgeklammert — Folgestudie, neue Pre-Reg; nicht vergessen):**

- Schattenpreis-getriggerte Kommunikation
- Aktive Inferenz / vorausschauende Reserve
- Hebb'sches Um-Routing
- Phasenwirksame Erweiterung von Bewölkung/Spitzenlast
  (Frequenz-/Leistungs-Rückkopplung auf Inverter-Phasen)

Begründung: SMART_GRID_ERGEBNIS — nur Leitungsausfall senkt R_grid; Bewölkung/
Spitzenlast können H1a strukturell nicht bestätigen. Diese Runde adressiert die
**W_dyn-Lücke** unter Leitungsausfall, nicht die Phasen-Lücke der anderen Stress-Typen.

---

## 3. Primärer Stress und Auswertungsumfang

| Stress | Rolle in Hebel 4 |
|---|---|
| **Leitungsausfall** | **Primär** — einziger Stress mit erwartbarem H1a; H1-Konjunktion entscheidet |
| Bewölkung | Deskriptiv (ΔW_dyn); H1a voraussichtlich NOT_CONFIRMED (ΔR≈0) — kein Scheitern der Pre-Reg |
| Spitzenlast | Deskriptiv (ΔW_dyn); analog |

**Entscheidungsregel (strikt):**

1. H0 bleibt Voraussetzung (bestehendes Gate; bei Fail → Design-Stopp, keine H1-Auswertung).
2. **WIRKSAM / H1 CONFIRMED:** Leitungsausfall Treatment: H1a UND H1b.
3. **NICHT_WIRKSAM / H1 NOT_CONFIRMED:** sonst (inkl. nur H1a oder nur H1b).
4. Null-Arm Leitungsausfall: erwartet H1 NOT_CONFIRMED (Replikation); Abweichung
   dokumentieren, nicht umdeuten.
5. Bewölkung/Spitzenlast: berichten, **nicht** in die Wirksamkeits-Entscheidung einbeziehen.
6. **Kein Nachjustieren** von α, Seed-Quoren, Flex-Baseline 0.4 oder Stress-Definitionen
   nach Datenblick.

Schwellen unverändert aus SMART_GRID_PREREG: α=0.01, H1b ≥7/10 Seeds,
+1-Korrektur p=(k+1)/(n+1).

---

## 4. Design / Laufplan

- 10 Seeds × Leitungsausfall × {Null, Treatment} = 20 Kernläufe
- Optional deskriptiv: 10 × 2 × {Bewölkung, Spitzenlast} unter Treatment
  (kein Einfluss auf Verdict)
- RNG-Trennung: pro Seed eigene Streams
  (`seed+1` Gen, `seed+5555` Last, `seed+7777` Jitter, `seed+999999` Stress-Onset
  ±30 sim-min). Keine byte-identischen Replikate (Hebel-3-Caveat vermieden).
- Metriken / Surrogate: wie SMART_GRID_PREREG (R_grid: Phasen-Offset-Shuffle;
  W_dyn: gepaarter Wilcoxon; λ≡0)

---

## 5. Methodische Caveats (im Ergebnis-Dossier dokumentieren)

1. **Passive Flex im Null-Arm:** `PASSIVE_FLEX_FRACTION = 0.4` ist ein **Stub**,
   keine gemessene Größe. Annahme der Baseline + Caveat: POSITIVBEFUND gilt
   gegenüber diesem Stub, nicht gegenüber einem realistischen Flex-Modell.
2. **H1b operativ, nicht klassischer Non-Inferioritätstest** (wie Pre-Reg).
3. **IUT bleibt:** H1a ∧ H1b — nicht Wilcoxon-only auf ΔW_dyn.
4. **Generalisierung:** Verdict nur Leitungsausfall; Bewölkung/Spitzenlast
   deskriptiv. POSITIVBEFUND ≠ Übertragbarkeit auf alle Störfälle.
5. **Bewusst ausgeklammert:** Schattenpreise, Hebb, Aktive Inferenz,
   phasenwirksame Stressoren — Folgestudie, nicht vergessen.
6. **SoC-Modell vereinfacht:** keine Batteriealterung / Marktpreise;
   Dispatch schritt-synchron (nicht OODA-getaktet) — siehe Spec.

---

## 6. Sequenzierung

1. **Jetzt:** Pre-Reg fixieren (dieses Dokument). Bestätigung Scope + Null-Definition.
2. **Dann:** Treatment implementieren (`_unit_act` Class B + Leistungsbilanz-Anbindung).
3. **Dann:** Tests (Dispatch reagiert auf Defizit; Null bleibt pass).
4. **Dann:** Studie (Kern: Leitungsausfall Null vs. Treatment).
5. **Dann:** Ergebnis-Dossier strikt gegen diese Regel.
6. **Falls WIRKSAM:** optional Folgestudie Schattenpreise / phasenwirksame Stressoren.
7. **Falls NICHT_WIRKSAM:** akzeptieren; Diagnose (Kapazität zu klein? SoC? Timing?) —
   keine Schwellenänderung.

---

## 7. Bestätigungen — erledigt

Alle drei Bestätigungen + IUT-Prüfung: siehe Block „Bestätigungen (2026-08-17)“
oben und `docs/HEBEL4_PLASTIZITAET_SPEC.md`.

Nächster Schritt: Implementierung laut Spec.
