# Agent X B2G — Kämmerer-Pitch „Das System, das sich selbst prüft"

**Stand:** 0.24.0 · **Dauer:** ~4 Minuten · **5 Akte**
**Zielgruppe:** Kämmerer / Rechnungsprüfungsamt / Vergabestelle

> Kernbotschaft: Agent X ist nicht „compliance-fähig" — es belegt Compliance zur Laufzeit,
> und es findet seine eigenen Mängel, bevor der Prüfer sie findet.

---

## Akt 1 · Die Last (≈40 s)

*[Regie: Schwarze Folie, dann ein einzelner Aktenordner-Berg / Prüfbericht]*

Jede Abschlagszahlung, jeder Einbehalt, jede Rechnung wandert am Ende über Ihren Tisch — und trägt Ihre Unterschrift. VOB/B-Fristen, §17-Einbehalt, §13b-Umsatzsteuer, GoBD-Archivierung. Und über allem schwebt die eine Frage des Rechnungshofs: Ist das alles ordnungsgemäß — oder gibt es Bemerkungen?

Die Last ist nicht die Arbeit. Die Last ist die persönliche Verantwortung für die Entlastung.

---

## Akt 2 · Das Versprechen (≈45 s)

*[Regie: Architektur-Folie — 27 Wellen, GAEB→VOB/B→BHO→GoBD-Lebenszyklus]*

Agent X bildet den gesamten Beschaffungs-Lebenszyklus ab: vom GAEB-Eingang über die VOB/B-Ausführung mit Abschlägen und Mängelrüge bis zur BHO-konformen Kasse und dem GoBD-Archiv.

Aber der Punkt ist nicht die Abdeckung. Der Punkt ist die eine Invariante, unter der alles läuft: **BHO-Nullsumme**. Jeder Zahlungsvorgang erfüllt Einzahlungen = Auszahlungen + Einbehalt + Kassenbestand. Weicht das System auch nur einen Cent ab — größer 0,01 Euro — stoppt es jede weitere Zahlung.

Nicht der Mensch muss die Kasse prüfen. Die Kasse prüft sich selbst.

---

## Akt 3 · Der Live-Beweis (≈50 s)

*[Regie: Terminal — `make full-pitch` laufen lassen; parallel Overwatch-Dashboard]*

Ich behaupte das nicht — ich zeige es. Ein Befehl: `make full-pitch`. Vier Akte, etwa fünfzehn Sekunden, BHO-Delta am Ende: **0,00 Euro**.

Und weil ein Demo-Datensatz nichts beweist, haben wir den Stresstest **protokolliert**: eine Million Ereignisse durch die komplette Kette. **Null Verlust.** **54 Mikrosekunden** P99-Latenz. **9.554 echte L1-Anker** auf der Kette. Das ist kein Versprechen — das ist ein nachprüfbarer Lauf.

Die Erhaltungsinvariante geht exakt auf: `1.000.000 = 949.734` gecleart + `50.266` quarantined. Nichts verschwindet.

---

## Akt 4 · Der Punch — Das System prüft sich selbst (≈70 s)

*[Regie: `curl /compliance` live; dann die sechs Funde als Liste einblenden]*

Und jetzt der Punkt, der für Sie als Kämmerer entscheidend ist. Compliance ist bei Agent X kein Zertifikat an der Wand. Es ist ein Prüf-Gate, das zur Laufzeit läuft. Sehen Sie selbst:

`curl /compliance` — **gate: PASS**. 30 von 42 Prüfungen sind nicht behauptet, sondern belegt: 13 davon laufen in dem Moment, in dem Sie die URL aufrufen. 17 weitere sind durch den Testlauf von heute Morgen gedeckt — das Alter dieses Laufs steht im selben JSON. 11 sind Selbstauskünfte, die wir ehrlich als Vorbehalt kennzeichnen. Und **0** Prüfungen sind verletzt.

Verdict: **KONFORM — mit dokumentiertem Vorbehalt**. Nicht „voll konform" — das wäre eine leere Behauptung. Sondern: nachweisbar konform, dort wo es softwareseitig beweisbar ist.

Eine Zahl fehlt in dieser Aufzählung — und sie fehlt mit Absicht. Die 42. Prüfung ist das NFC-Auslesen des Personalausweises über das AusweisApp2-SDK. Das ist hardwaregebunden, softwareseitig nicht beweisbar — deshalb führen wir sie offen als nicht-verifizierte Ceiling, nicht als verifizierte Prüfung. Wir behaupten nichts, was wir nicht belegen können. Das ist kein Makel — das ist der Beweis der Prüfungssicherheit.

Und hier wird es für Sie interessant. Diese Proben haben bei uns selbst **sechs echte Mängel** gefunden — und wir haben sie behoben, bevor irgendein Auditor sie hätte finden können:

- eine hartkodierte HSM-PIN — jetzt erzwungen aus der Umgebung,
- fehlende Pflichtfelder im GAEB-X84 — jetzt vollständig,
- eine syntaktisch kaputte CI-Pipeline — jetzt fünf saubere Jobs,
- eine Gewährleistungsfrist von 5 statt der VOB/B-konformen 4 Jahre — korrigiert,
- eine BHO-Prüfung, die das Falsche asserted hat — invertiert,
- und eine Fehlerausgabe, die Meldungen abgeschnitten hat — jetzt vollständig.

Das ist kein Schönheitsfehler im Vortrag. Das ist der Beweis der Prüfungssicherheit: Ein System, das seine eigenen Fehler findet und schließt, bevor der Rechnungshof fragt, ist ein System, dem Sie die Entlastung anvertrauen können.

---

## Akt 5 · Der Weg (≈35 s)

*[Regie: Pilot-Roadmap-Folie; Call-to-Action]*

Sie müssen dafür nichts an Ihren Prozessen ändern. Wir starten im Schattenbetrieb: der VOB-Shadow-Contract läuft parallel zur heutigen Abwicklung, Sie beobachten und validieren, ohne Risiko.

Am Ende steht die RPA-Entlastungspipeline: acht Prüfschritte, GoBD bis PDF/A-3, mit einem klaren Verdikt — ENTLASTET, VORBEHALT oder VERWEIGERT. Transparent, nachvollziehbar, gerichtsfest.

Der nächste Schritt ist ein zweistündiger Sandbox-Termin bei Ihnen im Haus. Sie bringen Ihren Prüfungsleiter mit, wir laufen gemeinsam `make full-pitch`, und Sie prüfen selbst die BHO-Nullsumme und das Compliance-Gate. Kein Verkaufsgespräch — ein Nachweis unter Ihrer Aufsicht.

---

## Zahlenkarte (für den Sprecher)

| Metrik | Wert |
|--------|------|
| BHO-Nullsumme | Δ=0,00 € · Stopp bei >0,01 € |
| 1M-Tsunami | 0 Verlust · 54 µs P99 · 9.554 L1-Anker |
| Erhaltung | 1.000.000 = 949.734 + 50.266 |
| Compliance-Gate | PASS · 30/42 verified · 11 attested · 0 failed |
| Verdict | KONFORM_MIT_VORBEHALT (ehrlich benannt) |
| E2E | 25/25 · alle Wellen grün |
| full-pitch | 4 Akte · ~15 s · BHO Δ=0,00 € |
| Selbstfund | 6 echte Mängel entdeckt und behoben (0.24.0) |

---

## Regie-Hinweise

1. **Akt 4 ist der Differentiator** — dort nicht hetzen. Die sechs Funde langsam und konkret sprechen. Wenn die Zeit drückt, kürze Akt 2, niemals Akt 4.
2. **Ehrlichkeit als Stilmittel:** „KONFORM mit Vorbehalt" bewusst betonen — glaubwürdiger als „voll konform"; deckt sich mit der dokumentierten Hardware-Ceiling (1.1 NFC).
3. **Live-Demos absichern:** `make full-pitch` und `curl /compliance` vor dem Termin einmal frisch durchlaufen (SON-Cron hält den Report frisch). Fallback-Screenshot bereithalten.
4. **Zahlenkarte** getrennt ausdrucken — Zahlen frei sprechen, nicht ablesen.

---

*Pitch-Dauer: ca. 4 Minuten. Live-Demo: `make full-pitch` + `curl /compliance`. Fragen: nach Bedarf.*
*Technische Validierung (0.24.0): gate=PASS, verified=30/42, failed=0, E2E 25/25, Air-Layer 18/18, Checker 0 Abweichungen.*
