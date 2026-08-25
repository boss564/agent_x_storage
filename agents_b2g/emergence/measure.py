#!/usr/bin/env python3
"""Emergenz-Messung fuer Agentenschwaerme — Divergenz, Graphstruktur, Kuramoto.

Drei Kennzahlen, die rot werden koennen:

  1. Divergenz D    — Unterscheiden sich die Agenten ueberhaupt?
                      D ~ 0 heisst: ein Prozess unter N Etiketten.
  2. Graphstruktur  — Hat der Interaktionsgraph Struktur, die ein Zufallsgraph
                      mit gleicher Gradsequenz nicht auch haette? (z-Scores)
  3. Kuramoto r     — Schwingen die Agenten aufeinander ein, staerker als
                      phasenrandomisierte Surrogate es erklaeren? (p-Wert)

Die drei zusammen ergeben erst ein Urteil. Perfekte Synchronie identischer
Agenten (D~0, r~1) ist KEINE Emergenz, sondern eine Tautologie — deshalb
schaltet die Interpretation bei D~0 auf TRIVIAL_SYNC.

Methodik-Vorbild: /Volumes/THX_CORE_16TB/cherrystudio_projekte/astrocore/PHASENKOPPLUNG.md
(resultierender Vektor, Rayleigh-Test, Surrogate; Nachtrag: IAAFT-Ko-Periodizität).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np

try:
    import networkx as nx
    NETWORKX = True
except ImportError:                                    # harte Abhaengigkeit
    NETWORKX = False

try:
    from scipy.signal import hilbert
    SCIPY = True
except ImportError:
    SCIPY = False


# ── Eingabeformat ────────────────────────────────────────────────────────────

@dataclass
class SwarmTrace:
    """Mitschnitt eines Schwarmlaufs.

    agents   : Agenten-IDs, Laenge N
    states   : (T, N, D) — Zustandsvektor je Agent je Tick
    messages : (t, sender, receiver) — gerichtete Nachrichten
    """
    agents: List[str]
    states: np.ndarray
    messages: List[Tuple[int, str, str]] = field(default_factory=list)

    def __post_init__(self):
        self.states = np.asarray(self.states, dtype=float)
        if self.states.ndim != 3:
            raise ValueError(f"states muss (T,N,D) sein, ist {self.states.shape}")
        if self.states.shape[1] != len(self.agents):
            raise ValueError("states.shape[1] != len(agents)")


# ── 1. Divergenz ─────────────────────────────────────────────────────────────

def divergence(trace: SwarmTrace) -> Dict:
    """Mittlerer paarweiser Abstand der Agentenzustaende, dimensionsnormiert.

    Jede Zustandsdimension wird ueber den ganzen Lauf z-normiert, damit
    Groessenordnungen sich nicht gegenseitig erschlagen. D = 0 heisst:
    alle Agenten sind zu jedem Zeitpunkt identisch.
    """
    S = trace.states                                   # (T, N, D)
    T, N, Dd = S.shape
    if N < 2:
        return {"divergence": 0.0, "note": "N<2"}

    scale = S.reshape(-1, Dd).std(axis=0)
    scale[scale < 1e-12] = 1.0                         # konstante Dimension
    Z = (S - S.reshape(-1, Dd).mean(axis=0)) / scale

    per_tick = []
    for t in range(T):
        X = Z[t]                                       # (N, D)
        diff = X[:, None, :] - X[None, :, :]
        dist = np.sqrt((diff ** 2).sum(axis=-1) / Dd)
        iu = np.triu_indices(N, k=1)
        per_tick.append(dist[iu].mean())
    per_tick = np.array(per_tick)

    # Statisch vs. dynamisch trennen: eine Dimension ist statisch, wenn sie
    # sich innerhalb eines Agenten ueber die Zeit nicht aendert. Unterschiede
    # in statischen Dimensionen sind Konfiguration, nicht Divergenz — sie
    # entstehen beim Anlegen, nicht im Lauf.
    per_dim, static_dims, dynamic_dims = [], [], []
    for d in range(Dd):
        spread = float(S[:, :, d].std(axis=1).mean())   # Streuung ueber Agenten
        temporal = float(S[:, :, d].std(axis=0).mean()) # Aenderung ueber Zeit
        per_dim.append(spread)
        (dynamic_dims if temporal > 1e-9 else static_dims).append(d)

    def _mean_pairwise(idx):
        if not idx:
            return 0.0
        Zi = Z[:, :, idx]
        acc = []
        for t in range(T):
            X = Zi[t]
            diff = X[:, None, :] - X[None, :, :]
            dist = np.sqrt((diff ** 2).sum(axis=-1) / len(idx))
            acc.append(dist[np.triu_indices(N, k=1)].mean())
        return float(np.mean(acc))

    D = float(per_tick.mean())
    D_dyn = _mean_pairwise(dynamic_dims)
    D_stat = _mean_pairwise(static_dims)
    return {
        "divergence": round(D, 6),
        "divergence_dynamic": round(D_dyn, 6),
        "divergence_static": round(D_stat, 6),
        "n_dynamic_dims": len(dynamic_dims),
        "n_static_dims": len(static_dims),
        "divergence_over_time": per_tick.round(6).tolist(),
        "per_dimension_spread": [round(x, 6) for x in per_dim],
        "identical_agents": bool(D_dyn < 1e-6),
    }


# ── 2. Graphstruktur gegen Nullmodell ────────────────────────────────────────

def _graph_metrics(G: "nx.DiGraph") -> Dict[str, float]:
    n = G.number_of_nodes()
    if n < 3:
        return {"centralization": 0.0, "reciprocity": 0.0, "clustering": 0.0}
    deg = dict(G.degree())
    dmax = max(deg.values())
    denom = (n - 1) * (n - 2) if n > 2 else 1
    centralization = sum(dmax - d for d in deg.values()) / denom if denom else 0.0
    try:
        recip = nx.reciprocity(G) or 0.0
    except Exception:
        recip = 0.0
    clust = nx.average_clustering(nx.Graph(G)) if G.number_of_edges() else 0.0
    return {
        "centralization": float(centralization),
        "reciprocity": float(recip),
        "clustering": float(clust),
    }


def graph_structure(trace: SwarmTrace, n_surrogates: int = 200,
                    seed: int = 12345) -> Dict:
    """Vergleicht den beobachteten Interaktionsgraphen mit einem
    Konfigurationsmodell gleicher Gradsequenz (degree-preserving rewiring).

    Wichtig: Bei Sterntopologie kann gradbewahrendes Rewiring die Struktur
    nicht zerstoeren — der z-Score ist dann uninformativ. Deshalb wird die
    Nabenlast separat berichtet und die Aussage entsprechend markiert.
    """
    if not NETWORKX:
        return {"error": "networkx nicht installiert — harte Abhaengigkeit"}
    if not trace.messages:
        return {"error": "keine Nachrichten im Trace"}

    G = nx.DiGraph()
    G.add_nodes_from(trace.agents)
    weights: Dict[Tuple[str, str], int] = {}
    for _, s, r in trace.messages:
        weights[(s, r)] = weights.get((s, r), 0) + 1
    for (s, r), w in weights.items():
        G.add_edge(s, r, weight=w)

    obs = _graph_metrics(G)

    # Nabenlast: Anteil der Nachrichten, die den staerksten Knoten BERUEHREN
    # (Sender oder Empfaenger). Beim perfekten Stern ist das 1.0; beim
    # Zufallsgraphen mit N Knoten etwa 2/N. Der Anteil an Nachrichten-ENDEN
    # waere beim Stern exakt 0.5 und damit nicht trennscharf.
    touch: Dict[str, int] = {}
    for _, s, r in trace.messages:
        for node in ({s, r}):
            touch[node] = touch.get(node, 0) + 1
    n_msgs = len(trace.messages) or 1
    hub, hub_touch = max(touch.items(), key=lambda kv: kv[1])
    hub_share = hub_touch / n_msgs

    rng = np.random.default_rng(seed)
    surr: Dict[str, List[float]] = {k: [] for k in obs}
    m = G.number_of_edges()
    for _ in range(n_surrogates):
        H = G.copy()
        if m >= 2:
            try:
                # DiGraph: undirected double_edge_swap fails silently/raises —
                # use directed_edge_swap so the null model has real variance.
                nx.directed_edge_swap(H, nswap=max(1, m), max_tries=m * 20,
                                      seed=int(rng.integers(1 << 30)))
            except (nx.NetworkXError, nx.NetworkXAlgorithmError):
                pass
        hm = _graph_metrics(H)
        for k, v in hm.items():
            surr[k].append(v)

    z = {}
    for k, v in obs.items():
        arr = np.array(surr[k])
        sd = arr.std()
        z[k] = round(float((v - arr.mean()) / sd), 3) if sd > 1e-12 else None

    n = G.number_of_nodes()
    density = m / (n * (n - 1)) if n > 1 else 0.0
    all_null = all(v is None for v in z.values())
    structured = any(zz is not None and abs(zz) > 2.0 for zz in z.values())

    if all_null:
        null_note = ("Surrogat-Ensemble ohne Varianz — bei sehr dichtem oder "
                     "sternfoermigem Graphen kann gradbewahrendes Rewiring die "
                     "Struktur nicht veraendern. z-Scores sind hier ohne Aussage.")
    else:
        null_note = ""

    return {
        "density": round(density, 4),
        "null_model_informative": bool(not all_null),
        "null_model_note": null_note,
        "observed": {k: round(v, 4) for k, v in obs.items()},
        "surrogate_mean": {k: round(float(np.mean(v)), 4) for k, v in surr.items()},
        "z_scores": z,
        "hub_node": hub,
        "hub_share": round(hub_share, 4),
        "hub_expected_random": round(2.0 / max(len(trace.agents), 1), 4),
        "hub_dominated": bool(hub_share > 0.5),
        "structured_vs_null": bool(structured),
        "note": ("Nabe beruehrt >50% aller Nachrichten — Sterntopologie. "
                 "Gradbewahrende Surrogate koennen das nicht aufloesen, "
                 "z-Scores sind hier uninformativ.") if hub_share > 0.5 else "",
    }


# ── 3. Kuramoto-Ordnungsparameter ────────────────────────────────────────────

def _detrend(A: np.ndarray) -> np.ndarray:
    """Entfernt je Agent den linearen Trend. Ohne das dominiert bei
    kumulativen Groessen (Volumen, Zaehler) die Rampe die Phasenschaetzung,
    und alle Agenten wirken gleichphasig, obwohl sie es nicht sind."""
    T = A.shape[0]
    t = np.arange(T, dtype=float)
    t = (t - t.mean()) / (t.std() or 1.0)
    beta = (t[:, None] * A).sum(axis=0) / (t @ t)
    return A - np.outer(t, beta) - A.mean(axis=0, keepdims=True)


def _phases(activity: np.ndarray) -> np.ndarray:
    """Momentanphase je Agent via Hilbert-Transformation. activity: (T, N)."""
    A = _detrend(np.asarray(activity, dtype=float))
    if SCIPY:
        return np.angle(hilbert(A, axis=0))
    # Fallback ohne scipy: FFT-basierte analytische Signalbildung
    T = A.shape[0]
    F = np.fft.fft(A, axis=0)
    h = np.zeros(T)
    h[0] = 1
    if T % 2 == 0:
        h[T // 2] = 1
        h[1:T // 2] = 2
    else:
        h[1:(T + 1) // 2] = 2
    return np.angle(np.fft.ifft(F * h[:, None], axis=0))


def _phase_randomize(A: np.ndarray, rng) -> np.ndarray:
    """Surrogat: Spektrum je Agent erhalten, Phasen unabhaengig randomisieren.
    Zerstoert Kopplung zwischen Agenten, laesst Autokorrelation intakt."""
    T, N = A.shape
    F = np.fft.rfft(A, axis=0)
    mag = np.abs(F)
    ph = rng.uniform(0, 2 * np.pi, size=F.shape)
    ph[0, :] = 0
    if T % 2 == 0:
        ph[-1, :] = 0
    return np.fft.irfft(mag * np.exp(1j * ph), n=T, axis=0)


def kuramoto(trace: SwarmTrace, dim="auto", n_surrogates: int = 200,
             seed: int = 12345) -> Dict:
    """Ordnungsparameter r = |1/N sum_j exp(i*theta_j)| ueber die Zeit,
    verglichen mit phasenrandomisierten Surrogaten.

    r nahe 1  = gleichphasig, r nahe 1/sqrt(N) = zufaellig verteilt.
    Entscheidend ist nicht r selbst, sondern r gegen die Surrogatverteilung.
    """
    if dim == "auto":
        # Nach Detrending waehlen: eine monotone Rampe hat grosse Varianz,
        # aber keine Schwingung — sie waere die falsche Wahl.
        resid = np.array([_detrend(trace.states[:, :, d]).std(axis=0).mean()
                          for d in range(trace.states.shape[2])])
        if float(resid.max()) <= 1e-12:
            return {"error": "keine schwingende Zustandsdimension — Phase undefiniert"}
        dim = int(np.argmax(resid))
    A = trace.states[:, :, dim]                        # (T, N)
    T, N = A.shape
    if T < 16:
        return {"error": f"zu wenige Ticks ({T}) fuer Phasenschaetzung"}

    theta = _phases(A)
    r_t = np.abs(np.exp(1j * theta).mean(axis=1))
    r_obs = float(r_t.mean())

    rng = np.random.default_rng(seed)
    r_surr = []
    for _ in range(n_surrogates):
        As = _phase_randomize(A, rng)
        th = _phases(As)
        r_surr.append(float(np.abs(np.exp(1j * th).mean(axis=1)).mean()))
    r_surr = np.array(r_surr)

    sd = r_surr.std()
    z = float((r_obs - r_surr.mean()) / sd) if sd > 1e-12 else None
    p = float((np.sum(r_surr >= r_obs) + 1) / (n_surrogates + 1))

    return {
        "r_observed": round(r_obs, 4),
        "r_surrogate_mean": round(float(r_surr.mean()), 4),
        "r_random_baseline": round(1.0 / np.sqrt(N), 4),
        "dimension_used": int(dim),
        "z_score": round(z, 3) if z is not None else None,
        "p_value": round(p, 4),
        "significant": bool(p < 0.05),
        "method": "hilbert",
    }


# ── 3b. Ereignisbasierte Phase (Relaxations-/IF-Oszillatoren) ────────────────

def firing_phase(firing_times, t_grid):
    """Event-based phase: linear 0→2π between consecutive firings.

    Returns theta(t) in [0, 2π), NaN outside the firing span.
    None if fewer than 2 firings.
    """
    ft = np.asarray(firing_times, dtype=float)
    if len(ft) < 2:
        return None
    t_grid = np.asarray(t_grid, dtype=float)
    theta = np.full(len(t_grid), np.nan)
    for i, t in enumerate(t_grid):
        k = int(np.searchsorted(ft, t, side="right") - 1)
        if k < 0 or k >= len(ft) - 1:
            continue
        t_k, t_k1 = ft[k], ft[k + 1]
        ifi = t_k1 - t_k
        if ifi <= 0:
            continue
        theta[i] = 2.0 * np.pi * (t - t_k) / ifi
    return theta


def kuramoto_r_nan(phases: np.ndarray):
    """phases: (n_agents, n_times). NaN-tolerant Kuramoto r(t) and mean r."""
    z = np.exp(1j * phases)
    n_valid = np.sum(~np.isnan(phases), axis=0)
    r_t = np.full(phases.shape[1], np.nan, dtype=float)
    for t in range(phases.shape[1]):
        if n_valid[t] >= 2:
            r_t[t] = float(np.abs(np.nanmean(z[:, t])))
    r_bar = float(np.nanmean(r_t)) if np.any(~np.isnan(r_t)) else float("nan")
    return r_t, r_bar


def surrogate_ifi_shuffle(firing_times, t_grid, rng):
    """Shuffle IFIs of one agent: keep rate+IFI dist, destroy cross-agent timing."""
    ft = np.asarray(firing_times, dtype=float)
    if len(ft) < 2:
        return None
    ifis = np.diff(ft)
    rng.shuffle(ifis)
    new_times = np.concatenate([[ft[0]], ft[0] + np.cumsum(ifis)])
    new_times = new_times[new_times <= ft[-1]]
    return firing_phase(new_times, t_grid)


def coincidence_histogram(agent_firing_times: Sequence[Sequence[float]],
                          t_max: int) -> Dict:
    """Per-cycle coincidence count + lag-0 peak diagnostic."""
    n_agents = len(agent_firing_times)
    counts = np.zeros(int(t_max) + 1, dtype=int)
    for ft in agent_firing_times:
        for t in ft:
            ti = int(t)
            if 0 <= ti <= t_max:
                counts[ti] += 1
    # cycles with ≥2 coincident fires
    multi = int(np.sum(counts >= 2))
    multi_ge3 = int(np.sum(counts >= 3))
    peak = int(counts.max()) if len(counts) else 0
    mean_c = float(counts.mean()) if len(counts) else 0.0
    # expected coincident cycles if independent Poisson-like:
    # P(k>=2) rough via mean rate
    rate = mean_c  # mean agents firing per cycle
    # histogram of coincidence multiplicity
    max_show = min(peak + 1, n_agents + 1)
    hist = {int(k): int(np.sum(counts == k)) for k in range(max_show)}
    # peaks only informative if sharper than a Poisson baseline with same mean
    # (independent oscillators with similar rates also produce multi-firer cycles)
    from math import exp, factorial
    lam = mean_c
    p_ge3 = 1.0
    if lam > 0:
        p_ge3 = 1.0 - sum(exp(-lam) * lam ** k / factorial(k) for k in range(3))
    expected_ge3 = p_ge3 * max(t_max, 1)
    excess_ge3 = multi_ge3 - expected_ge3 if lam > 0 else 0.0
    zero_frac = float(np.mean(counts == 0)) if len(counts) else 0.0
    # Two bundling regimes:
    #  (a) dense sync: more ge3-cycles than Poisson
    #  (b) sparse bursts: many silent cycles + tall peaks (corridor) —
    #      Poisson excess goes *negative* here, so use peak height instead
    dense_peak = bool(peak >= 3 and excess_ge3 > max(10.0, 0.05 * t_max))
    burst_peak = bool(peak >= max(3, int(0.5 * n_agents)) and zero_frac > 0.15)
    return {
        "mean_firers_per_cycle": round(mean_c, 4),
        "cycles_with_ge2": multi,
        "cycles_with_ge3": multi_ge3,
        "peak_coincidence": peak,
        "fraction_multi": round(multi / max(t_max, 1), 4),
        "zero_frac": round(zero_frac, 4),
        "hist_n_firers": hist,
        "poisson_expected_ge3": round(expected_ge3, 1),
        "excess_ge3_vs_poisson": round(excess_ge3, 1),
        "has_coincidence_peaks": bool(dense_peak or burst_peak),
        "peak_regime": "burst" if burst_peak else ("dense" if dense_peak else "none"),
    }


def kuramoto_firing(
    trace: SwarmTrace,
    n_surrogates: int = 500,
    seed: int = 12345,
    min_firings: int = 3,
) -> Dict:
    """Event-based Kuramoto with IFI-shuffle surrogates (TIER 2b measurement)."""
    firings = getattr(trace, "firing_times", None)
    if not firings:
        return {"error": "keine firing_times am Trace — ereignisbasierte Phase unmoeglich"}

    T = trace.states.shape[0]
    t_grid = np.arange(1, T + 1, dtype=float)  # cycles are 1-indexed in adapter
    # Align: adapter uses tc.cycle starting at 1
    agent_fts = []
    included = []
    excluded = []
    for aid in trace.agents:
        ft = sorted(firings.get(aid, []))
        if len(ft) < min_firings:
            excluded.append(aid)
            continue
        agent_fts.append(ft)
        included.append(aid)

    if len(agent_fts) < 2:
        return {
            "error": f"zu wenige Agenten mit ≥{min_firings} Feuern "
                     f"(inkl={len(included)}, excl={len(excluded)})",
            "agents_included": included,
            "agents_excluded": excluded,
            "method": "firing_ifi",
        }

    phases_rows = []
    for ft in agent_fts:
        th = firing_phase(ft, t_grid)
        if th is None:
            continue
        phases_rows.append(th)
    if len(phases_rows) < 2:
        return {"error": "Phasenmatrix < 2 Agenten", "method": "firing_ifi"}

    phases_obs = np.array(phases_rows, dtype=float)
    r_t, r_obs = kuramoto_r_nan(phases_obs)
    if not np.isfinite(r_obs):
        return {"error": "r_obs undefiniert (zu wenig Phasen-Ueberlapp)", "method": "firing_ifi"}

    rng = np.random.default_rng(seed)
    r_surr = np.empty(n_surrogates)
    for s in range(n_surrogates):
        ph = []
        for ft in agent_fts:
            th = surrogate_ifi_shuffle(ft, t_grid, rng)
            if th is None:
                th = np.full(len(t_grid), np.nan)
            ph.append(th)
        _, r_s = kuramoto_r_nan(np.array(ph, dtype=float))
        r_surr[s] = r_s if np.isfinite(r_s) else 0.0

    sd = float(np.nanstd(r_surr))
    mu = float(np.nanmean(r_surr))
    z = float((r_obs - mu) / sd) if sd > 1e-12 else None
    p = float((np.sum(r_surr >= r_obs) + 1) / (n_surrogates + 1))

    t_max = int(max((max(ft) for ft in agent_fts), default=T))
    coin = coincidence_histogram(agent_fts, t_max)

    fire_counts = {aid: len(firings.get(aid, [])) for aid in trace.agents}

    return {
        "r_observed": round(float(r_obs), 4),
        "r_surrogate_mean": round(mu, 4),
        "r_random_baseline": round(1.0 / np.sqrt(len(agent_fts)), 4),
        "dimension_used": "firing_times",
        "z_score": round(z, 3) if z is not None else None,
        "p_value": round(p, 4),
        "significant": bool(p < 0.05),
        "method": "firing_ifi",
        "n_surrogates": n_surrogates,
        "agents_included": included,
        "agents_excluded": excluded,
        "n_agents_phased": len(agent_fts),
        "min_firings": min_firings,
        "fire_counts": fire_counts,
        "coincidence": coin,
        "r_t_nanmean": round(float(np.nanmean(r_t)), 4),
    }


# ── Gesamturteil ─────────────────────────────────────────────────────────────

def assess(trace: SwarmTrace, n_surrogates: int = 200, seed: int = 12345,
           *, phase: str = "auto") -> Dict:
    """Fuehrt alle drei Messungen und leitet ein Urteil ab.

    phase:
      auto    — firing_ifi wenn Trace.firing_times, sonst hilbert
      hilbert — Zustandsvektor + IAAFT
      firing  — ereignisbasierte Phase + IFI-Shuffle
    """
    div = divergence(trace)
    gra = graph_structure(trace, n_surrogates, seed)

    use_firing = (
        phase == "firing"
        or (phase == "auto" and getattr(trace, "firing_times", None))
    )
    if use_firing:
        # Event-based needs more surrogates (Steuerer: 500)
        n_fire = max(n_surrogates, 500)
        kur = kuramoto_firing(trace, n_surrogates=n_fire, seed=seed)
        if kur.get("error") and phase == "auto":
            kur = kuramoto(trace, "auto", n_surrogates, seed)
    else:
        kur = kuramoto(trace, "auto", n_surrogates, seed)

    if div["identical_agents"]:
        verdict = "TRIVIAL_SYNC"
        reason = ("Agenten unterscheiden sich in keiner erworbenen Zustandsgroesse "
                  "(D_dyn~0) — Unterschiede stammen allein aus der Konfiguration. "
                  "Jede Synchronie ist tautologisch: ein Prozess unter N Namen.")
    elif kur.get("significant"):
        verdict = "COUPLED"
        reason = (f"Agenten divergieren dynamisch (D_dyn={div['divergence_dynamic']}) UND synchronisieren "
                  f"staerker als Surrogate (p={kur.get('p_value')}, method={kur.get('method')}).")
    else:
        verdict = "NO_COUPLING"
        reason = (f"Agenten divergieren dynamisch (D_dyn={div['divergence_dynamic']}), aber die "
                  f"Synchronie ist nicht von Zufall unterscheidbar "
                  f"(p={kur.get('p_value')}, method={kur.get('method')}).")

    return {
        "divergence": div,
        "graph": gra,
        "kuramoto": kur,
        "verdict": verdict,
        "reason": reason,
    }


def summary_line(res: Dict) -> str:
    d = res["divergence"]["divergence_dynamic"]
    k = res["kuramoto"]
    g = res["graph"]
    return (f"D_dyn={d:<8} r={k.get('r_observed')} (p={k.get('p_value')}) "
            f"hub={g.get('hub_share')} -> {res['verdict']}")


if __name__ == "__main__":
    import sys
    print(__doc__)
    print(f"numpy={np.__version__} networkx={NETWORKX} scipy={SCIPY}")
    sys.exit(0)
