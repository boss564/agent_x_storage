#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AstroCore Kuramoto-Emergenz-Evaluator (Baustein 3)

Liest die Transaction-Timestamps aller 9 Agenten ein, berechnet den
Kuramoto-Ordnungsparameter R(t) und führt einen IAAFT-Surrogat-Test
durch, um echte Schwarm-Emergenz von reinem Rauschen zu unterscheiden.

Status:
    - EMERGENCE_PASSED (GRÜN) : p < 0.01 → Echte Phasenkopplung
    - EMERGENCE_FAILED (ROT)  : p >= 0.01 → Nur paralleles Rauschen

Note: Parallel measurement stack also lives in agents_b2g/emergence/measure.py
(IFI-shuffle / Hilbert). AstroCore is the standalone CLI evaluator for
Wirtschaftsagenten transaction logs.
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
from scipy.fft import fft, ifft
from scipy.stats import rankdata


class KuramotoEvaluator:
    """
    Kern-Evaluator für Kuramoto-Synchronisation in Agentenschwärmen.
    """

    def __init__(
        self,
        agent_logs: Dict[str, List[float]],
        time_range: Optional[Tuple[float, float]] = None,
        n_time_bins: int = 1000,
    ):
        """
        Args:
            agent_logs: {agent_id: [transaktion_timestamps]}.
            time_range: (t_start, t_end) – falls None, wird aus Daten abgeleitet.
            n_time_bins: Anzahl der Abtastpunkte für das kontinuierliche Signal.
        """
        self.agent_logs = agent_logs
        self.n_agents = len(agent_logs)
        self.n_time_bins = n_time_bins

        # Zeitbereich aus allen Logs ableiten
        all_ts = [ts for log in agent_logs.values() for ts in log]
        if not all_ts:
            raise ValueError("Agenten-Logs sind leer – keine Transaktionen vorhanden.")

        self.t_min = min(all_ts)
        self.t_max = max(all_ts)
        if time_range:
            self.t_min, self.t_max = time_range

        self.time_points = np.linspace(self.t_min, self.t_max, self.n_time_bins)
        self.dt = self.time_points[1] - self.time_points[0]

        # Cache für beobachtete R-Werte
        self._R_obs_mean = None

    # --------------------------------------------------------------
    # 1. Phasenberechnung
    # --------------------------------------------------------------
    def _compute_phase(self, timestamps: List[float], t: float) -> float:
        """
        Berechnet die Kuramoto-Phase θ_j(t) ∈ [0, 2π) für einen Agenten
        gemäß: θ = 2π * (t - t_last) / (t_next - t_last).
        """
        if not timestamps:
            return 0.0

        # Falls t vor dem ersten oder nach dem letzten Event liegt
        if t <= timestamps[0]:
            return 0.0
        if t >= timestamps[-1]:
            # Dauerhaft auf 2π (bzw. 0) setzen, da zyklisch
            return 2.0 * np.pi

        # Binäre Suche für das umgebende Intervall
        idx = np.searchsorted(timestamps, t) - 1
        t_last = timestamps[idx]
        t_next = timestamps[idx + 1]

        if t_next - t_last == 0:
            return 0.0

        return 2.0 * np.pi * (t - t_last) / (t_next - t_last)

    # --------------------------------------------------------------
    # 2. Ordnungsparameter R(t)
    # --------------------------------------------------------------
    def _compute_order_parameter(self, t: float) -> float:
        """Berechnet den komplexen Kuramoto-Parameter R(t) zu einem Zeitpunkt."""
        phases = []
        for agent_id, timestamps in self.agent_logs.items():
            theta = self._compute_phase(timestamps, t)
            phases.append(theta)

        # R = | (1/N) * Σ e^{iθ_j} |
        complex_avg = np.mean(np.exp(1j * np.array(phases)))
        return np.abs(complex_avg)

    def compute_observed_mean_R(self) -> float:
        """Berechnet den gemittelten Ordnungsparameter R̄_obs über den gesamten Zeitraum."""
        if self._R_obs_mean is not None:
            return self._R_obs_mean

        R_values = [self._compute_order_parameter(t) for t in self.time_points]
        self._R_obs_mean = np.mean(R_values)
        return self._R_obs_mean

    # --------------------------------------------------------------
    # 3. IAAFT-Surrogat-Generator
    # --------------------------------------------------------------
    @staticmethod
    def _signal_from_timestamps(
        timestamps: List[float],
        time_points: np.ndarray,
    ) -> np.ndarray:
        """
        Wandelt diskrete Event-Timestamps in ein gleichmäßig abgetastetes
        Intensitätssignal um (Anzahl Events pro Bin).
        """
        signal = np.zeros(len(time_points))
        if not timestamps:
            return signal

        # Histogramm über die Bins
        counts, _ = np.histogram(timestamps, bins=time_points)

        # counts hat Länge bins-1, wir passen es auf die Mittelpunkte an
        # Für IAAFT ist es besser, die Zählungen den Bin-Mitten zuzuordnen.
        # Wir interpoliert hier grob: Wir setzen den Wert jedes Bins auf die Zählung.
        # Damit es ein kontinuierliches Signal wird, füllen wir die Mitte.
        bin_centers = (time_points[:-1] + time_points[1:]) / 2
        signal_interp = np.zeros(len(time_points))

        # Setze die Zählungen auf die nächsten Stützstellen (vereinfacht)
        for i, center in enumerate(bin_centers):
            idx = np.argmin(np.abs(time_points - center))
            signal_interp[idx] = counts[i]

        return signal_interp

    @staticmethod
    def _iaaft_surrogate(original_signal: np.ndarray, max_iter: int = 100) -> np.ndarray:
        """
        Erzeugt ein IAAFT-Surrogat für ein gegebenes Signal.

        Behält das Amplitudenspektrum und die empirische Verteilung bei,
        randomisiert aber die Phasenbeziehungen.

        Referenz: Schreiber & Schmitz (1996) – "Improved surrogate data for nonlinearity tests".
        """
        signal = np.asarray(original_signal)
        n = len(signal)

        # 1. Originale Amplituden des Spektrums speichern
        X_orig = fft(signal)
        amplitudes = np.abs(X_orig)

        # 2. Sortierte Originalwerte für die Rang-Erzwingung
        sorted_orig = np.sort(signal)

        # 3. Initialisierung: zufällige Phase (Fourier-Transformierte mit zufälligen Phasen)
        phases = np.random.uniform(0, 2 * np.pi, n)
        # Erzwinge Hermitesche Symmetrie für reelles Signal
        phases[1:] = -phases[-1:0:-1]  # einfache Symmetrie für n gerade/ungerade
        X_rand = amplitudes * np.exp(1j * phases)
        current = np.real(ifft(X_rand))

        # 4. Iteration: Amplituden-Erzwingung ↔ Rang-Erzwingung
        for _ in range(max_iter):
            # Schritt A: Amplituden-Erzwingung (Spektrum anpassen)
            X_cur = fft(current)
            X_cur_amp = np.abs(X_cur)
            # Ersetze Amplituden, behalte Phasen
            X_new = amplitudes * (X_cur / (X_cur_amp + 1e-12))  # + epsilon für Stabilität
            current = np.real(ifft(X_new))

            # Schritt B: Rang-Erzwingung (Verteilung anpassen)
            ranks = rankdata(current) - 1
            current = sorted_orig[ranks.astype(int)]

        return current

    def _generate_iaaft_surrogates_for_agents(
        self, n_surrogates: int
    ) -> List[Dict[str, List[float]]]:
        """
        Erzeugt für jeden Agenten n_surrogates unabhängige IAAFT-Surrogate
        der Intensitäts-Zeitreihe.
        """
        surrogate_datasets = []

        # Zuerst: Signale für alle Agenten aus ihren Timestamps generieren
        agent_signals = {}
        for agent_id, timestamps in self.agent_logs.items():
            signal = self._signal_from_timestamps(timestamps, self.time_points)
            agent_signals[agent_id] = signal

        for _ in range(n_surrogates):
            surr_logs = {}
            for agent_id, signal in agent_signals.items():
                # IAAFT-Surrogat erzeugen
                surr_signal = self._iaaft_surrogate(signal)

                # Rücktransformation in Timestamps:
                # Wir müssen aus dem Intensitätssignal wieder Events machen.
                # Dazu simulieren wir Poisson-ähnliche Events mit der Intensität.
                # Oder wir nehmen die Signalwerte als "Aktivitätsgewicht" und
                # generieren eine Liste von Zeiten, die dieser Intensität folgen.

                # Für den Kuramoto-Phasenvergleich brauchen wir nicht die exakten
                # ursprünglichen Timestamps, sondern nur die Aktivitätsverteilung.
                # Wir erzeugen hier eine Liste von Zeiten, die proportional zur
                # Intensität sind.

                # Konvertiere Signal in kumulative Verteilungsfunktion (CDF)
                intensity = np.maximum(surr_signal, 0)  # keine negativen Intensitäten
                if np.sum(intensity) == 0:
                    surr_ts = []
                else:
                    cdf = np.cumsum(intensity) / np.sum(intensity)
                    # Ziehe so viele Zufallsereignisse wie ursprünglich vorhanden
                    n_events = len(self.agent_logs[agent_id])
                    rand_vals = np.random.uniform(0, 1, n_events)
                    # Interpoliere die Zeitpunkte aus der CDF
                    surr_ts = np.interp(rand_vals, cdf, self.time_points).tolist()
                    surr_ts.sort()

                surr_logs[agent_id] = surr_ts

            surrogate_datasets.append(surr_logs)

        return surrogate_datasets

    # --------------------------------------------------------------
    # 4. Signifikanz-Test (Monte-Carlo)
    # --------------------------------------------------------------
    def run_significance_test(
        self, n_surrogates: int = 500, alpha: float = 0.01
    ) -> Tuple[float, str]:
        """
        Führt den Monte-Carlo-Signifikanztest durch.

        Returns:
            (p_value, status)
        """
        # 1. Beobachteten Mittelwert berechnen
        R_obs = self.compute_observed_mean_R()
        print(f"[Evaluator] R̄_obs = {R_obs:.6f}")

        # 2. Surrogate generieren
        print(f"[Evaluator] Generiere {n_surrogates} IAAFT-Surrogate...")
        surrogate_sets = self._generate_iaaft_surrogates_for_agents(n_surrogates)

        # 3. R̄ für jedes Surrogat berechnen
        R_surr_list = []
        for i, surr_logs in enumerate(surrogate_sets):
            # Temporären Evaluator für die Surrogate erzeugen
            sub_eval = KuramotoEvaluator(
                surr_logs,
                time_range=(self.t_min, self.t_max),
                n_time_bins=self.n_time_bins,
            )
            R_surr = sub_eval.compute_observed_mean_R()
            R_surr_list.append(R_surr)

            if (i + 1) % 100 == 0:
                print(f"  -> {i + 1}/{n_surrogates} Surrogate verarbeitet")

        # 4. p-Wert berechnen (Monte-Carlo)
        R_surr_array = np.array(R_surr_list)
        p_value = np.mean(R_surr_array >= R_obs)
        print(f"[Evaluator] p-Wert = {p_value:.6f}")

        # 5. Entscheidung
        if p_value < alpha:
            status = "EMERGENCE_PASSED"
            print(f"[Evaluator] ✅ Status: {status} (GRÜN) – Echte Schwarm-Emergenz")
        else:
            status = "EMERGENCE_FAILED"
            print(f"[Evaluator] ❌ Status: {status} (ROT) – Nur paralleles Rauschen")

        return p_value, status


# --------------------------------------------------------------
# 5. CLI / Einstiegspunkt
# --------------------------------------------------------------
def load_logs_from_dir(log_dir: Path) -> Dict[str, List[float]]:
    """Lädt die Transaction-Timestamps aus den JSON-Logs jedes Agenten."""
    logs = {}
    for log_file in log_dir.glob("agent_*.json"):
        agent_id = log_file.stem.replace("agent_", "")
        with open(log_file, "r") as f:
            data = json.load(f)
            # Erwartet: {"transactions": [1640995200.0, ...]} oder direkt Liste
            if isinstance(data, list):
                timestamps = data
            elif isinstance(data, dict) and "transactions" in data:
                timestamps = data["transactions"]
            else:
                continue
            logs[agent_id] = sorted(timestamps)
    return logs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AstroCore Kuramoto-Emergenz-Evaluator"
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        required=True,
        help="Pfad zum Verzeichnis mit den agent_*.json Logs",
    )
    parser.add_argument(
        "--n-surrogates",
        type=int,
        default=500,
        help="Anzahl der IAAFT-Surrogate (Default: 500)",
    )
    parser.add_argument(
        "--n-bins",
        type=int,
        default=1000,
        help="Anzahl der Zeit-Bins für die Signalabtastung",
    )
    args = parser.parse_args()

    # Logs laden
    print(f"Lade Agenten-Logs aus: {args.log_dir}")
    logs = load_logs_from_dir(args.log_dir)
    if len(logs) < 2:
        print("Fehler: Weniger als 2 Agenten-Logs gefunden.")
        exit(1)

    print(f"Gefundene Agenten: {list(logs.keys())}")

    # Evaluator ausführen
    evaluator = KuramotoEvaluator(logs, n_time_bins=args.n_bins)
    p_val, status = evaluator.run_significance_test(n_surrogates=args.n_surrogates)

    # Ergebnis persistieren (optional)
    result = {
        "R_obs": float(evaluator._R_obs_mean),
        "p_value": float(p_val),
        "status": status,
        "n_agents": len(logs),
        "n_surrogates": args.n_surrogates,
        "time_range": [evaluator.t_min, evaluator.t_max],
    }
    with open(args.log_dir / "emergence_result.json", "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n✅ Ergebnis gespeichert in: {args.log_dir / 'emergence_result.json'}")
