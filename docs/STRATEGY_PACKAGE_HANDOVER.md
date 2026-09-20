# Übergabe an das Strategy-Package — Konvention, Standard, Kontext

**Zweck:** Dieses Dokument ist der **erste Commit** des Strategy-Packages, nicht
Code. Es trägt die Konventionen mit, die im Agent-X-Repo entstanden sind, aber
dort *nicht* gelten. Ein Standard, der im Nachbar-Repo bleibt, wirkt an genau
dem Ort nicht, an dem der nächste Record geboren wird.

**Herkunft:** Erarbeitet im F1-Zyklus der Shadow Execution Engine (2026-09-20),
`agent_x_storage/docs/SHADOW_ENGINE_FOLLOWUPS.md`.

**Was dieses Dokument ist:** eine Übernahme, kein Entwurf. Die Regeln sind
nicht neu zu verhandeln; sie wurden in der Praxis geboren und haben sich an
Tag 1 bezahlt. Abweichungen brauchen eine Begründung, keine Mehrheit.

---

## 1. ADR 12 (Übernahme) — Modellbasis

> **Neue Records/Modelle im Strategy-Package sind grundsätzlich Pydantic
> `BaseModel`, Dataclass nur mit begründeter Ausnahme.**
>
> **Referenzimplementierung:** `PaperOrder` (`order_execution_engine/models.py`).
> **Begründung** (gehört als Docstring an die Klassen, nicht in diese Regel):
> der Drift-Befund — zwei Modellbasen koexistieren, neue Klassen werden im Stil
> ihrer Nachbarschaft geschrieben, nicht im Stil des Systems.
> **Review-Flag:** jeder Dataclass-Neuzugang.

Zwei Träger, zwei Rollen, kein duplizierter Text:

| Ort | Rolle | Inhalt |
|---|---|---|
| Diese Datei / CLAUDE.md | operative Stelle | die Regel, imperativ |
| Der `models.py`-Docstring | Entdeckungsstelle | die Begründung |

Die Trennung ist Absicht: Eine Regel ohne Begründung überlebt den ersten
Deadline-Konflikt nicht; eine Begründung ohne Regel wird nicht gelesen.

---

## 2. Der Scheinschutz-Standard — vier Schichten

**Die Frage ist nie „ist es vorhanden?", sondern „kann es feuern, und beweist
ein Test das?"**

| Angewandt auf | Zeuge |
|---|---|
| Risk-Check | Anker-Test: zweiter Fill kippt die Position über das Limit → Reject |
| Test | Sensitivitäts-Kriterium: der Test **muss rot werden**, wenn der Mutant eingebaut wird |
| Refactoring / Seam | Coverage auf den neuen Zeilen: der Seam wird tatsächlich durchlaufen |
| **Prädikat** | **Erreichbarkeits-Nachweis: der Wahr-Zweig muss erzeugbar sein.** |

### Die Namen der Krankheit, an denen sie im Review aufrufbar ist

- **Scheinschutz** — ein Check, der wie eine Zusicherung aussieht und nie
  feuern kann. (Erste drei Schichten.)
- **Phantom-Label** — ein Enum-Wert ohne Produzenten. Ein Leser, der das Enum
  als Dokumentation liest, muss ihn für möglich halten; er kommt nie.
  Der schlimmste Fall heißt wie sein Gegenteil (`SAFETY_GUARD`).

  **Präzise Fassung:** Die Fehlerklasse ist nicht „Wert ohne Produzent",
  sondern *ein Wert, den kein Pfad hervorbringen kann, obwohl das Enum ihn als
  möglich ausweist*. Das gilt für **Ausgangs-Enums** (`RejectReason`,
  `OrderStatus`) — dort ist der Produzent der richtige Zeuge. Für
  **Eingangs-Enums** (z. B. `Direction`) lautet die gleichwertige Frage: *hat
  jeder Wert eine sichtbare Behandlung?* Für **Konfigurations-Enums** (z. B.
  `ExecutionMode`) ist Produktion irrelevant.

  **Deshalb wird pro Enum die Richtung deklariert, nicht eine Liste geführt:**
  Ausgang → Produzenten-Prüfung · Eingang → Behandlungs-Prüfung ·
  Konfiguration → ausgenommen mit Begründung. Sonst meldet der Anker falsch
  positiv: `Direction.DOWN` hat null Code-Produzenten, ist aber im `else`-Zweig
  behandelt — ein produzentenbasierter Anker sähe eine Waise, wo keine ist.

  **Und die Richtung allein genügt nicht:** Das Instrument muss Produktion von
  Erwähnung unterscheiden. `re.findall(r"Enum\.[A-Z_]+", src)` zählt
  **Vorkommen** — ein reiner Vergleich (`if status == Enum.CANCELLED:`)
  erscheint darin als Produzent und lässt ein Phantom-Label grün durch. Der
  dauerhafte Anker liest das **Package** und erkennt als Produzent nur
  Zuweisung, Default oder Konstruktion — nie einen Vergleich. Bewiesen wird das
  durch einen Mutationsnachweis: ein Fixture-Wert, der **nur im Vergleich**
  vorkommt, muss den Anker rot machen.
- **Toter Wahr-Zweig** — ein Prädikat, dessen `True` unerreichbar ist
  (vierte Schicht).
- **Schweigepflicht** — ein Validator, der weitergestellt wurde, bis die Tests
  grün waren. Migriert nicht die Modelle, sondern nur die Stille.
- **Mechanisch richtig, semantisch falsch** — ein Zeuge, der eine Falle korrekt
  als erwartetes Verhalten kanonisiert. Er beantwortet „feuert der Check?" mit
  ja, ohne „sollte er?" zu fragen.

### Zwei Regeln, die aus dem Standard folgen

1. **Kein Label ohne Produzenten.** Jeder Enum-Wert hat einen lebenden
   Erzeuger. Prüfbar als Meta-Anker (siehe unten), nicht als Absichtserklärung.
2. **Tote Maschinerie neben einem gelöschten Label ist derselbe Befund einen
   Meter weiter.** Wird ein Wert entfernt, ist zu prüfen, was ihn einst
   plausibel machte.

---

## 3. Der Meta-Anker (Vorlage, mitzunehmen)

Der Wächter gegen **Phantom-Labels** — nicht ein Fehler, sondern eine
Fehlerklasse: Behauptungen, die aussehen wie Zusicherungen. Er fängt beide
Richtungen und ist als Test zu übernehmen:

**Bevor die Vorlage kopiert wird — die Richtung deklarieren.** Ein Anker, der
über *alle* Enums läuft, meldet falsch positiv: `Direction.DOWN` hat im
Engine-Code null explizite Produzenten (nur ein `else`-Zweig), und
`ExecutionMode.PAPER_TRADING` steht nur in einer Allowlist. Die Vorlage unten
prüft **Ausgangs-Enums**. Für Eingangs-Enums lautet die gleichwertige Frage
*hat jeder Wert eine sichtbare Behandlung?*; Konfigurations-Enums sind
ausgenommen, mit Begründung.

```python
def test_meta_every_reason_has_a_producer() -> None:
    """Jeder Wert eines AUSGANGS-Enums hat einen lebenden Produzenten.

    Ein Wert ohne Produzenten ist Scheinschutz im Enum — jeder Diagnostics-
    Konsument muss ihn fuer moeglich halten, er kommt nie.

    Gilt fuer Ausgangs-Enums (RejectReason, OrderStatus). Eingangs-Enums
    (Direction) brauchen eine Behandlungs-Pruefung, Konfigurations-Enums
    (ExecutionMode) sind mit Begruendung ausgenommen.

    WARNUNG — die Regex-Variante unten ist die SCHWACHE Form: Sie zaehlt
    Vorkommen, nicht Produktion, und liest eine Datei. Ein reiner Konsument
    (`if status == Enum.CANCELLED:`) macht ein Phantom-Label gruen; ein
    Docstring genuegt ebenfalls. Fuer den dauerhaften Waechter: Package lesen,
    Code statt Text (AST), und Produzent von Erwaehnung unterscheiden.

    KALIBRIERUNG: Produktion hat fuenf Formen (keyword, Assign, Dict, IfExp,
    Call). Eine naive "Elternknoten ist Assign/keyword"-Regel meldet sechs
    falsch-rote Waisen. Der Mutationsnachweis muss BEIDE Richtungen pruefen:
    Vergleich/Docstring -> rot, alle fuenf Formen -> gruen.
    """
    import re
    from pathlib import Path

    src = Path("<modul-mit-den-produzenten>.py").read_text()
    produced = set(re.findall(r"<EnumName>\.([A-Z_]+)", src))
    allowed_without_producer = {"NONE"}  # Marker, kein Reject

    orphans = [r.name for r in <EnumName>
               if r.name not in produced and r.name not in allowed_without_producer]
    assert not orphans, (
        f"Werte ohne Produzenten: {orphans}. Entweder Produzent herstellen "
        f"oder Wert entfernen."
    )
```

**Die Vorlage trägt ihre eigene Grenze mit.** Sie ist als Startpunkt
brauchbar — für `RejectReason`/`OrderStatus` bei Ein-Datei-Produktion —, aber
ihre Sehschärfe ist ungeprüft:

| Schwachstelle | Beleg | Folge |
|---|---|---|
| Zählt **Vorkommen**, nicht Produktion | `if status == Enum.CANCELLED:` → Waise verschwindet | **Falsch-Grün** |
| **Ein Docstring genügt** | `"""siehe Enum.EXPIRED"""` → Waise verschwindet, ohne Code | **Falsch-Grün ohne Codeänderung** |
| Liest **eine** Datei | `RejectReason.NONE` wird in `persistence.py:270` produziert | Falsch-Rot bei Package-Verteilung |
| **Kein Mutationsnachweis** | niemand hat ihn rot gesehen | Reichweite deklariert, Sehschärfe unbelegt |

> **Ein Wächter, der durchwinkt, ist schlimmer als einer, der falsch
> anschlägt: Falsch-Rot wird untersucht, Falsch-Grün nie.**

Die Docstring-Zeile ist die unangenehmste: `re.findall` liest die Datei als
**Text**, nicht als Programm. Wer in der Engine-Datei notiert, *warum* ein Wert
keinen Produzenten hat, nimmt dem Anker den Fund — **eine Lücke, die sich beim
Dokumentieren schließt, ohne dass sich etwas geändert hat.** Der dauerhafte
Anker liest deshalb Code (AST), nicht Text.

**Schrittordnung (Abhängigkeit, nicht Empfehlung):** Erst die Zeugenquelle auf
Package umstellen, dann ein Enum aufnehmen. Für `OrderStatus.PENDING` — dessen
einziger Produzent in `models.py:227` steht — erzeugt die Ein-Datei-Lesart sonst
ein Falsch-Rot, das kein Fund ist.

### Der Mutationsnachweis braucht beide Richtungen

Ein Nachweis, der nur die Falsch-Grün-Richtung prüft („Vergleich darf nicht als
Produzent zählen"), lässt die Falsch-Rot-Richtung genau so unbelegt wie der
heutige Anker seine Sehschärfe — **dieselbe Lücke, eine Ebene höher.**
Gefordert ist beides:

| Richtung | Fixture | Erwartung |
|---|---|---|
| Falsch-Grün | Wert nur in einem **Vergleich** | **rot** |
| Falsch-Grün | Wert nur in einem **Docstring** | **rot** |
| Falsch-Rot | Wert in Form `keyword` | grün |
| Falsch-Rot | Wert in Form `Assign` | grün |
| Falsch-Rot | Wert in Form `Dict` | grün |
| Falsch-Rot | Wert in Form `IfExp` | grün |
| Falsch-Rot | Wert in Form `Call` | grün |

**Warum die fünf Formen nötig sind (AST-verifiziert):** Eine naive Regel
(„Elternknoten ist `Assign`/`keyword`") erwischt nur einen Teil und meldet
**sechs falsch-rote Waisen** — darunter vier der sechs `RejectReason`-Werte,
die real über `Call` bzw. `Dict`/`IfExp` produziert werden. Ein AST-Anker, der
so kalibriert ist, tauscht Falsch-Grün gegen Falsch-Rot — und die erste
Reaktion auf ein Falsch-Rot ist eine Ausnahmeliste, die den Wächter aufweicht.

**Er hat sich an Tag 1 bezahlt:** Er fand bei seinem ersten Lauf zwei Waisen
(`EXPIRED`, `SAFETY_GUARD`), die auf keiner Liste standen, plus die verwaiste
Maschinerie dahinter (`is_expired()`, ein Prädikat mit totem Wahr-Zweig).

---

## 4. Was hierher umzieht

**`max_order_size_shares`** — derzeit ein Feld in `RiskConfig`
(`order_execution_engine/models.py`). Es ist **Strategie-Konfiguration in
Engine-Kleidung**: Seit der Sizing-Schnittstelle (F1/VM4) hat es keine
Schranken-Semantik mehr, es ist nur die Größe, die der Default-Adapter ordert
(ein Platzhalter für genau die Conviction-Logik, die hier entsteht).

Die Engine-Obergrenze ist `per_order_cap_shares` — engine-seitig geklemmt, mit
Config-Invariante `per_order_cap_shares <= max_position_size_usdc`.

**Der Umzug erfolgt in dem Commit, der die Conviction-Logik einführt.** Dann
reisen Feld und Konvention im selben Schritt.

---

## 5. Der Merksatz

> **Verifizieren, korrigieren, stehen lassen.**
>
> Der Zyklus, aus dem dieser Standard stammt, begann mit einer falschen
> Alarmmeldung und endete mit einer Engine, die nicht mehr lügen kann, ohne
> dass es jemand merkt. Der wertvollste Ertrag waren nicht die gehärteten
> Checks, sondern der Präzedenzfall dafür, wie mit Unsicherheit umgegangen
> wird.
>
> Zeugen werden **gelöscht, nicht umgeschrieben**, wenn ihr Gegenstand stirbt.
> Löschen heißt „existiert nicht", nicht „darf nie existieren" — ein Wert darf
> zurückkehren, dann mit Produzent *und* Zeuge.

---

## 6. Herkunft der Entscheidungen (für Rückfragen)

| Entscheidung | Begründung | Ort |
|---|---|---|
| Pydantic für neue Modelle | Drift-Befund, zwei Modellbasen | dieses Dok., §1 |
| Kein Label ohne Produzenten | Phantom-Label als Scheinschutz | dieses Dok., §2 |
| Vier-Schichten-Tabelle | Prädikat mit totem Wahr-Zweig | dieses Dok., §2 |
| `max_order_size_shares` gehört hierher | Strategie-Konfiguration, keine Schranke | dieses Dok., §4 |
| Sizing über injizierte `SizeFn` | Engine bleibt ohne Strategie lauffähig | `SHADOW_ENGINE_FOLLOWUPS.md`, F1c |

**Schnittstelle (unverändert, Engine-seitig definiert):**

```python
SizeFn = Callable[[SignalPayload, PortfolioState], Decimal]

def sizing(signal, portfolio_state) -> desired_size
```

Die Engine injiziert sie (`ShadowExecutionEngine(..., size_fn=...)`), klemmt
das Ergebnis auf `per_order_cap_shares` und protokolliert beide Größen
(`requested_size` = Wunsch, `executed_size` = geklemmt). Hier entsteht die
echte Conviction-Logik gegen dieselbe Schnittstelle — ohne Engine-Änderung.
