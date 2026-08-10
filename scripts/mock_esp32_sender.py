#!/usr/bin/env python3
"""Mock ESP32 Sensor Sender — for pitch demos without hardware.

Simulates an ESP32 sending DHT22 temperature/humidity readings
with hardware signatures via HTTP to the Telemetry Ingest service.

Usage:
  python3 scripts/mock_esp32_sender.py              # Send 50 events (default)
  python3 scripts/mock_esp32_sender.py 200          # Send 200 events
  python3 scripts/mock_esp32_sender.py 100 0.1      # 100 events, 100ms interval
"""

import hashlib
import hmac
import json
import random
import sys
import time
import urllib.request

DEVICE_ID = "ESP32_DEMO_01"
SECRET = "DEMO_SECRET_2026"
INGEST_URL = "http://localhost:8000/telemetry/ingest"


def sign(payload: dict) -> str:
    """Create HMAC-SHA256 hardware signature."""
    sorted_str = json.dumps(
        {k: v for k, v in sorted(payload.items())}, separators=(",", ":")
    )
    return hmac.new(SECRET.encode(), sorted_str.encode(), hashlib.sha256).hexdigest()


def send_event(temp: float, humidity: float) -> dict:
    """Send one sensor event to the ingest service."""
    payload = {
        "device_id": DEVICE_ID,
        "temperature": round(temp, 2),
        "humidity": round(humidity, 1),
        "timestamp": int(time.time() * 1000),
    }
    payload["signature"] = sign(payload)

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        INGEST_URL, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        return {"status": "error", "message": str(e)}


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5

    print(f"\n📡 Mock ESP32 Sender — {DEVICE_ID}")
    print(f"   Events: {count} | Interval: {interval}s | Target: {INGEST_URL}\n")

    sent = 0
    batches = 0

    for i in range(count):
        temp = round(random.uniform(18.0, 22.0), 2)
        humidity = round(random.uniform(40.0, 60.0), 1)

        result = send_event(temp, humidity)
        sent += 1

        status = result.get("status", "?")
        fill = result.get("buffer_fill", 0)
        if status == "batch_created":
            batches += 1
            proof = result.get("proof_hash", "")[:12]
            print(f"  [{i+1:>4}/{count}] {temp}°C {humidity}% → 📦 BATCH! proof={proof}")
        else:
            print(f"  [{i+1:>4}/{count}] {temp}°C {humidity}% → buffered ({fill}/100)")

        time.sleep(interval)

    print(f"\n✅ Done: {sent} events sent, {batches} batches triggered\n")


if __name__ == "__main__":
    main()
