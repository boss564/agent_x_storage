# RaaS — Supranode Facade v0 (Ingress/Egress)

**Status:** ARCHITECTURE v0 (2026-08-27) · additiv · Charter Option 1  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false`  
**Basis:** `docs/RaaS_P9_MAPPING_v1.md` · `docs/RaaS_P9_MAPPING_v2.md` · `docs/RaaS_HYBRID_KI_ROADMAP_v0.md`  
**Pilot:** `prototypes/raas_hybrid_shell/` (`TrustedCoreGateway`)

Ziel: Nach außen **eine** gehärtete Entität (Agent-X-Schwarm). Innen bleiben die
**v1-Rollen** — kein Remap, kein neues `agents/p1…`.

---

## 1. Was vom Roh-Entwurf bleibt / was nicht

| Roh | Hier |
|-----|------|
| P1 = einzige Außen-Eingabe, P9 = einzige Außen-Ausgabe | **behalten** als Facade |
| Interner Bus; P2–P8 ohne Extern-Kontakt | **behalten** als Intent |
| P2 = Red-Orchestrator, P5 = MEV-Bot `execute_*`, P8 = Oracle-Manipulator | **abgelehnt** — v1-Funktionen |
| 9 neue Microservices sofort | **abgelehnt** als erster Schritt |
| Topics `internal.attack.*.execute` | **`…run_scenario` / `…result`** |

P-Funktionen (v1): P₁ Parser · P₂ Latenz · P₃ Pressure · P₄ MEV-Szenario ·
P₅ Oracle · P₆ Z3 · P₇ Shock · P₈ Kaskade · P₉ Anchor/Envelope.

---

## 2. Zwei Ebenen (Facade)

```text
Externe Welt / Untrusted Shell
        │
        ▼
   INGRESS (P₁-Facade)     — Charter-Vorfilter, übersetzt → Kern-Tools
        │
        ▼
   TrustedCoreGateway      — bestehender Pilot (store/runner/gate/exporter)
   (+ später: interner Bus mit v1-Rollen als Worker)
        │
        ▼
   EGRESS (P₉-Facade)      — Envelope + WORM; HSM-Signatur Intent
        │
        ▼
   external.response / SafetyEnvelope
```

Heute ist Ingress+Egress+Kern **eine Klasse** (`TrustedCoreGateway`).
Die Facade-Trennung ist die **nächste Schicht**, nicht neun parallele Remaps.

---

## 3. Topic-Skizze (Intent — an v1 gebunden)

Nur wenn ein Bus kommt (NATS existiert im Gesamtstack / Surface; **nicht** in
`podman-compose.p9.yml` für RaaS). Topics spiegeln v1, nicht den Roh-Remap:

| Rolle | Abonniert (Intent) | Publiziert (Intent) |
|-------|--------------------|---------------------|
| Ingress P₁ | `external.request` | `internal.task.created` |
| P₂ Latenz | `internal.sim.latency.request` | `internal.sim.latency.result` |
| P₃ Pressure | `internal.sim.pressure.request` | `internal.sim.pressure.result` |
| P₄ MEV-Szenario | `internal.scenario.mev.request` | `internal.scenario.mev.result` |
| P₅ Oracle | `internal.scenario.oracle.request` | `internal.scenario.oracle.result` |
| P₆ Z3 | `internal.verify.request` | `internal.verify.result` · `internal.patch.candidate` |
| P₇ Shock | `internal.scenario.shock.request` | `internal.scenario.shock.result` |
| P₈ Kaskade | `internal.scenario.cascade.request` | `internal.scenario.cascade.result` |
| Egress P₉ | `internal.final.result` | `external.response` |

Red-Orchestrierung (v2 Overlay) = **Shell/Plugin außerhalb**, nicht Topic-Umbenennung von P₂.

---

## 4. Nachrichten-Minimum

```json
{
  "header": {
    "message_id": "…",
    "correlation_id": "…",
    "source": "ingress|core|egress",
    "scope": "DEFENSIVE_CAUSAL_GROUNDING",
    "live_execution": false,
    "not_investment_advice": true
  },
  "body": { }
}
```

Signatur/HMAC und Topic-ACL = Intent (D3-Verwandtschaft). SoftHSM/Bunker für
Egress-Signatur = bestehendes Muster (`agents_b2g/bunker/`, Mock-HSM), nicht neu erfinden.

---

## 5. End-to-End (heutiger Ist vs. Ziel)

| Schritt | Heute (Pilot) | Ziel-Facade |
|---------|---------------|-------------|
| Anfrage | `propose()` → Gateway | `external.request` → Ingress |
| Kern | `evaluate_shell_proposal` | dieselben Tools (+ optional Bus-Worker) |
| Antwort | `SafetyEnvelope` im Prozess | Egress publiziert `external.response` |
| Archiv | `audit.worm.jsonl` | P₉ WORM + optionale HSM-Signatur |

Pilot-Test bleibt gültig: Facade muss `HYBRID_SHELL_PASS`-Semantik erhalten
(mild/aggressive Slippage, keine `execute_*`-Gegenmaßnahmen).

---

## 6. Implementierungsstand

| Schicht | Stand |
|---------|--------|
| Dokument | ✅ `docs/RaaS_SUPRANODE_v0.md` |
| Dünne Facade | ✅ `prototypes/raas_hybrid_shell/supranode_facade.py` |
| Smoke | ✅ `scripts/test_raas_supranode.py` · `make raas-supranode` |
| 9 Microservices / NATS-Bus | **nicht gebaut** (Ausbaustufe) |

**Bau-Regel:** Keine 9 Container mit Remap. Bus-Worker erst nach D1–D3-Pfad und ohne Rollen-Umschreibung.

---

## 7. Schuld (mitführen)

| ID | Zusage | Stand |
|----|--------|-------|
| D1 | `not_investment_advice` | Health/Envelope · Ebene 1 |
| D2 | Red nur Sandbox / Blue zeichnet | Map v2 · Ebene 1 |
| D3 | Validierungs-Gateway | Pilot-Klasse · Ebene 1 |
| D4 | Ingress/Egress-only exterior | **diese Map** · Facade `SupranodeFacade` (dünn); Bus/9-Services weiterhin Intent |

---

## 8. Verweise

| Dokument / Code | Rolle |
|-----------------|-------|
| `prototypes/raas_hybrid_shell/` | Laufender Kern-Zugang + `SupranodeFacade` |
| `docs/RaaS_HYBRID_KI_ROADMAP_v0.md` | Core/Shell Phasen |
| `docs/RaaS_P9_MAPPING_v2.md` | Red/Blue Overlay |
| `services/raas_portal/` | Tools |
| `agents_b2g/bunker/` | HSM-Adapter Intent für Egress |
