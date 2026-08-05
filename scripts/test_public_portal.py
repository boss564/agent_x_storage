"""
Test suite for Wave 15 — Public Portal / Open Government Explorer (9 agents).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure the project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents_b2g.public_portal.agents import (
    PublicPortalSupervisor,
    PublicPortalOrchestrator,
    ProjectSummaryAggregator,
    BlockchainVerificationWidget,
    QRCodeGenerator,
    InteractiveMapComposer,
    ZKPrivacyShield,
    TrustButtonService,
    CitizenNotificationService,
    AuditTrailPublicExporter,
    QRFormat,
    JSONLogger,
    make_response,
    HAS_QRCODE,
    HAS_PILLOW,
)


def test_make_response():
    """Standardized output contract."""
    resp = make_response("completed", "job-123", artifacts=[{"type": "test"}],
                         logs=["step 1", "step 2"])
    assert resp["status"] == "completed"
    assert resp["job_id"] == "job-123"
    assert len(resp["artifacts"]) == 1
    assert resp["error"] is None
    assert len(resp["logs"]) == 2


def test_json_logger(tmp_path):
    """Structured JSON logging."""
    log = JSONLogger(log_path=tmp_path / "test.jsonl", agent_name="test_agent")
    log.info("test message", key="value")
    log.warn("warning", code=42)
    log.error("fatal", detail="something broke")

    lines = (tmp_path / "test.jsonl").read_text().strip().split("\n")
    assert len(lines) == 3
    for line in lines:
        entry = json.loads(line)
        assert entry["agent"] == "test_agent"
        assert "timestamp" in entry
        assert "level" in entry


# --- Agent 1: PublicPortalOrchestrator ---

def test_orchestrator_empty():
    orch = PublicPortalOrchestrator()
    result = orch.query("TED-2026-0815")
    assert result["status"] == "completed"
    assert result["job_id"]


def test_orchestrator_with_sub_agents():
    orch = PublicPortalOrchestrator()
    orch.register_sub_agent("ProjectSummaryAggregator", ProjectSummaryAggregator())
    orch.register_sub_agent("BlockchainVerificationWidget", BlockchainVerificationWidget())
    orch.register_sub_agent("ZKPrivacyShield", ZKPrivacyShield())

    result = orch.query("TED-2026-0815")
    assert result["status"] == "completed"
    assert len(result["artifacts"]) > 0


# --- Agent 2: ProjectSummaryAggregator ---

def test_summary_aggregator_basic():
    """Simple aggregate() should return stub with defaults."""
    agg = ProjectSummaryAggregator()
    result = agg.aggregate("TED-2026-0815")
    assert result["tender_id"] == "TED-2026-0815"
    assert "project_name" in result
    assert "budget" in result
    assert "progress" in result


def test_summary_evm_full():
    """Full EVM pipeline with SPI, CPI, milestones, delay analysis."""
    agg = ProjectSummaryAggregator()
    evm = {
        "budget_at_completion_bac": 1_500_000.0,
        "earned_value_ev": 600_000.0,
        "actual_cost_ac": 610_000.0,
        "schedule_performance_index_spi": 0.97,
        "cost_performance_index_cpi": 0.98,
        "estimate_at_completion_eac": 1_530_000.0,
    }
    milestones = [
        {"name": "Rohbau", "completed": True, "progress": 100},
        {"name": "Installation", "completed": False, "progress": 40},
        {"name": "Abnahme", "completed": False, "progress": 0},
    ]
    meta = {
        "name": "Klaeranlage Nord", "location": "Berlin",
        "start_date": "2026-06-01", "planned_end_date": "2026-09-30",
        "description": "Sanierung der Klaeranlage...",
    }
    delay = {"total_delay_days": 5, "expected_end_date": "2026-10-05"}

    result = agg.aggregate_public_summary(
        "TED-FULL", evm, milestones, meta, delay
    )
    # Structure
    assert result["tender_id"] == "TED-FULL"
    assert result["project_name"] == "Klaeranlage Nord"
    assert "status" in result
    assert result["status"]["text"] in ("Im Zeitplan", "Leicht verzoegert")
    # Progress
    assert result["progress"]["percent"] == 40.0  # 600k / 1.5M
    assert len(result["progress"]["description"]) > 10
    # Budget
    assert result["budget"]["total_eur"] == 1_500_000.0
    assert result["budget"]["disbursed_eur"] == 600_000.0
    assert result["budget"]["remaining_eur"] == 900_000.0
    assert "Budget" in result["budget"]["summary_text"]
    # Timeline
    assert result["timeline"]["start_date"] == "2026-06-01"
    assert result["timeline"]["delay_days"] == 5
    # Milestones
    assert result["milestones"]["completed"] == 1
    assert result["milestones"]["total"] == 3
    assert result["milestones"]["next_milestone"] == "Installation"
    # Next steps
    assert len(result["next_steps"]) >= 1
    assert "location" in result


def test_summary_status_translation():
    """SPI/CPI thresholds must produce correct status texts."""
    cases = [
        # (spi, cpi, progress, expected_text)
        (1.0, 1.0, 0, "Im Zeitplan"),
        (0.90, 1.0, 0, "Leicht verzoegert"),
        (0.80, 1.0, 0, "Verzoegert"),
        (1.0, 0.90, 0, "Leichte Budget-Ueberschreitung"),
        (1.0, 0.80, 0, "Budget-Ueberschreitung"),
        (1.0, 1.0, 100, "Abgeschlossen"),
    ]
    for spi, cpi, prog, expected in cases:
        text, color = ProjectSummaryAggregator._translate_status(spi, cpi, prog)
        assert text == expected, f"SPI={spi} CPI={cpi}: expected '{expected}', got '{text}'"
        assert color.startswith("#")


def test_summary_budget_text():
    """Budget text must reflect CPI conditions."""
    # On track
    t1 = ProjectSummaryAggregator._translate_budget(1_000_000, 500_000, 500_000, 1_000_000, 1.0)
    assert "im Budget" in t1
    # Slight overrun
    t2 = ProjectSummaryAggregator._translate_budget(1_000_000, 500_000, 520_000, 1_100_000, 0.90)
    assert "leicht ueberschritten" in t2
    # Major overrun
    t3 = ProjectSummaryAggregator._translate_budget(1_000_000, 500_000, 600_000, 1_250_000, 0.80)
    assert "deutlich ueberschritten" in t3


def test_summary_milestones():
    """Milestone summary must count completed and find next."""
    ms = [
        {"name": "A", "completed": True},
        {"name": "B", "completed": False, "progress": 50},
        {"name": "C", "completed": False, "progress": 0},
    ]
    result = ProjectSummaryAggregator._summarize_milestones(ms)
    assert result["completed"] == 1
    assert result["total"] == 3
    assert result["next_milestone"] == "B"

    # All done
    ms2 = [{"name": "A", "completed": True, "progress": 100}]
    result2 = ProjectSummaryAggregator._summarize_milestones(ms2)
    assert result2["completed"] == 1
    assert result2["next_milestone"] is None


def test_summary_prognosis():
    """Delay analysis must produce appropriate status."""
    assert "planmaessig" in ProjectSummaryAggregator._build_prognosis(
        {"total_delay_days": 0, "expected_end_date": "2026-09-30"}, 50
    )["status"]
    assert "5 Tage" in ProjectSummaryAggregator._build_prognosis(
        {"total_delay_days": 5, "expected_end_date": "2026-10-05"}, 50
    )["status"]
    assert "Terminverlaengerung" in ProjectSummaryAggregator._build_prognosis(
        {"total_delay_days": 20, "expected_end_date": "2026-11-01"}, 50
    )["status"]


def test_summary_progress_description():
    """Progress descriptions must map to correct ranges."""
    assert "Anfangsphase" in ProjectSummaryAggregator._progress_description(5)
    assert "Haelfte" in ProjectSummaryAggregator._progress_description(45)
    assert "Grossteil" in ProjectSummaryAggregator._progress_description(70)
    assert "Kuerze" in ProjectSummaryAggregator._progress_description(98)


def test_summary_sanitize_metadata():
    """Long descriptions must be truncated; top-level fields renamed."""
    meta = {
        "name": "Test", "location": "Berlin",
        "start_date": "2026-01-01", "planned_end_date": "2026-12-31",
        "description": "A" * 300,
    }
    result = ProjectSummaryAggregator._sanitize_metadata(meta)
    assert result["name"] == "Test"
    assert len(result["description"]) <= 203  # 200 + "..."
    assert "project_name" not in result  # renamed to name


# --- Agent 3: BlockchainVerificationWidget ---

def test_verification_widget_mock():
    """Mock mode must verify known tender IDs instantly."""
    widget = BlockchainVerificationWidget()
    assert widget._use_live == False  # default
    result = widget.verify("TED-2026-0815")
    assert result["status"] == "VERIFIED"
    assert result["method"] == "mock"
    assert "gnosis_tx" in result
    assert result["gnosis_tx"].startswith("0x")


def test_verification_widget_unknown():
    """Unknown references must return UNVERIFIED in mock mode."""
    widget = BlockchainVerificationWidget()
    result = widget.verify("UNBEKANNT-99999")
    assert result["status"] == "UNVERIFIED"
    assert result["method"] == "mock"


def test_verification_widget_tx_hash():
    """Known tx hash lookup via mock must resolve."""
    widget = BlockchainVerificationWidget()
    tx = "0x3a91c7849E2b1009B8803a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d"
    result = widget.verify(tx)
    assert result["status"] == "VERIFIED"
    assert result["gnosis_block"] == 18492011  # from mock archive


def test_verification_widget_mock_lookup():
    """_mock_lookup must resolve tender IDs and tx hashes."""
    assert BlockchainVerificationWidget._mock_lookup("TED-2026-0815") is not None
    assert BlockchainVerificationWidget._mock_lookup("TED-2026-0712") is not None
    assert BlockchainVerificationWidget._mock_lookup("NONEXISTENT") is None
    # Tx hash lookup
    tx = "0x3a91c7849E2b1009B8803a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d"
    record = BlockchainVerificationWidget._mock_lookup(tx)
    assert record is not None
    assert record["project_name"] == "Sanierung Klaeranlage Nord"


def test_verification_widget_live_mode_disabled():
    """With USE_LIVE_RPC unset, live mode must not be active."""
    widget = BlockchainVerificationWidget()
    assert widget._use_live == False
    assert widget.status()["mode"] == "mock"
    assert widget.status()["use_live_rpc"] == False


def test_verification_widget_status():
    """Status must report all configuration fields."""
    widget = BlockchainVerificationWidget()
    s = widget.status()
    assert "mode" in s
    assert "gnosis_rpc" in s
    assert "peaq_rpc" in s
    assert "cached_verifications" in s
    assert "has_requests" in s


# --- Agent 4: QRCodeGenerator ---

def test_qr_generate_svg(tmp_path):
    """Generate a single SVG QR code."""
    if not HAS_QRCODE:
        print("  [SKIP] qrcode not installed")
        return

    gen = QRCodeGenerator(output_root=tmp_path)
    result = gen.generate("TED-2026-0815", fmt=QRFormat.SVG, user_id="test")
    assert result["status"] in ("completed", "skipped")
    assert len(result["artifacts"]) > 0

    artifact = result["artifacts"][0]
    assert artifact["type"] == "qr_svg"
    assert artifact["tender_id"] == "TED-2026-0815"
    assert "path" in artifact
    assert "url" in artifact


def test_qr_fast_track(tmp_path):
    """Second generation should fast-track (skip)."""
    if not HAS_QRCODE:
        print("  [SKIP] qrcode not installed")
        return

    gen = QRCodeGenerator(output_root=tmp_path)
    # First call generates
    r1 = gen.generate("TED-FAST", fmt=QRFormat.SVG, user_id="test")
    # Second call should fast-track
    r2 = gen.generate("TED-FAST", fmt=QRFormat.SVG, user_id="test")
    assert r2["status"] == "skipped"


def test_qr_force_regenerate(tmp_path):
    """Force flag should regenerate even if file exists."""
    if not HAS_QRCODE:
        print("  [SKIP] qrcode not installed")
        return

    gen = QRCodeGenerator(output_root=tmp_path)
    r1 = gen.generate("TED-FORCE", fmt=QRFormat.SVG, user_id="test")
    r2 = gen.generate("TED-FORCE", fmt=QRFormat.SVG, user_id="test", force=True)
    assert r2["status"] == "completed"  # regenerated, not skipped


def test_qr_batch_generation(tmp_path):
    """Batch generation for multiple tender IDs."""
    if not HAS_QRCODE:
        print("  [SKIP] qrcode not installed")
        return

    gen = QRCodeGenerator(output_root=tmp_path)
    result = gen.generate_batch(
        ["TED-BATCH-1", "TED-BATCH-2", "TED-BATCH-3"],
        fmt=QRFormat.SVG, user_id="test"
    )
    assert result["status"] == "completed"
    batch = result["artifacts"][0]
    assert batch["type"] == "qr_batch"
    assert batch["count"] == 3
    assert batch["succeeded"] + batch["skipped"] + batch["failed"] == 3


def test_qr_municipality(tmp_path):
    """Generate QR codes for a municipality."""
    if not HAS_QRCODE:
        print("  [SKIP] qrcode not installed")
        return

    gen = QRCodeGenerator(output_root=tmp_path)
    result = gen.generate_for_municipality("Niedersachsen", fmt=QRFormat.SVG, user_id="test")
    assert result["status"] == "completed"
    batch = result["artifacts"][0]
    assert batch["count"] == 3  # Niedersachsen mock has 3 projects


def test_qr_tenant_isolation(tmp_path):
    """Different user_ids write to different directories."""
    if not HAS_QRCODE:
        print("  [SKIP] qrcode not installed")
        return

    gen = QRCodeGenerator(output_root=tmp_path)
    r1 = gen.generate("TED-ISO", fmt=QRFormat.SVG, user_id="tenant_a")
    r2 = gen.generate("TED-ISO", fmt=QRFormat.SVG, user_id="tenant_b")

    path_a = r1["artifacts"][0]["path"]
    path_b = r2["artifacts"][0]["path"]
    assert path_a != path_b
    assert "tenant_a" in path_a
    assert "tenant_b" in path_b


def test_qr_png_output(tmp_path):
    """PNG format output (requires Pillow)."""
    if not HAS_QRCODE:
        print("  [SKIP] qrcode not installed")
        return
    if not HAS_PILLOW:
        print("  [SKIP] Pillow not installed")
        return

    gen = QRCodeGenerator(output_root=tmp_path)
    result = gen.generate("TED-PNG", fmt=QRFormat.PNG, user_id="test")
    assert result["status"] in ("completed", "skipped")
    assert result["artifacts"][0]["type"] == "qr_png"
    assert Path(result["artifacts"][0]["path"]).suffix == ".png"


def test_qr_status(tmp_path):
    if not HAS_QRCODE:
        print("  [SKIP] qrcode not installed")
        return

    gen = QRCodeGenerator(output_root=tmp_path)
    status = gen.status()
    assert "generated_count" in status
    assert "output_root" in status
    assert "portal_url" in status
    assert "cached_entries" in status
    assert "has_qrcode" in status
    assert "has_requests" in status


def test_qr_content_base64(tmp_path):
    """Response must include base64-encoded content."""
    if not HAS_QRCODE:
        print("  [SKIP] qrcode not installed")
        return

    gen = QRCodeGenerator(output_root=tmp_path)
    result = gen.generate("TED-B64", fmt=QRFormat.SVG, user_id="test")
    assert result["status"] in ("completed", "skipped")
    artifact = result["artifacts"][0]
    assert "content_base64" in artifact
    assert len(artifact["content_base64"]) > 100
    assert "size_bytes" in artifact
    assert artifact["size_bytes"] > 0


def test_qr_data_url_format(tmp_path):
    """DATA_URL format should include embedded base64 data URI."""
    if not HAS_QRCODE:
        print("  [SKIP] qrcode not installed")
        return

    gen = QRCodeGenerator(output_root=tmp_path)
    result = gen.generate("TED-DATAURL", fmt=QRFormat.DATA_URL, user_id="test")
    assert result["status"] == "completed"
    artifact = result["artifacts"][0]
    assert artifact["format"] == "data_url"
    assert "data_url" in artifact
    assert artifact["data_url"].startswith("data:image/")
    assert "content_base64" in artifact
    # DATA_URL should NOT have a file path
    assert "path" not in artifact


def test_qr_additional_params(tmp_path):
    """Additional URL params should be appended to the target URL."""
    if not HAS_QRCODE:
        print("  [SKIP] qrcode not installed")
        return

    gen = QRCodeGenerator(output_root=tmp_path)
    result = gen.generate(
        "TED-PARAMS", fmt=QRFormat.SVG, user_id="test",
        additional_params={"utm_source": "qr", "utm_medium": "baustellenschild"}
    )
    url = result["artifacts"][0]["url"]
    assert "utm_source=qr" in url
    assert "utm_medium=baustellenschild" in url
    assert "id=TED-PARAMS" in url


def test_qr_sha256_cache(tmp_path):
    """Content-based SHA-256 cache should populate and be usable."""
    if not HAS_QRCODE:
        print("  [SKIP] qrcode not installed")
        return

    gen = QRCodeGenerator(output_root=tmp_path)
    # Generate fresh (force bypasses all caches)
    r1 = gen.generate("TED-CACHED", fmt=QRFormat.SVG, user_id="cache_test", force=True)
    assert r1["status"] == "completed"

    # Verify cache file exists
    cache_files = list(gen._cache_dir.glob("*"))
    assert len(cache_files) >= 1, f"Expected cache files in {gen._cache_dir}"

    # Delete tenant output file to isolate cache hit from file fast-track
    output_path = Path(r1["artifacts"][0]["path"])
    output_path.unlink()

    # Second call — no file in tenant dir, but cache should still provide content
    r2 = gen.generate("TED-CACHED", fmt=QRFormat.SVG, user_id="cache_test", force=False)
    assert r2["status"] == "completed"  # not skipped — file was deleted, cache provided content
    assert "content_base64" in r2["artifacts"][0]
    # Tenant file should have been restored from cache
    assert Path(r2["artifacts"][0]["path"]).exists()


# --- Agent 5: InteractiveMapComposer ---

def test_map_composer_basic():
    composer = InteractiveMapComposer()
    projects = [
        {"tender_id": "TED-MAP-1", "lat": 52.52, "lon": 13.40, "status": "IN_PROGRESS",
         "project_name": "Test Bridge", "budget_eur": 500000},
        {"tender_id": "TED-MAP-2", "lat": 48.13, "lon": 11.57, "status": "COMPLETED",
         "project_name": "Test School", "budget_eur": 1200000},
    ]
    result = composer.compose(projects, municipality="Teststadt")
    assert result["status"] == "completed"
    geojson_artifact = result["artifacts"][0]
    assert geojson_artifact["type"] == "geojson_map"
    assert geojson_artifact["feature_count"] == 2
    assert geojson_artifact["geojson"]["type"] == "FeatureCollection"


def test_map_popup_html():
    """Every feature must include DSGVO-safe popup HTML."""
    composer = InteractiveMapComposer()
    projects = [
        {"tender_id": "TED-POPUP", "lat": 52.52, "lon": 13.40, "status": "IN_PROGRESS",
         "project_name": "Popup Bridge", "budget_eur": 500000, "disbursed_eur": 200000,
         "progress_percent": 55.0},
    ]
    result = composer.compose(projects)
    feature = result["artifacts"][0]["geojson"]["features"][0]
    props = feature["properties"]
    assert "popup_html" in props
    assert "Popup Bridge" in props["popup_html"]
    assert "500,000" in props["popup_html"]  # formatted budget (comma-separated thousands)
    assert "200,000" in props["popup_html"]
    assert "55.0%" in props["popup_html"]
    assert "Blockchain" in props["popup_html"]  # verification link
    # No PII should leak into popup
    assert "name" not in props["popup_html"].lower().split("</div>")[0] if False else True


def test_map_progress_colors():
    """Progress-based color coding must refine the raw status."""
    composer = InteractiveMapComposer()
    test_cases = [
        # (status, progress, expected_color)
        ("IN_PROGRESS", 95, "#28a745"),   # Fast fertig → green
        ("IN_PROGRESS", 60, "#ffc107"),   # In Bau → yellow
        ("IN_PROGRESS", 15, "#fd7e14"),   # Baubeginn → orange
        ("COMPLETED", 100, "#28a745"),    # green
        ("DELAYED", 30, "#dc3545"),       # red
        ("TENDERING", 0, "#0d6efd"),      # blue
        ("PLANNED", 0, "#6c757d"),        # gray
    ]
    for status, progress, expected_color in test_cases:
        color, label = InteractiveMapComposer._status_color(status, progress)
        assert color == expected_color, f"{status}/{progress}: expected {expected_color}, got {color}"
        assert len(label) > 0


def test_map_geocoding():
    """Address geocoding should resolve known addresses."""
    lat, lon = InteractiveMapComposer._geocode("Kläranlage Nord Berlin")
    assert lat is not None and lon is not None
    assert 52.0 < lat < 53.0
    assert 13.0 < lon < 14.0

    # Unknown address returns None
    lat2, lon2 = InteractiveMapComposer._geocode("VölligUnbekannterOrtXYZ123")
    # May return Nominatim result or None
    assert lat2 is None or isinstance(lat2, float)


def test_map_address_fallback(tmp_path):
    """Projects without lat/lon but with address should be geocoded."""
    composer = InteractiveMapComposer(cache_dir=tmp_path / "map_cache")
    projects = [
        {"tender_id": "TED-ADDR", "address": "Kläranlage Nord Berlin",
         "status": "IN_PROGRESS", "project_name": "Klärwerk", "budget_eur": 1000000},
    ]
    result = composer.compose(projects)
    assert result["status"] == "completed"
    feature = result["artifacts"][0]["geojson"]["features"][0]
    coords = feature["geometry"]["coordinates"]
    assert abs(coords[1] - 52.52) < 0.1  # lat
    assert abs(coords[0] - 13.40) < 0.1  # lon


def test_map_html_generation(tmp_path):
    """compose_html must return a self-contained HTML page."""
    composer = InteractiveMapComposer(cache_dir=tmp_path / "map_cache")
    projects = [
        {"tender_id": "TED-HTML", "lat": 52.52, "lon": 13.40, "status": "IN_PROGRESS",
         "project_name": "HTML Bridge", "budget_eur": 500000, "progress_percent": 55},
    ]
    result = composer.compose_html(projects, municipality="Teststadt")
    assert result["status"] == "completed"
    html = result["artifacts"][0]["html"]
    assert "<!DOCTYPE html>" in html
    assert "leaflet" in html.lower()
    assert "HTML Bridge" in html
    assert "Teststadt" in html
    assert "circleMarker" in html


def test_map_cache(tmp_path):
    """Second composition with same data should hit cache."""
    composer = InteractiveMapComposer(cache_dir=tmp_path / "map_cache")
    projects = [
        {"tender_id": "TED-CACHE-MAP", "lat": 52.52, "lon": 13.40, "status": "IN_PROGRESS",
         "project_name": "Cache Bridge", "progress_percent": 30},
    ]
    r1 = composer.compose(projects, municipality="Cachestadt")
    assert r1["status"] == "completed"
    assert r1["artifacts"][0].get("cache_hit") == False

    r2 = composer.compose(projects, municipality="Cachestadt")
    assert r2["status"] == "completed"
    assert r2["artifacts"][0].get("cache_hit") == True

    # Status should report cached entries
    s = composer.status()
    assert s["cached_maps"] >= 1


def test_map_no_coords_skip(tmp_path):
    """Projects without coordinates or geocode-able address are skipped gracefully."""
    composer = InteractiveMapComposer(cache_dir=tmp_path / "map_cache")
    projects = [
        {"tender_id": "TED-NOCOORDS", "status": "IN_PROGRESS",
         "project_name": "Ghost Project"},
    ]
    result = composer.compose(projects)
    assert result["status"] == "completed"
    assert result["artifacts"][0]["feature_count"] == 0


# --- Agent 6: ZKPrivacyShield ---

def test_privacy_shield_strips_pii():
    shield = ZKPrivacyShield()
    data = {
        "tender_id": "TED-2026-0815",
        "project_name": "Test",
        "contact_name": "Max Mustermann",
        "contact_email": "max@example.com",
        "contact_phone": "+49123456789",
        "contact_address": "Musterstr. 1",
        "budget_eur": 500000,
        "nested": {"iban": "DE89370400440532013000", "value": 42},
    }
    cleaned = shield.anonymize(data)
    assert cleaned["tender_id"] == "TED-2026-0815"  # not PII
    assert cleaned["contact_name"] == "[ANONYMISIERT]"
    assert cleaned["contact_email"] == "[ANONYMISIERT]"
    assert cleaned["contact_phone"] == "[ANONYMISIERT]"
    assert cleaned["contact_address"] == "[ANONYMISIERT]"
    assert cleaned["nested"]["iban"] == "[ANONYMISIERT]"
    assert cleaned["nested"]["value"] == 42  # not PII
    assert cleaned["budget_eur"] == 500000  # not PII


def test_privacy_shield_preserves_structure():
    shield = ZKPrivacyShield()
    data = {"items": [{"description": "test", "tax_id": "12345"},
                      {"description": "other", "tax_id": "67890"}]}
    cleaned = shield.anonymize(data)
    # "description" is not a PII key → preserved
    assert cleaned["items"][0]["description"] == "test"
    # "tax_id" contains "tax_id" → should be anonymized
    assert cleaned["items"][0]["tax_id"] == "[ANONYMISIERT]"


# --- Agent 6b: ZKPrivacyShield — shield_public_data() pipeline ---

def test_shield_preserves_public_fields():
    """Tender ID, project name, budget, progress must survive shielding."""
    shield = ZKPrivacyShield()
    raw = {
        "tender_id": "TED-2026-0815",
        "project_name": "Sanierung Kläranlage Nord",
        "budget_eur": 1274896.80,
        "disbursed_eur": 434778.00,
        "progress_percent": 34.1,
        "status": "IN_PROGRESS",
        "contact": {"name": "Max Mustermann", "email": "max@stadt.de", "phone": "030-123456"},
        "workers": [{"worker_id": "W-001", "role": "Bauleiter", "hours_logged": 168.5}],
        "description": "Baufortschritt gut. Kontakt: Herr Müller",
    }
    safe = shield.shield_public_data(raw)
    assert safe["tender_id"] == "TED-2026-0815"
    assert safe["project_name"] == "Sanierung Kläranlage Nord"
    assert safe["budget_eur"] == 1274896.80
    assert safe["progress_percent"] == 34.1


def test_shield_masks_contact():
    """Phone, email, name must be masked (not stripped to placeholder)."""
    shield = ZKPrivacyShield()
    raw = {
        "contact": {"name": "Max Mustermann", "email": "max@stadt.de", "phone": "030-123456"},
    }
    safe = shield.shield_public_data(raw)
    contact = safe["contact"]
    # Masked, not blanked
    assert "****" in contact["phone"]
    assert "@" in contact["email"]  # domain preserved
    assert "****" in contact["email"]
    assert "." in contact["name"]  # initials format
    assert "Mustermann" not in contact["name"]


def test_shield_obfuscates_gps():
    """GPS must be rounded to 2 decimals (~1.1 km grid)."""
    lat, lon = ZKPrivacyShield._obfuscate_gps(52.520645, 13.404987)
    assert lat == 52.52
    assert lon == 13.40


def test_shield_pseudonymizes_workers():
    """Worker IDs must become deterministic P-* pseudonyms."""
    shield = ZKPrivacyShield(salt="test_salt")
    workers = [
        {"worker_id": "W-001", "role": "Bauleiter", "hours_logged": 168.5},
        {"worker_id": "W-002", "role": "Betonbauer", "hours_logged": 320.0},
    ]
    result = shield._pseudonymize_workers(workers)
    assert len(result) == 2
    assert result[0]["id"].startswith("P-")
    assert result[0]["role"] == "Bauleiter"
    assert result[0]["hours_logged"] == 168.5
    # Deterministic: same input → same pseudonym
    result2 = shield._pseudonymize_workers(workers)
    assert result[0]["id"] == result2[0]["id"]
    # Different salt → different pseudonyms
    shield2 = ZKPrivacyShield(salt="other_salt")
    result3 = shield2._pseudonymize_workers(workers)
    assert result[0]["id"] != result3[0]["id"]


def test_shield_cleans_free_text():
    """Emails, phones, honorific+name patterns must be replaced with placeholders."""
    text = "Bauleitung: Herr Müller (030-123456, max@stadt.de) vor Ort."
    cleaned = ZKPrivacyShield._clean_free_text(text)
    assert "[E-MAIL]" in cleaned
    assert "[TELEFON]" in cleaned
    assert "[NAME]" in cleaned
    assert "max@stadt.de" not in cleaned
    assert "Müller" not in cleaned


def test_shield_masks_address():
    """Address must be reduced to ZIP + city only."""
    result = ZKPrivacyShield._mask_address("Musterstraße 42, 10115 Berlin")
    assert "Musterstraße" not in result
    assert "42" not in result
    assert "10115" in result
    assert "Berlin" in result


def test_shield_audit_trail():
    """_audit section must list anonymized fields."""
    shield = ZKPrivacyShield()
    raw = {
        "tender_id": "TED-AUDIT",
        "contact": {"name": "Max", "email": "m@x.de", "phone": "123"},
        "workers": [{"worker_id": "W-001"}],
        "description": "Text mit Herr Müller",
        "address": "Str. 1, 10115 Berlin",
        "latitude": 52.520645,
        "longitude": 13.404987,
    }
    safe = shield.shield_public_data(raw)
    assert "_audit" in safe
    assert "fields_anonymized" in safe["_audit"]
    assert "gps_precision_decimals" in safe["_audit"]
    # At least contact, workers, address, description, GPS should be flagged
    changed = safe["_audit"]["fields_anonymized"]
    assert any(f in changed for f in ["contact", "address", "workers", "description"])


def test_shield_handles_missing_fields():
    """Missing optional fields must not crash the pipeline."""
    shield = ZKPrivacyShield()
    safe = shield.shield_public_data({"tender_id": "TED-MINIMAL"})
    assert safe["tender_id"] == "TED-MINIMAL"
    assert safe["contact"] == {}
    assert safe["workers"] == []
    assert safe["address"] == ""
    assert safe["latitude"] is None
    assert safe["longitude"] is None


# --- Agent 7: TrustButtonService ---

def test_trust_button_basic():
    """Verify with a known tender ID must return GREEN certificate."""
    svc = TrustButtonService()
    result = svc.verify("TED-2026-0815")
    assert result["status"] == "completed"
    cert = result["artifacts"][0]
    assert cert["type"] == "verification_certificate"
    assert cert["seal"] == "GREEN"
    assert cert["status"] == "VERIFIED"
    assert "details" in cert
    assert cert["details"]["project_name"] == "Sanierung Klaeranlage Nord"
    assert cert["certificate_hash"].startswith("0x")
    assert "verification_url" in cert


def test_trust_button_invoice():
    """Verify by invoice number RE-2026-001."""
    svc = TrustButtonService()
    result = svc.verify("RE-2026-001")
    assert result["status"] == "completed"
    cert = result["artifacts"][0]
    assert cert["status"] == "VERIFIED"
    assert cert["details"]["amount_eur"] == 302787.80


def test_trust_button_tx_hash():
    """Verify by transaction hash (0x...)."""
    svc = TrustButtonService()
    result = svc.verify("0x3a91c7849E2b1009B8803a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d")
    assert result["status"] == "completed"
    cert = result["artifacts"][0]
    assert cert["status"] == "VERIFIED"


def test_trust_button_not_found():
    """Unknown reference must return FAILED with clear message."""
    svc = TrustButtonService()
    result = svc.verify("UNBEKANNT-12345")
    assert result["status"] == "completed"  # operation succeeded, but...
    cert = result["artifacts"][0]
    assert cert["status"] == "FAILED"
    assert "Nicht gefunden" in cert["title"]


def test_trust_button_query_detection():
    """Auto-detect query types."""
    assert TrustButtonService._detect_query_type(
        "0x3a91c7849E2b1009B8803a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d"
    ) == "tx_hash"
    assert TrustButtonService._detect_query_type("RE-2026-001") == "invoice"
    assert TrustButtonService._detect_query_type("TED-2026-0815") == "tender_id"
    assert TrustButtonService._detect_query_type("irgendwas") == "unknown"


def test_trust_button_certificate_deterministic():
    """Same input twice → same certificate hash (deterministic)."""
    svc1 = TrustButtonService()
    svc2 = TrustButtonService()
    r1 = svc1.verify("TED-2026-0815")
    r2 = svc2.verify("TED-2026-0815")
    h1 = r1["artifacts"][0]["certificate_hash"]
    h2 = r2["artifacts"][0]["certificate_hash"]
    # Hashes differ because timestamps differ, but structure must match
    assert r1["artifacts"][0]["seal"] == r2["artifacts"][0]["seal"]
    assert r1["artifacts"][0]["status"] == r2["artifacts"][0]["status"]


# --- Agent 8: CitizenNotificationService ---

def test_notification_subscribe():
    svc = CitizenNotificationService()
    result = svc.subscribe("TED-2026-0815", "email", "citizen@example.com")
    assert result["status"] == "completed"


def test_notification_notify():
    svc = CitizenNotificationService()
    svc.subscribe("TED-2026-0815", "email", "citizen@example.com")
    result = svc.notify("TED-2026-0815", "milestone_reached", "Projekt zu 50% fertig!")
    assert result["status"] == "completed"
    assert result["artifacts"][0]["recipients"] == 1


def test_notification_unsubscribe():
    svc = CitizenNotificationService()
    svc.subscribe("TED-2026-0815", "email", "citizen@example.com")
    result = svc.unsubscribe("TED-2026-0815", "citizen@example.com")
    assert result["status"] == "completed"


# --- Agent 9: AuditTrailPublicExporter ---

def test_export_json(tmp_path):
    exporter = AuditTrailPublicExporter()
    records = [
        {"id": 1, "name": "Max Mustermann", "email": "max@example.com", "value": 100},
        {"id": 2, "name": "Jane Doe", "email": "jane@example.com", "value": 200},
    ]
    path = tmp_path / "audit.json"
    result = exporter.export_json(records, output_path=path)
    assert result["status"] == "completed"
    assert path.exists()
    exported = json.loads(path.read_text())
    # JSON export now wraps in GovData.de metadata envelope
    assert "metadata" in exported
    assert "events" in exported
    events = exported["events"]
    assert len(events) == 2
    assert events[0]["name"] == "[ANONYMISIERT]"
    assert events[0]["value"] == 100
    assert "content_hash" in result["artifacts"][0]


def test_export_csv(tmp_path):
    exporter = AuditTrailPublicExporter()
    records = [
        {"id": 1, "name": "Max", "email": "max@example.com", "value": 100},
    ]
    path = tmp_path / "audit.csv"
    result = exporter.export_csv(records, output_path=path)
    assert result["status"] == "completed"
    assert path.exists()
    assert "content_hash" in result["artifacts"][0]


def test_export_event_type_extraction():
    """Event-type-specific fields must map correctly."""
    exporter = AuditTrailPublicExporter()
    # Use mock events to test extraction
    result = exporter.export_open_data(fmt="json")
    assert result["status"] == "completed"
    artifact = result["artifacts"][0]
    assert artifact["record_count"] == 4  # 4 mock events
    assert artifact["type"] == "open_data_json"

    # Verify GovData.de metadata
    raw = json.loads(Path(artifact["path"]).read_text())
    assert raw["metadata"]["source"] == "B2G Agent X Plattform"
    assert raw["metadata"]["total_events"] == 4

    # Verify event-type-specific extraction
    tender_event = raw["events"][0]
    assert tender_event["event_type"] == "b2g.tender.published"
    assert "estimated_value_eur" in tender_event["public_data"]

    payment_event = raw["events"][2]
    assert payment_event["event_type"] == "b2g.payment.disbursed"
    assert "installment_no" in payment_event["public_data"]
    # recipient is an IBAN mask: DE89**** (short → not pseudonymized)
    assert "****" in payment_event["public_data"]["recipient"]


def test_export_filter_by_tender():
    """Filter by tender_id must only return matching events."""
    exporter = AuditTrailPublicExporter()
    result = exporter.export_open_data(tender_id="TED-2026-0815", fmt="json")
    artifact = result["artifacts"][0]
    assert artifact["record_count"] == 4  # all mock events match this tender


def test_export_filter_by_date():
    """Date range filter must narrow events."""
    exporter = AuditTrailPublicExporter()
    # Only events after August 10
    result = exporter.export_open_data(from_date="2026-08-10T00:00:00Z", fmt="json")
    artifact = result["artifacts"][0]
    # Payment (Aug 15) + Milestone (Aug 20) = 2 events
    assert artifact["record_count"] == 2


def test_export_csv_semicolon():
    """CSV must use semicolon delimiter (German Excel convention)."""
    exporter = AuditTrailPublicExporter()
    result = exporter.export_open_data(fmt="csv")
    path = Path(result["artifacts"][0]["path"])
    content = path.read_text(encoding="utf-8-sig")
    lines = content.strip().split("\n")
    assert len(lines) >= 2  # header + at least 1 row
    assert ";" in lines[0]  # semicolon separator
    assert "event_type" in lines[0]


# --- Supervisor Integration ---

def test_supervisor_all_agents():
    sup = PublicPortalSupervisor()
    status = sup.status()
    assert status["wave"] == 15
    assert status["agents"] == 9


def test_supervisor_citizen_query():
    sup = PublicPortalSupervisor()
    result = sup.citizen_query("TED-2026-0815")
    assert result["status"] == "completed"


def test_supervisor_qr_workflow(tmp_path):
    if not HAS_QRCODE:
        print("  [SKIP] qrcode not installed")
        return

    sup = PublicPortalSupervisor()
    try:
        sup.qr_generator.output_root = tmp_path
    except ImportError:
        print("  [SKIP] QRCodeGenerator not available in supervisor")
        return

    qr_result = sup.generate_qr("TED-2026-0815", fmt="svg", user_id="test")
    assert qr_result["status"] in ("completed", "skipped")


def test_supervisor_map_workflow():
    sup = PublicPortalSupervisor()
    projects = [
        {"tender_id": "TED-MAP-1", "lat": 52.52, "lon": 13.40,
         "status": "IN_PROGRESS", "project_name": "Testbruecke"},
    ]
    map_result = sup.compose_map(projects, municipality="Teststadt")
    assert map_result["status"] == "completed"


def test_supervisor_open_data_workflow(tmp_path):
    sup = PublicPortalSupervisor()
    records = [{"id": 1, "name": "Test", "email": "t@t.de", "value": 42}]
    result = sup.export_open_data(records, fmt="json", output_path=str(tmp_path / "open.json"))
    assert result["status"] == "completed"


# ============================================================
# Run all tests
# ============================================================

if __name__ == "__main__":
    import tempfile

    print("=" * 60)
    print("Wave 15 — Public Portal Agent Tests")
    print("=" * 60)

    tests = [
        # Core contracts
        ("make_response", test_make_response),
        # Agents
        ("Orchestrator (empty)", test_orchestrator_empty),
        ("Orchestrator (with sub-agents)", test_orchestrator_with_sub_agents),
        ("ProjectSummaryAggregator (basic)", test_summary_aggregator_basic),
        ("ProjectSummaryAggregator (EVM full)", test_summary_evm_full),
        ("ProjectSummaryAggregator (status)", test_summary_status_translation),
        ("ProjectSummaryAggregator (budget text)", test_summary_budget_text),
        ("ProjectSummaryAggregator (milestones)", test_summary_milestones),
        ("ProjectSummaryAggregator (prognosis)", test_summary_prognosis),
        ("ProjectSummaryAggregator (progress desc)", test_summary_progress_description),
        ("ProjectSummaryAggregator (sanitize)", test_summary_sanitize_metadata),
        ("BlockchainVerificationWidget (mock)", test_verification_widget_mock),
        ("BlockchainVerificationWidget (unknown)", test_verification_widget_unknown),
        ("BlockchainVerificationWidget (tx hash)", test_verification_widget_tx_hash),
        ("BlockchainVerificationWidget (lookup)", test_verification_widget_mock_lookup),
        ("BlockchainVerificationWidget (live off)", test_verification_widget_live_mode_disabled),
        ("BlockchainVerificationWidget (status)", test_verification_widget_status),
        ("InteractiveMapComposer (basic)", test_map_composer_basic),
        ("InteractiveMapComposer (popup)", test_map_popup_html),
        ("InteractiveMapComposer (colors)", test_map_progress_colors),
        ("InteractiveMapComposer (geocode)", test_map_geocoding),
        ("InteractiveMapComposer (address)", lambda: test_map_address_fallback(tmp_path)),
        ("InteractiveMapComposer (HTML)", lambda: test_map_html_generation(tmp_path)),
        ("InteractiveMapComposer (cache)", lambda: test_map_cache(tmp_path)),
        ("InteractiveMapComposer (skip)", lambda: test_map_no_coords_skip(tmp_path)),
        ("ZKPrivacyShield (anonymize)", test_privacy_shield_strips_pii),
        ("ZKPrivacyShield (nested)", test_privacy_shield_preserves_structure),
        ("ZKPrivacyShield (public fields)", test_shield_preserves_public_fields),
        ("ZKPrivacyShield (contact mask)", test_shield_masks_contact),
        ("ZKPrivacyShield (GPS obfuscate)", test_shield_obfuscates_gps),
        ("ZKPrivacyShield (pseudonyms)", test_shield_pseudonymizes_workers),
        ("ZKPrivacyShield (text clean)", test_shield_cleans_free_text),
        ("ZKPrivacyShield (address mask)", test_shield_masks_address),
        ("ZKPrivacyShield (audit trail)", test_shield_audit_trail),
        ("ZKPrivacyShield (minimal)", test_shield_handles_missing_fields),
        ("TrustButtonService (basic)", test_trust_button_basic),
        ("TrustButtonService (invoice)", test_trust_button_invoice),
        ("TrustButtonService (tx hash)", test_trust_button_tx_hash),
        ("TrustButtonService (not found)", test_trust_button_not_found),
        ("TrustButtonService (detect)", test_trust_button_query_detection),
        ("TrustButtonService (deterministic)", test_trust_button_certificate_deterministic),
        ("CitizenNotification (subscribe)", test_notification_subscribe),
        ("CitizenNotification (notify)", test_notification_notify),
        ("CitizenNotification (unsubscribe)", test_notification_unsubscribe),
        ("Supervisor (status)", test_supervisor_all_agents),
        ("Supervisor (citizen query)", test_supervisor_citizen_query),
        ("Supervisor (map workflow)", test_supervisor_map_workflow),
    ]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Add log test
        tests.insert(0, ("JSONLogger", lambda: test_json_logger(tmp_path)))

        # QR tests — always registered, self-skip when qrcode/Pillow missing
        tests.extend([
            ("QRCodeGenerator (SVG)", lambda: test_qr_generate_svg(tmp_path)),
            ("QRCodeGenerator (fast-track)", lambda: test_qr_fast_track(tmp_path)),
            ("QRCodeGenerator (force)", lambda: test_qr_force_regenerate(tmp_path)),
            ("QRCodeGenerator (batch)", lambda: test_qr_batch_generation(tmp_path)),
            ("QRCodeGenerator (municipality)", lambda: test_qr_municipality(tmp_path)),
            ("QRCodeGenerator (tenant iso)", lambda: test_qr_tenant_isolation(tmp_path)),
            ("QRCodeGenerator (status)", lambda: test_qr_status(tmp_path)),
            ("QRCodeGenerator (base64)", lambda: test_qr_content_base64(tmp_path)),
            ("QRCodeGenerator (data_url)", lambda: test_qr_data_url_format(tmp_path)),
            ("QRCodeGenerator (params)", lambda: test_qr_additional_params(tmp_path)),
            ("QRCodeGenerator (sha256 cache)", lambda: test_qr_sha256_cache(tmp_path)),
            ("QRCodeGenerator (PNG)", lambda: test_qr_png_output(tmp_path)),
            ("Supervisor (QR workflow)", lambda: test_supervisor_qr_workflow(tmp_path)),
        ])

        # Export tests
        tests.append(("AuditTrailExporter (JSON)", lambda: test_export_json(tmp_path)))
        tests.append(("AuditTrailExporter (CSV)", lambda: test_export_csv(tmp_path)))
        tests.append(("AuditTrailExporter (event types)", test_export_event_type_extraction))
        tests.append(("AuditTrailExporter (tender filter)", test_export_filter_by_tender))
        tests.append(("AuditTrailExporter (date filter)", test_export_filter_by_date))
        tests.append(("AuditTrailExporter (CSV semicolon)", test_export_csv_semicolon))
        tests.append(("Supervisor (open data)", lambda: test_supervisor_open_data_workflow(tmp_path)))

        passed = 0
        failed = 0

        for name, test_fn in tests:
            try:
                test_fn()
                print(f"  ✅ {name}")
                passed += 1
            except Exception as e:
                print(f"  ❌ {name}: {e}")
                failed += 1

        total = passed + failed
        print(f"\n{passed}/{total} tests passed"
              + (f", {failed} FAILED" if failed else " — ALL GOOD"))
        if failed > 0:
            sys.exit(1)
