# Continuous Dissensus Gegenprobe — Analyse

**Gate (matched protocol):** `PROTO_PASS` · 0.00s / 16s · relational pass 3/3

## Zwei Metrik-Ebenen

| Ebene | Definition | Rolle |
|-------|------------|-------|
| **Primary (relational)** | anti vs **true** Sticky-Partner · Margin B−C | Gate — analog diskret |
| **Secondary (global)** | Gegenzeichen über **alle** Paare | Bericht — topologie-blind |

v1 (unbounded): divergiert (alle Seeds).

v2 (tanh): Primary kann PASS oder FAIL sein; Secondary sieht oft B≈C
(anti_global ≈ 0.5, kleine Margin) — das erklärt Berichte der Form
„beide Arme identisch“, ist aber **kein** Ersatz für den relationalen Gate.

## Root Cause (präzisiert)

`S_i += α·(S_i − S_j)` ist auf der **Signal-Kante** symmetrisch. Ob daraus
**keine** relationale Struktur vs. true Partner folgt, ist empirisch:
gemessen wird anti_true, nicht anti_signal und nicht nur die globale Paarstatistik.

## Serie

- Stateful Graph v0: `STRUCTURE_RELATIONAL` (diskret) — versiegelt Sweep
- Dissens-Gegenprobe: `PROTO_PASS` unter matched protocol — siehe Gate-Datei

Kein Pre-Reg ohne User-Freigabe.
