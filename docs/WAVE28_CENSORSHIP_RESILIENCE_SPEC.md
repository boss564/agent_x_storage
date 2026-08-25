# Wave 28 Censorship Resilience — Spezifikation

**Status:** Bindend für Censorship-Stack unter Wave 28 (Variante A)  
**Charakter:** Defensiv · objektiv · keine ×9-Verletzung  
**Schema:** `agents_b2g/defense/wave28_threat_engine.sql` (§ Censorship)  
**Leitplanken:** keine Gewinn-Umleitung · kein Clone-Architect · keine normative Stigmatisierung

---

## 1. Operative Bedrohungsvektoren (v1.0)

| Vektor | Nachweis | Schutz |
|--------|----------|--------|
| RPC/Builder-Zensur | OFAC-Filter bei Public RPCs / MEV-Boost-Buildern | Dynamic Routing / Fallback-RPC |
| Stablecoin-Blacklisting | USDC `Blacklisted`, USDT `blacklist` | Asset-Exposure Fallback (→ native) |
| Bridge-Relayer-Selektion | CCTP/LayerZero/OmniBridge Attester | Relayer Health + Drop-Rate |
| Adversarielles Builder-Filtering | Searcher-Bevorzugung | Bypass-Route / alternate builder |

---

## 2. Architektur: Erweiterung, kein 10. Hauptagent

×9 bleibt. `CounterSwarmDeployer` (4.7) wird zu **`CensorshipBypassRouter`** umgewidmet
(Counter-Swarm operativ selten; Zensur operativ zwingend). Alias
`counter_swarm_deployer` bleibt für Abwärtskompatibilität.

| Mechanismus | Hauptagent | Subagent |
|-------------|------------|----------|
| Sanctions & Poisoning | PerimeterGatewayDefender | `reputation_score_lookup` + `SanctionsScreeningAdapter` |
| Censorship-Aware Routing | ActiveResponseCoordinator | `censorship_bypass_router` (ex 4.7) |
| Relayer Health | SwarmLearningAdapter | `feature_extractor` + `RelayerHealthAdapter` |
| Asset-Exposure | SwarmLearningAdapter | `attack_vector_database` + Vektoren `CENSORSHIP_*` |

---

## 3. Address Poisoning (objektiv)

Vanity-/Poisoning-Heuristik: Adresse teilt **≥ 4** führende **oder** abschließende
Hex-Zeichen mit einem Watchlist-Ziel, ist aber **nicht** identisch.
Keine Intent-Zuschreibung — nur String-Ähnlichkeit.

---

## 4. Gatekeeper

`block_cause = CENSORSHIP_DETECTED` ist gültig für:

- `wave28_record_gate_coupling` / `wave28_censorship_incidents`
- Wave-38 `BlockCause.CENSORSHIP_DETECTED` (operativ; nicht Bridge-Pre-Reg)

BLOCKED weiterhin nur mit `block_cause` (Single Source of Truth in SQL).

---

## 5. Wave 38

Relayer-Drop als Zensur-Event darf **nur** über eine **neue** Pre-Reg als Z_neu-Kandidat
eingehen — nicht in die versiegelte Bridge-Diagnose.

---

## 6. Version

| Version | Datum | Änderung |
|---------|-------|----------|
| 1.0 | 2026-08-23 | Erstfassung: Umwidmung 4.7, 3 Tabellen, 3 Adapter |
