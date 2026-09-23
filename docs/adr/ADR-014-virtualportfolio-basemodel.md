# ADR 14: VirtualPortfolio bleibt BaseModel mit Methoden

**Datum:** 2026-09-23
**Status:** akzeptiert
**Bezug:** ADR 12 (Modellbasen), ADR 13 (Telemetrie-Vertrag), F2 in
`docs/SHADOW_ENGINE_FOLLOWUPS.md`

---

## Kontext

F2-Regel: „Validierung an der Grenze, Verhalten im Kern."

Ist: `VirtualPortfolio` ist Pydantic-`BaseModel`, trägt Methoden
(`apply_fill`, `update_peak_equity`, `snapshot`), wird pro Fill mutiert.
Das sieht aus wie ein Verstoß gegen die F2-Kern-Regel (Verhalten gehört
nicht in Grenz-DTOs) und würde ohne Eintrag in drei Monaten als
Refactoring-„Fund" wieder auftauchen.

## Entscheidung

Bewusste Ausnahme von der strengen Lesart „BaseModel = nur Validierung".
Begründung:

1. `validate_assignment` ist aus (Pydantic-v2-Default) → Validierungskosten
   entstehen nur bei Konstruktion, nicht pro Fill-Mutation.
2. Schema-Garantie liegt am Seam: Grenzüberschreitungen fahren als frozen
   DTOs (`FillResult`, `TelemetryRecord`, `ExecutionReport`,
   `PortfolioSnapshot` / `PositionSnapshot`). Das Zustandsobjekt selbst
   ist kein Hub-DTO und kein Persistenz-Contract.
3. Migration auf Dataclass wäre reiner Churn: 67 grüne Tests bewegen
   kein Verhalten.

## Konsequenzen

- `validate_assignment` nicht einschalten ohne ADR-Änderung.
- Neue grenzüberschreitende Typen: frozen BaseModel (ADR 12).
- Portfolio niemals direkt serialisieren — immer über Snapshot-DTOs.
  (Ist-Schuld: `SQLiteShadowStorage.write_portfolio` liest noch Felder
  vom lebenden `VirtualPortfolio`; Folge-Ticket = Snapshot-DTO an der
  Spaltengrenze, kein Verhaltenswechsel im Kern.)

## Auffindbarkeit

Greppbar als `ADR 14` in dieser Datei und in `CLAUDE.md` (Key B2G
Decisions), analog zur Auffindbarkeits-Regel zu ADR 12/13.
