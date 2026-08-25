# Hebel-Serie Effizienz — Abschluss-Dokument

**Status:** Serie abgeschlossen — vier Hebel ausgewertet, Gesamtaussage diagnostisch
**Datum:** 2026-08-17
**Zwischenbilanz:** `docs/HEBEL_EFFIZIENZ_ZWISCHENBILANZ.md`

**Einzel-Dossiers:**

- `docs/HEBEL1_EVALUATOR_REDUNDANZ_PREREG.md` (+ Follow-up-Tests)
- `docs/HEBEL1_DIFFERENZIERUNG_PREREG.md` / `docs/HEBEL1_DIFFERENZIERUNG_ERGEBNIS.md`
- `docs/HEBEL2_ZUWEISUNG_PREREG.md` / `docs/HEBEL2_ZUWEISUNG_ERGEBNIS.md`
- `docs/HEBEL3_TIER2A_EFFIZIENZ_PREREG.md` / `docs/HEBEL3_TIER2A_EFFIZIENZ_ERGEBNIS.md`
- `docs/HEBEL4_PLASTIZITAET_PREREG.md` / `docs/HEBEL4_PLASTIZITAET_SPEC.md` /
  `docs/HEBEL4_PLASTIZITAET_ERGEBNIS.md`

---

## 1. Die vier Hebel im Überblick

| Hebel | Frage | Maßnahme | Ergebnis | Charakter |
|---|---|---|---|---|
| **1 — Redundanz** | Sind neun identische Evaluatoren Verifikation oder Replikation? | Regeln differenzieren (verschiedene Regeln, gleiche Felder) | **NICHT_WIRKSAM** auf realen Daten | strukturell gelöst, funktional datenabhängig |
| **2 — Zuweisung** | Ist Least-Loaded besser als `hash % 9`? | Least-Loaded-Zuweisung | **POSITIVBEFUND** (Sim) | validierend, nicht therapeutisch |
| **3 — TIER-2a** | Wirkt Rückstau auf der Effizienz-Achse? | Neu auf Durchsatz messen | **INCONCLUSIVE** | kein klarer Befund |
| **4 — Plastizität** | Hält aktiver Class-B-Dispatch W_dyn stabil? | Wasserfall Batterie → EV → Wärmepumpe | **NICHT_WIRKSAM** | aktiver Dispatch < passiver Stub |

## 2. Das übergreifende Muster: diagnostisch, nicht therapeutisch

Die zentrale und ehrliche Gesamtaussage der Serie:

> **Die vier Hebel haben überwiegend diagnostisch gewirkt. Sie haben Probleme
> aufgezeigt und Annahmen validiert, aber keine unmittelbaren therapeutischen
> Produktions-Verbesserungen geliefert.**

Im Einzelnen:

- **Hebel 1** hat gezeigt, dass die neun Evaluatoren Replikation, nicht Verifikation
  sind (tote Strictness, identische Regel). Die Differenzierung ist strukturell
  korrekt, aber auf der realen Datenverteilung funktional wirkungslos, weil nur
  das Balance-Gate ausgereizt wird.
- **Hebel 2** hat eine echte Verbesserung gezeigt (Last-Balancierung), aber die
  Produktion nutzt Least-Loaded bereits. Der Befund validiert den Status quo,
  statt ihn zu ändern.
- **Hebel 3** hat keinen klaren Befund geliefert (INCONCLUSIVE).
- **Hebel 4** hat gezeigt, dass die aktive Plastizität unter dem aktuellen Modell
  schlechter ist als der passive Stub (SoC-Drain vs. unerschöpflicher Stub).

Das ist **kein Scheitern** der Serie. Es ist eine wertvolle diagnostische Erkenntnis:
Sie verhindert, dass ineffektive Mechanismen als Verbesserungen verkauft werden, und
sie zeigt präzise, wo die tatsächlichen Engpässe liegen (Datenverteilung, SoC-Modell,
bereits implementierte Zuweisung).

## 3. Methodische Lehren der Serie

Die vier Hebel haben eine konsistente Methodik etabliert, die über die Serie
hinaus Bestand hat:

1. **Pre-Reg-Disziplin:** Alle vier Hebel wurden vorab registriert, mit fixierten
   Schwellen, die nach dem Datenblick NICHT nachjustiert wurden. Das schützt vor
   HARKing und macht Negativbefunde belastbar.
2. **Die Messachse ist entscheidend:** Hebel 3 wurde zunächst auf der falschen
   Achse gemessen (Phasenkohärenz statt Durchsatz) und musste neu ausgewertet
   werden. Die Wahl der Messachse bestimmt, ob ein Befund aussagekräftig ist.
3. **Faire Nullmodelle:** Hebel 4 hat den aktiven Dispatch den passiven Stub
   *ersetzen* lassen (kein `max`), um einen fairen Vergleich zu gewährleisten.
   Ein unfaires Nullmodell hätte den Befund uninterpretierbar gemacht.
4. **Die Datenverteilung bestimmt die funktionale Wirksamkeit:** Hebel 1 hat
   gezeigt, dass ein strukturell korrekter Hebel funktional wirkungslos sein
   kann, wenn die Datenverteilung ihn nicht ausreizt. Ein Hebel ist nur so gut
   wie die Daten, auf denen er operiert.
5. **Negativbefunde sind wertvoll:** Drei der vier Hebel endeten in NICHT_WIRKSAM
   oder INCONCLUSIVE. Das sind ehrliche Befunde, die vor Fehlinvestitionen schützen.

## 4. Offene Fragen und Folgestudien

Zwei Fragen sind offen und gehören in **neue Pre-Regs**, nicht in Nachjustierungen
der bestehenden Hebel:

1. **SoC-Nachfüllung (Folgestudie zu Hebel 4):** Der aktive Dispatch ist im
   aktuellen Modell durch die einseitig leerende SoC benachteiligt. Eine
   SoC-Nachfüllung (aus erneuerbarer Erzeugung oder dem Netz) wäre die
   naheliegendste Folge-Untersuchung. **Dies erfordert eine neue Pre-Reg**, da
   es das Modell von Hebel 4 ändert und keine Nachjustierung der bestehenden
   Schwellen sein darf.
2. **Datenverteilung (Folgestudie zu Hebel 1):** Die Differenzierung ist auf der
   realen Datenverteilung wirkungslos, weil nur das Balance-Gate ausgereizt wird.
   Die Frage ist, ob der Provider OFFERs mit ausgeglichener Bilanz, aber suspekten
   Einzelwerten (hohe Steuerrate, etc.) erzeugen sollte. **Dies erfordert einen
   Realismus-Check** (kommen solche OFFERs in echten B2G-Traces vor?), um HARKing
   zu vermeiden. Eine Pre-Reg ohne Realismus-Check würde die Datenverteilung so
   konstruieren, dass die Messung grün wird.

Beide Folgestudien sind **optional** und nicht Teil der abgeschlossenen Serie.

## 5. Gesamtaussage

Die Hebel-Serie Effizienz ist abgeschlossen. Sie hat vier Hypothesen vorab
registriert, methodisch sauber ausgewertet und ehrlich berichtet. Das Ergebnis
ist überwiegend diagnostisch: Die Serie hat gezeigt, dass die naheliegenden
Effizienz-Hebel (Differenzierung, Zuweisung, Rückstau, Plastizität) unter den
aktuellen Modellen und Datenverteilungen keine unmittelbaren Produktions-
Verbesserungen liefern. Das ist eine wertvolle Erkenntnis, die den Blick auf die
tatsächlichen Engpässe lenkt (Datenverteilung, SoC-Modell, bereits implementierte
Optimierungen) und vor Fehlinvestitionen in ineffektive Mechanismen schützt.

Die etablierte Methodik (Pre-Reg-Disziplin, Messachsen-Wahl, faire Nullmodelle,
Datenverteilungs-Bewusstsein) bleibt als wiederverwendbares Fundament für künftige
Effizienz-Untersuchungen bestehen.
