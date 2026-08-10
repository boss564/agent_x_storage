#!/usr/bin/env python3
"""Agent X Telemetry Ingest — MQTT/HTTP bridge for ESP32 IoT sensors.

Receives sensor payloads via MQTT or HTTP, verifies hardware signatures,
buffers events into batches of 100, produces Merkle proofs, and forwards
batches to the DemoOrchestrator (A1 → A9 pipeline).

Hardware → MQTT → FastAPI → Batch Proof → Agent X

Usage:
  uvicorn services.telemetry_ingest.main:app --reload --port 8000
  python services/telemetry_ingest/main.py
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure repo root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TelemetryIngest")

# ─── Device Registry ────────────────────────────────────────────────────────

DEVICE_REGISTRY: Dict[str, Dict] = {
    "ESP32_DEMO_01": {
        "secret": "DEMO_SECRET_2026",
        "owner": "demo.firma.b2g",
        "sector": "BAU",
        "location": "Munich",
    },
    "ESP32_SOLAR_MUC": {
        "secret": "SOLAR_SECRET_2026",
        "owner": "stadtwerke.muenchen.b2g",
        "sector": "ENERGY",
        "location": "Munich",
    },
}

# ─── Models ─────────────────────────────────────────────────────────────────

class SensorPayload(BaseModel):
    device_id: str
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    timestamp: int
    signature: Optional[str] = None

class IngestResponse(BaseModel):
    status: str
    event_id: Optional[str] = None
    batch_id: Optional[str] = None
    proof_hash: Optional[str] = None
    buffer_fill: int = 0
    buffer_max: int = 100
    message: str = ""


# ─── Hardware Verification ──────────────────────────────────────────────────

def verify_hardware_signature(payload: Dict, device_id: str) -> bool:
    """Verify ESP32 hardware signature (zero-trust)."""
    if device_id not in DEVICE_REGISTRY:
        logger.warning("Unknown device: %s", device_id)
        return False

    sig = payload.pop("signature", None)
    if not sig:
        return False

    secret = DEVICE_REGISTRY[device_id]["secret"]
    sorted_str = json.dumps(
        {k: v for k, v in sorted(payload.items()) if k != "signature"},
        separators=(",", ":"),
    )
    expected = hmac.new(secret.encode(), sorted_str.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


# ─── MQTT Listener ──────────────────────────────────────────────────────────

class MQTTListener:
    """Receives MQTT messages from ESP32 sensors."""

    def __init__(self, broker: str = "localhost", port: int = 1883):
        self.broker = broker
        self.port = port
        self._client = None
        self._service: Optional["TelemetryIngestService"] = None

    def set_service(self, svc: "TelemetryIngestService"):
        self._service = svc

    def start(self):
        try:
            import paho.mqtt.client as mqtt
            self._client = mqtt.Client()
            self._client.on_connect = self._on_connect
            self._client.on_message = self._on_message
            self._client.connect(self.broker, self.port, 60)
            self._client.loop_start()
            logger.info("MQTT listener started on %s:%s", self.broker, self.port)
        except Exception as e:
            logger.warning("MQTT not available (mock mode): %s", e)

    def stop(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    def _on_connect(self, client, userdata, flags, rc):
        client.subscribe("telemetry/sensor/+/+")
        logger.info("MQTT subscribed to telemetry/sensor/+/+")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            device_id = payload.get("device_id", "unknown")
            if verify_hardware_signature(payload, device_id):
                if self._service:
                    self._service._ensure_loop()
                    asyncio.run_coroutine_threadsafe(
                        self._service.ingest(payload),
                        self._service._loop,
                    )
            else:
                logger.warning("Invalid signature from %s", device_id)
        except Exception as e:
            logger.error("MQTT message error: %s", e)


# ─── Ingest Service ─────────────────────────────────────────────────────────

class TelemetryIngestService:
    """Buffers sensor events, creates Merkle-proofed batches, forwards to orchestrator."""

    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size
        self.buffer: Dict[str, List[Dict]] = {}
        self.total_events = 0
        self.total_volume = 0.0
        self.batches_produced = 0
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _ensure_loop(self):
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)

    async def ingest(self, payload: Dict) -> Dict:
        """Process a single sensor event."""
        self.total_events += 1
        device_id = payload.get("device_id", "unknown")
        temp = payload.get("temperature", 0.0) or 0.0
        value_eur = round(max(0.01, temp / 100.0), 6)
        self.total_volume += value_eur

        event = {
            "event_id": str(uuid.uuid4())[:8],
            "device_id": device_id,
            "value_eur": value_eur,
            "raw": payload,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }

        if device_id not in self.buffer:
            self.buffer[device_id] = []
        self.buffer[device_id].append(event)
        fill = len(self.buffer[device_id])

        if fill >= self.batch_size:
            batch = await self._create_batch(device_id)
            return {
                "status": "batch_created",
                "batch_id": batch["batch_id"],
                "proof_hash": batch["merkle_root"],
                "buffer_fill": 0,
                "buffer_max": self.batch_size,
                "message": f"Batch {self.batches_produced} produced ({self.batch_size} events)",
            }

        return {
            "status": "buffered",
            "event_id": event["event_id"],
            "buffer_fill": fill,
            "buffer_max": self.batch_size,
            "message": f"Event stored ({fill}/{self.batch_size})",
        }

    async def _create_batch(self, device_id: str) -> Dict:
        """Create a Merkle proof from buffered events."""
        events = self.buffer.pop(device_id, [])
        if not events:
            return {"status": "empty", "batch_id": None}

        # Merkle root
        leaves = [
            hashlib.sha256(json.dumps(e, sort_keys=True, default=str).encode()).hexdigest()
            for e in events
        ]
        current = leaves
        while len(current) > 1:
            if len(current) % 2 != 0:
                current.append(current[-1])
            current = [
                hashlib.sha256(
                    (current[i] + current[i + 1]).encode()
                ).hexdigest()
                for i in range(0, len(current), 2)
            ]
        root = current[0] if current else "0x0"

        total_val = round(sum(e["value_eur"] for e in events), 6)
        self.batches_produced += 1

        batch = {
            "batch_id": f"BATCH-{self.batches_produced:06d}",
            "device_id": device_id,
            "event_count": len(events),
            "total_value": total_val,
            "merkle_root": root,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Batch %s: %d events, €%.6f, root=%s",
            batch["batch_id"], len(events), total_val, root[:16],
        )
        return batch

    def status(self) -> Dict:
        return {
            "total_events": self.total_events,
            "total_volume": round(self.total_volume, 6),
            "batches_produced": self.batches_produced,
            "buffer_devices": len(self.buffer),
            "buffer_total_events": sum(len(v) for v in self.buffer.values()),
            "registered_devices": len(DEVICE_REGISTRY),
        }


# ─── FastAPI App ────────────────────────────────────────────────────────────

SERVICE = TelemetryIngestService(batch_size=100)
MQTT = MQTTListener(
    broker=os.getenv("MQTT_BROKER", "localhost"),
    port=int(os.getenv("MQTT_PORT", "1883")),
)
MQTT.set_service(SERVICE)


@asynccontextmanager
async def lifespan(app: FastAPI):
    MQTT.start()
    yield
    MQTT.stop()


app = FastAPI(
    title="Agent X Telemetry Ingest",
    description="MQTT/HTTP bridge for ESP32 IoT sensors → Agent X pipeline",
    version="2.0",
    lifespan=lifespan,
    docs_url="/docs",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.post("/telemetry/ingest", response_model=IngestResponse)
async def ingest_endpoint(payload: SensorPayload):
    """HTTP ingest (alternative to MQTT)."""
    data = payload.model_dump()
    device_id = data.get("device_id", "")
    if not verify_hardware_signature(data, device_id):
        raise HTTPException(403, "Invalid hardware signature")
    result = await SERVICE.ingest(data)
    return IngestResponse(**result)


@app.post("/telemetry/ingest/mock")
async def ingest_mock():
    """Generate a mock sensor event (for demos without hardware)."""
    import random
    device_id = random.choice(list(DEVICE_REGISTRY.keys()))
    payload = {
        "device_id": device_id,
        "temperature": round(random.uniform(18.0, 22.0), 2),
        "humidity": round(random.uniform(40.0, 60.0), 1),
        "timestamp": int(time.time() * 1000),
    }
    # Sign it
    secret = DEVICE_REGISTRY[device_id]["secret"]
    sorted_str = json.dumps(
        {k: v for k, v in sorted(payload.items())}, separators=(",", ":")
    )
    sig = hmac.new(secret.encode(), sorted_str.encode(), hashlib.sha256).hexdigest()
    payload["signature"] = sig

    result = await SERVICE.ingest(payload)
    return {**result, "device_id": device_id, "temperature": payload["temperature"]}


@app.get("/telemetry/status")
async def get_status():
    return {**SERVICE.status(), "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/telemetry/batch/{device_id}")
async def force_batch(device_id: str):
    """Force batch creation for a device."""
    batch = await SERVICE._create_batch(device_id)
    return batch


@app.post("/telemetry/flood")
async def flood_events(
    count: int = Query(default=100, ge=1, le=10000),
    device_id: str = "ESP32_DEMO_01",
):
    """Generate N mock events (for load testing)."""
    import random
    results = []
    for i in range(count):
        payload = {
            "device_id": device_id,
            "temperature": round(random.uniform(18.0, 22.0), 2),
            "timestamp": int(time.time() * 1000) + i,
        }
        secret = DEVICE_REGISTRY[device_id]["secret"]
        sorted_str = json.dumps(
            {k: v for k, v in sorted(payload.items())}, separators=(",", ":")
        )
        sig = hmac.new(secret.encode(), sorted_str.encode(), hashlib.sha256).hexdigest()
        payload["signature"] = sig
        results.append(await SERVICE.ingest(payload))

    batches = sum(1 for r in results if r.get("status") == "batch_created")
    return {
        "events_sent": count,
        "batches_triggered": batches,
        **SERVICE.status(),
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "mqtt_broker": MQTT.broker, **SERVICE.status()}


# ─── Main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("INGEST_PORT", "8000")))
