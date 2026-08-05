"""
Redis-Bridge – übersetzt Redis-Jobs in Aufrufe der Agent 140-143.

Agent-Mapping:
  sakral  → Agent 140 (Storage-Orchestrator) – Sound-Dateien
  motorik → Agent 141 (Seafile-Connector)     – Drum-Samples / MIDI
  effekte → Agent 142 (Medien-Archivar)        – Effekt-Presets
  master  → Agent 143 (Speicher-Wächter)       – Mastering-Ziele
"""

import logging
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from agent_x_storage import STORAGE_LAYERS, check_usage, generate_report
    from agent_x_seafile import SeafileBridge
except ImportError as e:
    logging.warning("Agenten-Import fehlgeschlagen: %s", e)

logger = logging.getLogger("redis_bridge")

# ─── Agent-140: Sakral-Sounds ─────────────────────────────────

SAKRAL_BASE = Path("/Volumes/THX_CORE_16TB/media/audio/chorales")


class SakralBridge:
    """Agent 140 – Sound-Dateien auf RAID/HDD."""

    @staticmethod
    def get(identifier: str) -> Optional[str]:
        """Sucht eine Sound-Datei nach Identifier: 'orgel:dorian_slow'."""
        parts = identifier.split(":", 1)
        subdir = parts[0] if len(parts) > 1 else ""
        name = parts[-1]

        search_dir = SAKRAL_BASE / subdir if subdir else SAKRAL_BASE
        if not search_dir.exists():
            return None

        for ext in (".wav", ".flac", ".mp3", ".aiff"):
            for f in search_dir.glob(f"*{name}*{ext}"):
                logger.info("Sakral get: %s → %s", identifier, f)
                return str(f)

        # Fallback: rekursiv
        for f in SAKRAL_BASE.rglob(f"*{name}*"):
            if f.suffix in (".wav", ".flac", ".mp3", ".aiff"):
                return str(f)
        return None

    @staticmethod
    def list_resources(category: Optional[str] = None) -> list:
        root = SAKRAL_BASE / category if category else SAKRAL_BASE
        if not root.exists():
            return []
        return sorted(str(p) for p in root.rglob("*") if p.is_file())


# ─── Agent-141: Motorik (Drum-Samples / MIDI) ───────────────

MOTORIK_BASE = Path("/Volumes/THX_CORE_16TB/media/audio/samples")


class MotorikBridge:
    """Agent 141 – Drum-Samples und MIDI-Grooves auf RAID."""

    @staticmethod
    def get(identifier: str) -> Optional[str]:
        parts = identifier.split(":", 1)
        subdir = parts[0] if len(parts) > 1 else ""
        name = parts[-1]

        search_dir = MOTORIK_BASE / subdir if subdir else MOTORIK_BASE
        if not search_dir.exists():
            return None

        for f in search_dir.glob(f"*{name}*"):
            if f.suffix in (".wav", ".flac", ".mp3", ".mid", ".midi"):
                return str(f)
        for f in MOTORIK_BASE.rglob(f"*{name}*"):
            if f.suffix in (".wav", ".flac", ".mp3", ".mid", ".midi"):
                return str(f)
        return None

    @staticmethod
    def list_resources(category: Optional[str] = None) -> list:
        root = MOTORIK_BASE / category if category else MOTORIK_BASE
        if not root.exists():
            return []
        return sorted(str(p) for p in root.rglob("*") if p.is_file())


# ─── Agent-142: Effekte (Presets) ────────────────────────────

EFFEKTE_BASE = Path("/Volumes/THX_CORE_16TB/data/presets")


class EffekteBridge:
    """Agent 142 – Effekt-Presets als JSON."""

    @staticmethod
    def get_preset(effect_type: str, name: str) -> Optional[dict]:
        import json

        preset_file = EFFEKTE_BASE / effect_type / f"{name}.json"
        if preset_file.exists():
            with open(preset_file) as f:
                return json.load(f)

        # Fallback: rekursive Suche
        for f in EFFEKTE_BASE.rglob(f"{name}.json"):
            with open(f) as fh:
                return json.load(fh)
        return None

    @staticmethod
    def list_resources(category: Optional[str] = None) -> list:
        root = EFFEKTE_BASE / category if category else EFFEKTE_BASE
        if not root.exists():
            return []
        return sorted(str(p) for p in root.rglob("*.json"))


# ─── Agent-143: Mastering ───────────────────────────────────

MASTER_BASE = Path("/Volumes/THX_CORE_16TB/data/mastering")


class MasterBridge:
    """Agent 143 – Mastering-Zielwerte."""

    DEFAULTS = {
        "sakral_motorik": {
            "loudness_target_lufs": -16.0,
            "true_peak_dbtp": -1.5,
            "crest_factor_min": 12.0,
        },
        "sakral": {
            "loudness_target_lufs": -18.0,
            "true_peak_dbtp": -2.0,
            "crest_factor_min": 14.0,
        },
        "motorik": {
            "loudness_target_lufs": -14.0,
            "true_peak_dbtp": -1.0,
            "crest_factor_min": 10.0,
        },
    }

    @staticmethod
    def get_target(genre: str = "sakral_motorik") -> dict:
        import json

        target_file = MASTER_BASE / f"{genre}.json"
        if target_file.exists():
            with open(target_file) as f:
                return json.load(f)
        return MasterBridge.DEFAULTS.get(genre, MasterBridge.DEFAULTS["sakral_motorik"])

    @staticmethod
    def list_resources(category: Optional[str] = None) -> list:
        if not MASTER_BASE.exists():
            return []
        return sorted(str(p) for p in MASTER_BASE.glob("*.json"))


# ─── Router ──────────────────────────────────────────────────

BRIDGES = {
    "sakral": SakralBridge(),
    "motorik": MotorikBridge(),
    "effekte": EffekteBridge(),
    "master": MasterBridge(),
}


def dispatch(agent_type: str, action: str, payload: dict) -> dict:
    """Leitet einen Job an die richtige Bridge-Methode weiter."""
    bridge = BRIDGES.get(agent_type)
    if not bridge:
        return {"status": "error", "error": f"Unbekannter Agent: {agent_type}"}

    method = getattr(bridge, action, None)
    if not method:
        return {"status": "error", "error": f"Unbekannte Aktion: {action}"}

    try:
        if action == "get":
            path = method(payload.get("identifier", ""))
            return {"status": "success" if path else "not_found", "path": path}
        elif action == "get_preset":
            preset = method(payload.get("effect_type", ""), payload.get("name", ""))
            return {"status": "success" if preset else "not_found", "preset": preset}
        elif action == "get_target":
            target = method(payload.get("genre", "sakral_motorik"))
            return {"status": "success", "target": target}
        elif action == "list":
            resources = method(payload.get("category"))
            return {"status": "success", "resources": resources}
        else:
            return {"status": "error", "error": f"Unbekannte Aktion: {action}"}
    except Exception as e:
        logger.error("Dispatch-Fehler %s.%s: %s", agent_type, action, e)
        return {"status": "error", "error": str(e)}
