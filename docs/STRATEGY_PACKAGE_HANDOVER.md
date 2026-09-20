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

    KALIBRIERUNG: Produktion hat SIEBEN Formen (keyword, Assign, AnnAssign,
    arguments, Dict, IfExp, Call-delegierend). Eine naive "Elternknoten ist
    Assign/keyword"-Regel meldet sechs falsch-rote Waisen. Drei Fallstricke:
      - AnnAssign ist keine Assign (engine:61, 2 Stellen) und wird heute nur
        durch die Ausnahme NONE unsichtbar — gruen durch Ausnahme beweist nichts.
      - arguments (Default im Funktionskopf, models.py:698) produziert beim
        Weglassen des Arguments, ganz ohne Aufruf.
      - Call ist zwei Klassen: delegierender Callee (RejectReason via
        RiskDecision.reject) produziert; pruefender Callee (assert_safe)
        konsumiert. Kriterium ist der Callee-Rumpf, nicht der Elternknoten.
    FALSCH-GRUEN hat vier Gestalten: Vergleich, Docstring, pruefender Callee,
    Membership. Die vierte haengt AST-seitig unter Set/Tuple, nicht unter
    Compare (models.py:692) — "alles ausser Compare ist Produktion" winkt sie
    durch.
    Der Mutationsnachweis muss BEIDE Richtungen pruefen:
      Vergleich/Docstring/pruefender-Callee/Membership -> rot,
      alle sieben Produktionsformen                    -> gruen.
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
| Falsch-Grün | Wert nur in einem **Docstring** | **rot** *(instrumentabhängig)* |
| Falsch-Grün | Wert nur als Argument eines **prüfenden Callees** | **rot** |
| Falsch-Grün | Wert nur in einer **Membership** (`Set`/`Tuple`) | **rot** |
| Falsch-Rot | Wert in Form `keyword` | grün |
| Falsch-Rot | Wert in Form `Assign` | grün |
| Falsch-Rot | Wert in Form `AnnAssign` | grün |
| Falsch-Rot | Wert in Form `arguments` (Default im Funktionskopf) | grün |
| Falsch-Rot | Wert in Form `Dict` | grün |
| Falsch-Rot | Wert in Form `IfExp` | grün |
| Falsch-Rot | Wert in Form `Call` (delegierender Callee) | grün |

**Eine Zeile dieser Matrix ist instrumentabhängig.** Die Docstring-Fixture
(„Wert nur im Docstring → muss rot werden") ist unter AST **tautologisch grün**:
Der Syntaxbaum sieht Stringinhalte nicht. Gemessen sind es **9 Enum-Nennungen
in String-/Docstring-Konstanten** im Package:

```
models.py:1                        RejectReason.NONE
models.py:188                      OrderSide.BUY · OrderSide.SELL
models.py:241                      ExecutionMode.DISABLED
persistence.py:249                 RejectReason.NONE
shadow_execution_engine.py:387     RejectReason.NONE
shadow_execution_engine.py:438     RejectReason.NONE
test_persistence.py:111/211        RejectReason.NONE
```

Alle neun sind für den **Regex** sichtbar, für den **AST** unsichtbar. Der Fund
von damals verschwindet also nicht, weil er behoben wurde, sondern weil das
Instrument gewechselt hat.

**Die Fixture bleibt — aber mit Etikett:** *instrumentabhängig.* Sie ist Zeuge
gegen einen **Rückfall auf Textmessung**, nicht Zeuge für die Sehschärfe des
AST-Ankers. Ohne dieses Etikett zählt der Nachweis vier Falsch-Grün-Richtungen
und belegt drei.

**Der Glücksfall, präzise:** Von den sieben String-Nennungen betrifft **keine**
ein `OrderStatus`-Label. Der Befund hätte sich mit einer einzigen Zeile kippen
lassen — ein Docstring, der `CANCELLED` oder `EXPIRED` erwähnt. Dass keiner es
tut, ist der Grund, warum die Waisen überlebt haben; nicht die Güte des
Instruments.

### Was die Ein-Datei-Lesart verliert (Zeuge für die Reihenfolge)

**Zehn Produzentenstellen in zwei Dateien**, die der Anker heute nicht sieht:

| Wert | Form | Ort | Folge bei F2b-zuerst |
|---|---|---|---|
| `OrderStatus.PENDING` | `keyword` | `models.py:227` | **falsch-rote Waise** |
| `RejectReason.NONE` | `keyword` / `Assign` | `models.py:230`, `persistence.py:270` | heute durch Ausnahme gedeckt |
| `OrderSide.BUY` / `SELL` | `IfExp` / `keyword` | `models.py:196`, `:198`, `:570` | falsch-rot, sobald `OrderSide` aufgenommen wird |
| `ExecutionMode.DRY_RUN` | `keyword` / `arguments` | `models.py:228`, `:698` | ausgenommenes Konfigurations-Enum |

Drei Werte werden sofort falsch-rot, sobald F2b die Enums aufnimmt, **ohne
vorher die Zeugenquelle umzustellen**: `OrderStatus.PENDING`, `OrderSide.BUY`,
`OrderSide.SELL`.

**Die Reihenfolge-Entscheidung selbst ist damit zweitrangig** — F2b-zuerst beißt
mit drei Falsch-Rot, F2-zuerst verschiebt den Biss, ohne ihn zu vermeiden.
Entscheidend ist die **Binnenordnung von F2b**: Zeugenquelle **vor**
Enum-Aufnahme. Mit dieser Zahl ist das kein Argument mehr, sondern ein Beleg.

**Der Regressionswert ist real:** Der Regex wird nicht verschwinden — die
F2b-Demo will genau den Vergleich zeigen (ein Kommentar löscht eine Waise aus
der Liste), und ein Leser, der den Befund nachstellt, greift zum naheliegenden
Werkzeug. Die Fixture steht damit an derselben Stelle wie `--self-test` beim
Checker: ein Zeuge, der über den gezogenen Vorgänger wacht.

**Warum die sieben Formen nötig sind (AST-verifiziert):** Eine naive Regel
(„Elternknoten ist `Assign`/`keyword`") erwischt nur einen Teil und meldet
**sechs falsch-rote Waisen** — darunter vier der sechs `RejectReason`-Werte,
die real über `Call` bzw. `Dict`/`IfExp` produziert werden. Ein AST-Anker, der
so kalibriert ist, tauscht Falsch-Grün gegen Falsch-Rot — und die erste
Reaktion auf ein Falsch-Rot ist eine Ausnahmeliste, die den Wächter aufweicht.

**Drei Fallstricke, die die Matrix adressiert:**

- **`AnnAssign` ist keine `Assign`.** `reason: RejectReason = RejectReason.NONE`
  (`engine:61`, `:408`, 2 Stellen) — weder `Assign` noch `keyword`. Heute
  folgenlos, weil `NONE` auf der Ausnahmeliste steht: **Die Form ist
  vorhanden, aber durch die Ausnahme unsichtbar.** Grün durch Ausnahme beweist
  nichts.
- **`arguments` ist ein Produzent ohne Aufruf.** Ein Default im Funktionskopf
  (`def __init__(self, mode: ExecutionMode = ExecutionMode.DRY_RUN)`,
  `models.py:698`) landet auf dem Objekt, wenn der Aufrufer das Argument
  weglässt. Im Produktivcode trifft es heute nur ein ausgenommenes
  Konfigurations-Enum — die Form existiert aber auch an `OrderSide`
  (`test_engine.py:45`).
- **`Call` ist zwei Klassen.** `RiskDecision.reject(...)` **produziert** durch
  Delegation; `guard.assert_safe(...)` **prüft nur** — syntaktisch identisch.
  Wer `Call` pauschal als Produzent führt, holt die Falsch-Grün-Lücke über die
  Hintertür zurück. Kriterium ist der **Callee-Rumpf** (weist er den Wert zu
  oder gibt er ihn zurück?), nicht der Elternknoten.

**Und `Membership` heißt AST-seitig nicht `Compare`.** Der `PAPER_TRADING`-Fall
von ganz oben hat endlich seinen Namen:
`frozenset({ExecutionMode.DRY_RUN, ExecutionMode.PAPER_TRADING})`
(`models.py:692`) hängt unter `Set`, nicht unter `Compare` — `x in (a, b)` ist
zwar ein `Compare`, aber die Werte hängen am `Set`/`Tuple` darunter. Eine Regel
„alles außer `Compare` ist Produktion" winkt ihn durch: **dieselbe Lücke wie
beim Regex, nur mit Syntaxbaum.**

### Die Formen sind Testdaten, nicht das Kriterium

Die Formliste wuchs in vier Runden von 2 auf 11 Einträge — und **jede Fassung
sah vollständig aus.** Python hat mehr Ausdruckskontexte als das Modul heute
benutzt (`List`, `Starred`, `BoolOp`, Walrus, Comprehension, Lambda-Default,
`match`-Pattern, `setattr`-String, `**{...}`). Eine Liste, die mit dem Code
nachwachsen muss, sichert zu, dass sie die Formen *kennt*, und kann das nur für
die Vergangenheit belegen.

> **Deshalb steht am Anfang nicht die Frage „welche Elternknoten bedeuten
> Produktion?" (offene Menge), sondern: Erreicht der Wert ein Ziel?**

Die **Konsum**gestalten sind die geschlossene Menge — sie teilen eine
Eigenschaft (*der Wert wird gelesen und verworfen*):

| Konsumgestalt | Beispiel |
|---|---|
| Vergleich | `if status == OrderStatus.CANCELLED:` |
| Membership | `frozenset({ExecutionMode.DRY_RUN, …})` |
| prüfender Callee | `guard.assert_safe(ExecutionMode.PAPER_TRADING)` |
| Docstring | `"""siehe OrderStatus.EXPIRED"""` |

**Regel:** *Alles, was nicht nachweislich konsumiert wird, gilt als
Produktion.* Dann irrt der Anker im Zweifel nach **Falsch-Rot** — die Richtung,
die untersucht wird statt durchgewinkt.

**Die Formen bleiben — als Testdaten für diese Regel, nicht als Kriterium.**
Als Kriterium erben sie das Nachwachsen; als Testdaten belegen sie eine Regel,
die ohne sie auskommt.

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
