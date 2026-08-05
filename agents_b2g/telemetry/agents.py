"""
Agent X — Telemetry & Physical Proof (Wave 5, 9 Agents).

On-site hardware integration: GPS tracks, IoT scales, photo evidence.
Produces cryptographically verifiable PoPW proofs for the DeliveryOracle.

Agents:
  1. GPSCollectorAgent          — Live GPS from worker DIDs, geofence + activity
  2. IoTScaleReaderAgent        — Truck scales, net material quantities
  3. PhotoEvidenceAgent         — Site photos with EXIF hashing
  4. SubcontractorValidatorAgent — DID vs bidder list verification
  5. ProgressAggregatorAgent    — Fusion of GPS + scales + photos
  6. PoPWProofGeneratorAgent    — Merkle root from telemetry streams
  7. PoPWVerifierAgent          — On-chain proof verification
  8. DailyReportAgent           — Machine-readable daily construction reports
  9. EmergencyStopAgent         — Anomaly detection + payment halt trigger
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


# ============================================================
# Agent 1: GPSCollectorAgent
# ============================================================


class GPSCollectorAgent:
    """Receives live GPS tracks from worker peaq-DIDs, filters noise, classifies activity."""

    async def check_geofence(self, point: tuple[float, float],
                             site: tuple[float, float], radius_m: float = 500) -> dict:
        """Subagent: GeofenceBoundaryChecker."""
        lat1, lon1 = math.radians(point[0]), math.radians(point[1])
        lat2, lon2 = math.radians(site[0]), math.radians(site[1])
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        dist_m = 6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return {"on_site": dist_m < radius_m, "distance_m": round(dist_m, 1)}

    async def smooth_interpolate(self, track: list[dict]) -> list[dict]:
        """Subagent: SmoothInterpolator — removes GPS spikes."""
        return track  # Production: Kalman filter

    async def classify_activity(self, speeds: list[float]) -> str:
        """Subagent: WorkerActivityClassifier — working / driving / idle."""
        avg_speed = sum(speeds) / max(len(speeds), 1)
        if avg_speed < 1.0:
            return "working"
        elif avg_speed > 30:
            return "driving"
        return "walking"

    async def collect(self, worker_did: str, track: list[dict],
                      site_gps: tuple = (52.376, 9.732)) -> dict:
        """Main: process a worker's GPS track for one day."""
        track = await self.smooth_interpolate(track)
        points_on_site = 0
        total_points = len(track)
        speeds = []

        for i, pt in enumerate(track):
            lat, lon = pt.get("lat", 0), pt.get("lon", 0)
            check = await self.check_geofence((lat, lon), site_gps)
            if check["on_site"]:
                points_on_site += 1
            if i > 0:
                prev = track[i-1]
                dist = math.sqrt((lat-prev.get("lat",0))**2 + (lon-prev.get("lon",0))**2)
                dt = max(1, pt.get("ts", 0) - prev.get("ts", 0))
                speeds.append(dist / dt * 111000)  # Approx m/s

        activity = await self.classify_activity(speeds)
        presence_pct = round(points_on_site / max(total_points, 1) * 100, 1)
        print(f"  [GPS-Collector] 📍 {worker_did[:16]}...: {presence_pct}% on-site "
              f"({points_on_site}/{total_points} pts, activity={activity})")
        return {"worker_did": worker_did, "presence_pct": presence_pct,
                "points_on_site": points_on_site, "total_points": total_points,
                "activity": activity, "gps_hash": hashlib.sha256(
                    json.dumps(track).encode()).hexdigest()[:32]}


# ============================================================
# Agent 2: IoTScaleReaderAgent
# ============================================================


class IoTScaleReaderAgent:
    """Reads IoT truck scales: gross, tare, net material quantities."""

    async def extract_truck_id(self, rfid: str) -> str:
        """Subagent: TruckIDExtractor."""
        return f"TRUCK-{hashlib.sha256(rfid.encode()).hexdigest()[:8].upper()}"

    async def validate_weight(self, gross: float, tare: float, expected: float) -> dict:
        """Subagent: WeightValidator."""
        net = round(gross - tare, 1)
        deviation_pct = round(abs(net - expected) / max(expected, 1) * 100, 1) if expected > 0 else 0
        return {"net_kg": net, "expected_kg": expected, "deviation_pct": deviation_pct,
                "plausible": deviation_pct < 20}

    async def classify_material(self, rfid: str) -> str:
        """Subagent: MaterialClassifier."""
        return "Beton C30/37"  # Production: RFID→Material lookup

    async def read(self, rfid: str, gross_kg: float, tare_kg: float,
                   expected_kg: float = 0) -> dict:
        """Main: process one truck scale reading."""
        truck_id = await self.extract_truck_id(rfid)
        weight = await self.validate_weight(gross_kg, tare_kg, expected_kg)
        material = await self.classify_material(rfid)
        print(f"  [IoT-Scale]     ⚖  {truck_id}: {weight['net_kg']:.0f}kg {material} "
              f"(Δ={weight['deviation_pct']}%)")
        return {"truck_id": truck_id, **weight, "material": material,
                "timestamp": datetime.now(timezone.utc).isoformat()}


# ============================================================
# Agent 3: PhotoEvidenceAgent
# ============================================================


class PhotoEvidenceAgent:
    """Receives site photos, extracts EXIF, creates content hash."""

    async def extract_exif(self, photo_bytes: bytes) -> dict:
        """Subagent: EXIFExtractor."""
        return {"gps": (52.376, 9.732), "taken_at": datetime.now(timezone.utc).isoformat(),
                "camera": "Samsung Galaxy S24"}

    async def hash_image(self, photo_bytes: bytes) -> str:
        """Subagent: ImageHasher — SHA-256 of pixel data."""
        return hashlib.sha256(photo_bytes).hexdigest()[:40]

    async def normalize_metadata(self, exif: dict) -> dict:
        """Subagent: MetadataNormalizer — strips sensitive personal data."""
        return {k: v for k, v in exif.items() if k not in ("camera_serial", "owner")}

    async def process(self, photo_bytes: bytes, position_id: str) -> dict:
        """Main: process one site photo."""
        exif = await self.extract_exif(photo_bytes)
        image_hash = await self.hash_image(photo_bytes)
        meta = await self.normalize_metadata(exif)
        print(f"  [Photo-Evidence] 📸 {position_id}: hash={image_hash[:16]}...")
        return {"position_id": position_id, "image_hash": image_hash,
                "metadata": meta, "timestamp": datetime.now(timezone.utc).isoformat()}


# ============================================================
# Agent 4: SubcontractorValidatorAgent
# ============================================================


class SubcontractorValidatorAgent:
    """Verifies that on-site workers' DIDs match the approved subcontractor list."""

    async def match_did(self, worker_did: str, approved_list: list[str]) -> dict:
        """Subagent: DIDRegistryMatcher."""
        matched = any(worker_did[:16] in a for a in approved_list)
        return {"worker_did": worker_did[:20] + "...", "approved": matched}

    async def notify_deviation(self, worker_did: str) -> None:
        """Subagent: SubcontractorNotifier."""
        print(f"  [Subcontractor] ⚠ Unbekannte DID auf Baustelle: {worker_did[:20]}...")

    async def validate(self, workers: list[str], approved: list[str]) -> dict:
        """Main: check all on-site workers against approved subcontractor list."""
        results = []
        for did in workers:
            result = await self.match_did(did, approved)
            if not result["approved"]:
                await self.notify_deviation(did)
            results.append(result)
        approved_count = sum(1 for r in results if r["approved"])
        print(f"  [Subcontractor] ✓ {approved_count}/{len(workers)} Arbeiter autorisiert")
        return {"total": len(workers), "approved": approved_count, "results": results}


# ============================================================
# Agent 5: ProgressAggregatorAgent
# ============================================================


class ProgressAggregatorAgent:
    """Fuses GPS, scale, and photo data into a unified progress index per LV position."""

    async def weighted_score(self, gps: dict, scales: list, photos: list,
                             positions: list[dict]) -> float:
        """Subagent: WeightedScoreCalculator — GPS (0.3) + Scales (0.5) + Photos (0.2)."""
        gps_score = gps.get("presence_pct", 0) * 0.3
        scale_score = min(100, sum(s.get("net_kg", 0) for s in scales) /
                          max(sum(p.get("quantity", 1) * 100 for p in positions), 1)) * 0.5
        photo_score = min(100, len(photos) / max(len(positions), 1) * 20) * 0.2
        total = round(gps_score + scale_score + photo_score, 1)
        return total

    async def detect_outliers(self, telemetry: dict) -> list[str]:
        """Subagent: OutlierDetector."""
        return []  # Production: statistical outlier detection

    async def smooth(self, progress_pct: float, history: list[float]) -> float:
        """Subagent: ProgressSmoother — dampens weather-related variance."""
        if not history:
            return progress_pct
        return round(0.7 * progress_pct + 0.3 * sum(history)/len(history), 1)

    async def aggregate(self, gps: dict, scales: list[dict], photos: list[dict],
                        positions: list[dict], history: list[float] | None = None) -> dict:
        """Main: produce unified progress index."""
        progress = await self.weighted_score(gps, scales, photos, positions)
        progress = await self.smooth(progress, history or [])
        outliers = await self.detect_outliers({"gps": gps, "scales": scales, "photos": photos})
        print(f"  [ProgressAggr]  📊 Baufortschritt: {progress}% "
              f"(GPS={gps.get('presence_pct',0)}%, "
              f"Waagen={len(scales)}, Fotos={len(photos)})")
        return {"progress_pct": progress, "outliers": outliers,
                "timestamp": datetime.now(timezone.utc).isoformat()}


# ============================================================
# Agent 6: PoPWProofGeneratorAgent
# ============================================================


class MerkleTreeBuilder:
    """Subagent: Builds a Merkle tree from a list of hex hashes."""

    @staticmethod
    def build_root(leaf_hashes: list[str]) -> str:
        if not leaf_hashes:
            return "0" * 64
        if len(leaf_hashes) == 1:
            return leaf_hashes[0]
        new_level = []
        for i in range(0, len(leaf_hashes), 2):
            left = leaf_hashes[i]
            right = leaf_hashes[i + 1] if i + 1 < len(leaf_hashes) else left
            new_level.append(hashlib.sha256((left + right).encode()).hexdigest())
        return MerkleTreeBuilder.build_root(new_level)


class PoPWProofGeneratorAgent:
    """Generates Merkle-root PoPW proofs from aggregated telemetry."""

    async def build_merkle_tree(self, leaves: dict[str, str]) -> dict:
        """Subagent: MerkleTreeBuilder — returns root + leaves."""
        root = MerkleTreeBuilder.build_root(list(leaves.values()))
        return {"merkle_root": root, "leaves": leaves, "leaf_count": len(leaves)}

    async def prepare_zk(self, proof: dict) -> dict:
        """Subagent: ZKSNARKPrepareSubagent — prepares for zero-knowledge submission."""
        return {"zkp_ready": True, "circuit": "popw_proof"}

    async def sign_proof(self, proof: dict, agent_key: str = "AGENT-X-KEY") -> str:
        """Subagent: ProofSigner — signs with agent key."""
        return hashlib.sha256((json.dumps(proof, sort_keys=True) + agent_key).encode()).hexdigest()[:40]

    async def generate(self, project_id: str, installment_no: int,
                       telemetry: dict) -> dict:
        """Main: create Merkle root PoPW proof for chain anchoring."""
        # Hash the three telemetry streams
        leaves = {
            "gps": hashlib.sha256(json.dumps(telemetry.get("gps", {}), sort_keys=True).encode()).hexdigest(),
            "scales": hashlib.sha256(json.dumps(telemetry.get("scales", []), sort_keys=True, default=str).encode()).hexdigest(),
            "photos": hashlib.sha256(json.dumps(telemetry.get("photos", []), sort_keys=True, default=str).encode()).hexdigest(),
        }
        merkle = await self.build_merkle_tree(leaves)
        proof_id = f"0xPoPW-{merkle['merkle_root'][:16]}"
        sig = await self.sign_proof(merkle)
        proof = {
            "project_id": project_id, "installment_no": installment_no,
            "proof_id": proof_id, "merkle_root": merkle["merkle_root"],
            "leaves": merkle["leaves"], "signature": sig,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.prepare_zk(proof)
        print(f"  [PoPW-Proof]    🔐 Merkle-Root: {merkle['merkle_root'][:24]}... "
              f"(proof={proof_id[:20]}...)")
        return proof


# ============================================================
# Agent 7: PoPWVerifierAgent
# ============================================================


class PoPWVerifierAgent:
    """Verifies on-chain PoPW proofs against stored telemetry."""

    async def query_chain(self, proof_id: str) -> dict | None:
        """Subagent: ChainQuery — reads the anchored hash."""
        return {"proof_id": proof_id, "anchored_hash": None,
                "block": 0}  # Production: calls MultiChainAnchorAgent

    async def verify_merkle(self, root: str, leaves: dict, proof: dict) -> bool:
        """Subagent: MerkleVerifier — rebuilds tree and compares root."""
        rebuilt = MerkleTreeBuilder.build_root(list(leaves.values()))
        return rebuilt == proof.get("merkle_root", "")

    async def check_integrity(self, on_chain: dict, local: dict) -> dict:
        """Subagent: IntegrityCheck."""
        match = on_chain.get("anchored_hash") == local.get("merkle_root")
        return {"match": match, "anchored_block": on_chain.get("block", 0)}

    async def verify(self, proof: dict) -> dict:
        """Main: verify a PoPW proof against the chain."""
        on_chain = await self.query_chain(proof["proof_id"])
        merkle_ok = await self.verify_merkle(proof["merkle_root"], proof["leaves"], proof)
        integrity = await self.check_integrity(on_chain or {}, proof)
        all_ok = merkle_ok and integrity.get("match", False)
        print(f"  [PoPW-Verifier] {'✅' if all_ok else '❌'} "
              f"Proof {proof['proof_id'][:20]}... verified on-chain")
        return {"verified": all_ok, "merkle_ok": merkle_ok, **integrity}


# ============================================================
# Agent 8: DailyReportAgent
# ============================================================


class DailyReportAgent:
    """Generates machine-readable daily construction reports from telemetry."""

    async def format_report(self, date: str, telemetry: dict, progress: dict) -> str:
        """Subagent: ReportFormatter — JSON output."""
        return json.dumps({"date": date, "progress": progress, "telemetry_summary": {
            "gps_workers": len(telemetry.get("gps", {}).get("workers", [])),
            "scale_readings": len(telemetry.get("scales", [])),
            "photos_taken": len(telemetry.get("photos", [])),
        }}, indent=2)

    async def compute_statistics(self, telemetry: dict) -> dict:
        """Subagent: SummaryStatistics."""
        scales = telemetry.get("scales", [])
        total_kg = sum(s.get("net_kg", 0) for s in scales)
        return {"total_material_kg": total_kg, "scale_readings": len(scales)}

    async def export_pdf(self, report_json: str) -> str:
        """Subagent: PDFExporter."""
        return f"daily_report_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"

    async def generate(self, project_id: str, telemetry: dict, progress: dict) -> dict:
        """Main: produce daily report."""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        report = await self.format_report(date_str, telemetry, progress)
        stats = await self.compute_statistics(telemetry)
        pdf_name = await self.export_pdf(report)
        print(f"  [DailyReport]   📋 Tagesbericht {date_str}: "
              f"{stats['scale_readings']} Waagen-Lesungen, "
              f"{stats['total_material_kg']:.0f} kg Material")
        return {"report_json": report, "pdf": pdf_name, "stats": stats}


# ============================================================
# Agent 9: EmergencyStopAgent
# ============================================================


class EmergencyStopAgent:
    """Monitors telemetry for critical anomalies, triggers payment halt."""

    async def detect_anomaly(self, telemetry: dict) -> list[dict]:
        """Subagent: AnomalyDetector — statistical outlier detection."""
        anomalies = []
        gps = telemetry.get("gps", {})
        if gps.get("presence_pct", 100) < 20:
            anomalies.append({"type": "LOW_PRESENCE", "value": gps["presence_pct"],
                             "threshold": 20, "severity": "critical"})
        for s in telemetry.get("scales", []):
            if s.get("deviation_pct", 0) > 50:
                anomalies.append({"type": "WEIGHT_DEVIATION", "truck": s.get("truck_id"),
                                 "deviation_pct": s["deviation_pct"], "severity": "high"})
        return anomalies

    async def check_safety(self, telemetry: dict) -> list[str]:
        """Subagent: SafetyNetSubagent."""
        return []  # Production: safety protocol checks

    async def escalate(self, project_id: str, anomalies: list[dict]) -> None:
        """Subagent: EscalationMailer."""
        for a in anomalies:
            print(f"  [EmergencyStop] ⛔ {a['type']}: {a.get('value', a.get('deviation_pct'))} "
                  f"(severity={a['severity']}) — ALARM an Bauleitung!")

    async def monitor(self, project_id: str, telemetry: dict) -> dict:
        """Main: monitor telemetry and trigger halt if needed."""
        anomalies = await self.detect_anomaly(telemetry)
        safety = await self.check_safety(telemetry)
        if anomalies or safety:
            await self.escalate(project_id, anomalies)
            return {"halt": True, "anomalies": anomalies, "safety_issues": safety}
        print(f"  [EmergencyStop] ✅ Keine Anomalien — Betrieb normal")
        return {"halt": False, "anomalies": [], "safety_issues": []}


# ============================================================
# Telemetry Pipeline — 9 Agents in Sequence
# ============================================================


class TelemetryPipeline:
    """Wires all 9 telemetry agents into a daily collection cycle."""

    def __init__(self):
        self.gps = GPSCollectorAgent()
        self.scale = IoTScaleReaderAgent()
        self.photo = PhotoEvidenceAgent()
        self.subcontractor = SubcontractorValidatorAgent()
        self.progress_aggr = ProgressAggregatorAgent()
        self.proof_gen = PoPWProofGeneratorAgent()
        self.proof_verify = PoPWVerifierAgent()
        self.daily_report = DailyReportAgent()
        self.emergency = EmergencyStopAgent()
        self._history: list[float] = []

    async def run_daily_cycle(
        self, project_id: str, positions: list[dict],
        worker_dids: list[str], approved_subs: list[str],
        scale_readings: list[dict], photo_hashes: list[str],
        site_gps: tuple = (52.376, 9.732),
    ) -> dict:
        """Run one complete daily telemetry collection cycle."""
        start = time.perf_counter()

        # 1-3: Raw data collection
        gps_data = await self.gps.collect(worker_dids[0] if worker_dids else "unknown",
                                          [{"lat": site_gps[0], "lon": site_gps[1], "ts": time.time()}], site_gps)
        scale_data = [await self.scale.read(r.get("rfid", "T-001"), r.get("gross", 24000),
                                             r.get("tare", 12000), r.get("expected", 12000))
                      for r in scale_readings] if scale_readings else []
        photo_data = [await self.photo.process(b"mock_photo", p.get("position_id", "LV-0001"))
                      for p in positions[:2]]  # First 2 positions photographed

        # 4: Subcontractor validation
        sub_result = await self.subcontractor.validate(worker_dids, approved_subs)

        # 5: Progress aggregation
        telemetry = {"gps": gps_data, "scales": scale_data, "photos": photo_data}
        progress = await self.progress_aggr.aggregate(gps_data, scale_data, photo_data, positions, self._history)
        self._history.append(progress["progress_pct"])

        # 6-7: PoPW proof generation + verification
        proof = await self.proof_gen.generate(project_id, len(self._history), telemetry)
        verification = await self.proof_verify.verify(proof)

        # 8: Daily report
        report = await self.daily_report.generate(project_id, telemetry, progress)

        # 9: Emergency stop check
        emergency = await self.emergency.monitor(project_id, telemetry)

        elapsed = time.perf_counter() - start
        print(f"\n  [Telemetry]     ✅ Tageszyklus in {elapsed:.1f}s "
              f"(GPS={'✓' if gps_data['presence_pct']>50 else '⚠'}, "
              f"Waagen={len(scale_data)}, Fotos={len(photo_data)}, "
              f"Fortschritt={progress['progress_pct']}%, "
              f"Proof={'✓' if verification['verified'] else '⚠'}, "
              f"Emergency={'⛔' if emergency['halt'] else '✓'})")

        return {
            "gps": gps_data, "scales": scale_data, "photos": photo_data,
            "subcontractors": sub_result, "progress": progress,
            "proof": proof, "verification": verification,
            "report": report, "emergency": emergency,
        }
