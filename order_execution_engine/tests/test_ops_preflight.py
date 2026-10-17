"""Zeugen Ops Pre-Flight: Freeze, Tail/Dedup, WS⊇Allowlist, Policy 3900."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from order_execution_engine.allowlist_freeze import (
    FreezeError,
    freeze_to_resolver_map,
    load_allowlist_file,
    load_freeze,
)
from order_execution_engine.market_data_feed import (
    PolySentinelBookHandler,
    PolymarketWsFeed,
)
from order_execution_engine.news_bridge import BridgePolicy
from order_execution_engine.shadow_runner import (
    DEFAULT_MAX_NEWS_AGE_S,
    JsonlTail,
    assert_ws_covers_allowlist,
    build_runner,
    load_policy_cfg,
)


OPS = Path(__file__).resolve().parents[1] / "ops"


def _freeze_doc() -> dict:
    return {
        "schema": "allowlist.freeze/v1",
        "frozen_at": "2026-10-04T00:00:00+00:00",
        "entries": {
            "BTC": {
                "asset": "BTC",
                "market_question": "Will Bitcoin reach $150,000 in October?",
                "slug": "btc-test",
                "token_id": "tokBTC",
                "market_id": "condBTC",
                "resolved_at": "2026-10-04T00:00:00+00:00",
                "source": "gamma",
            },
            "ETH": {
                "asset": "ETH",
                "market_question": "Will Ethereum dip to $2,100 in October?",
                "slug": "eth-test",
                "token_id": "tokETH",
                "market_id": "condETH",
                "resolved_at": "2026-10-04T00:00:00+00:00",
                "source": "gamma",
            },
        },
    }


def test_w_ops_1_freeze_schema_and_ws_cover() -> None:
    """Freeze-Schema + WS assets_ids == Freeze-token_ids; leere Allowlist fail-closed."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "allowlist.freeze.json"
        path.write_text(json.dumps(_freeze_doc()))
        freeze = load_freeze(path)
        amap, cfg = load_allowlist_file(path)
        assert set(amap) == {"BTC", "ETH"}
        assert cfg["BTC"]["slug"] == "btc-test"
        ids = [amap[k]["token_id"] for k in sorted(amap)]
        assert_ws_covers_allowlist(ids, amap)
        payload = PolymarketWsFeed.subscription_payload(ids)
        assert set(payload["assets_ids"]) == {"tokBTC", "tokETH"}
        try:
            build_runner(
                data_root=Path(td),
                user_id="u",
                allowlist={},
                policy_cfg={"max_news_age_s": 3900},
                start_ws=False,
            )
            raise AssertionError("empty allowlist must fail")
        except ValueError as exc:
            assert "empty" in str(exc).lower()
    print("OK test_w_ops_1_freeze_schema_and_ws_cover")


def test_w_ops_2_policy_3900_in_config_json() -> None:
    """run_policy / Defaults → max_news_age_s=3900 in eingefrorenem config_json."""
    assert DEFAULT_MAX_NEWS_AGE_S == 3900.0
    policy_path = OPS / "run_policy.json"
    cfg = load_policy_cfg(policy_path if policy_path.exists() else None)
    assert float(cfg["max_news_age_s"]) == 3900
    p = BridgePolicy.from_config(cfg)
    assert p.max_news_age_s == 3900

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        amap = freeze_to_resolver_map(_freeze_doc())
        engine, bridge, store, binding, config_json = build_runner(
            data_root=root,
            user_id="shadow",
            allowlist=amap,
            policy_cfg=cfg,
            start_ws=False,
            config_allowlist=_freeze_doc()["entries"],
            git_commit="deadbeef",
        )
        assert config_json["max_news_age_s"] == 3900
        assert config_json["max_book_age_ms"] == 2000
        assert config_json["staleness_policy"] == "reject_stale"
        assert config_json["resting_model"] == "re_cross"
        assert config_json["signal_ref_mode"] == "fallback_limit"
        assert config_json["git_commit"] == "deadbeef"
        assert set(config_json["ws_token_ids"]) == {"tokBTC", "tokETH"}
        assert "slug" in config_json["market_allowlist"]["BTC"]
        # Book für späteren Dispatch
        PolySentinelBookHandler(binding.cache).on_book_update(
            "tokBTC",
            bids=[(Decimal("0.40"), Decimal("100"))],
            asks=[(Decimal("0.42"), Decimal("100"))],
        )
        store.close()
    print("OK test_w_ops_2_policy_3900_in_config_json")


def test_w_ops_3_jsonl_tail_batch_dedup() -> None:
    """JSONL-Tail: zwei Appends → zwei Dispatches; Restart ohne Re-Dispatch."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        jsonl = root / "news.jsonl"
        offset = root / "news_tail.offset"
        jsonl.write_text("")
        amap = {"BTC": {"token_id": "tokBTC", "market_id": "mBTC"}}
        cfg = load_policy_cfg(OPS / "run_policy.json" if (OPS / "run_policy.json").exists() else None)
        engine, bridge, store, binding, _cfg = build_runner(
            data_root=root,
            user_id="u1",
            allowlist=amap,
            policy_cfg=cfg,
            start_ws=False,
            git_commit="test",
        )
        PolySentinelBookHandler(binding.cache).on_book_update(
            "tokBTC",
            bids=[(Decimal("0.40"), Decimal("500"))],
            asks=[(Decimal("0.42"), Decimal("500"))],
        )
        tail = JsonlTail(jsonl, offset)
        tail.seek_end()

        def _append(item_id: str) -> None:
            row = {
                "item_id": item_id,
                "target_assets": ["BTC"],
                "sentiment_score": "0.5",
                "impact_level": "HIGH",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "schema": "news_agent_multi/v1",
            }
            with jsonl.open("a") as fh:
                fh.write(json.dumps(row) + "\n")

        _append("batch:1")
        _append("batch:2")
        batch = tail.poll()
        assert len(batch) == 2
        n = sum(1 for it in batch if bridge.on_news_item(it))
        assert n == 2
        assert len(engine.telemetry._records) == 2

        # Gleicher Offset → keine neuen Zeilen
        assert tail.poll() == []

        # Offset hält: keine Re-Reads
        tail2 = JsonlTail(jsonl, offset)
        assert tail2.poll() == []
        # Dedup: gleiche item_ids auch bei Offset-Reset + neuem Runner
        engine2, bridge2, store2, _binding2, _ = build_runner(
            data_root=root,
            user_id="u1",
            allowlist=amap,
            policy_cfg=cfg,
            start_ws=False,
            git_commit="test",
        )
        PolySentinelBookHandler(_binding2.cache).on_book_update(
            "tokBTC",
            bids=[(Decimal("0.40"), Decimal("500"))],
            asks=[(Decimal("0.42"), Decimal("500"))],
        )
        tail2._offset = 0
        again = tail2.poll()
        assert len(again) == 2
        assert sum(1 for it in again if bridge2.on_news_item(it)) == 0
        assert engine2.telemetry._records == []
        store.close()
        store2.close()
    print("OK test_w_ops_3_jsonl_tail_batch_dedup")


def test_w_ops_4_freeze_file_on_disk_if_present() -> None:
    """Ops-Freeze-Datei (falls vorhanden) validiert Pflichtfelder."""
    path = OPS / "allowlist.freeze.json"
    if not path.exists():
        print("SKIP test_w_ops_4_freeze_file_on_disk_if_present (no freeze yet)")
        return
    freeze = load_freeze(path)
    assert set(freeze["entries"]) >= {"BTC", "ETH"}
    for asset, entry in freeze["entries"].items():
        assert entry["source"] == "gamma"
        assert entry["token_id"]
        assert entry["resolved_at"]
    amap = freeze_to_resolver_map(freeze)
    ids = [amap[k]["token_id"] for k in sorted(amap)]
    assert_ws_covers_allowlist(ids, amap)
    print("OK test_w_ops_4_freeze_file_on_disk_if_present")


def test_w_ops_5_freeze_rejects_bad_source() -> None:
    with tempfile.TemporaryDirectory() as td:
        doc = _freeze_doc()
        doc["entries"]["BTC"]["source"] = "manual"
        path = Path(td) / "bad.json"
        path.write_text(json.dumps(doc))
        try:
            load_freeze(path)
            raise AssertionError("must reject non-gamma source")
        except FreezeError:
            pass
    print("OK test_w_ops_5_freeze_rejects_bad_source")


def test_shipped_run_policy_defines_theta_explicitly() -> None:
    """Die ausgelieferte Config, nicht ein Dict, muss `theta` tragen (§5.4cr).

    `from_config` ist gepinnt — aber der Pin greift nur, wenn die Datei
    den Wert **nennt**. Fehlt `theta` in `run_policy.json`, greift der
    Default in `load_policy_cfg`, und der Assert im `from_config` wäre der
    einzige Wächter: Code-Eigenschaft statt Betriebs-Eigenschaft. Ein
    fehlender Schlüssel ist hier still, ein falscher laut — deshalb prüft
    dieser Test **beides**: Präsenz und Wert.
    """
    import json as _json

    path = (Path(__file__).resolve().parents[1] / "ops" / "run_policy.json")
    assert path.exists(), f"ausgelieferte Config fehlt: {path}"

    raw = _json.loads(path.read_text(encoding="utf-8"))
    assert "theta" in raw, (
        "theta steht nicht in run_policy.json — der Pin prüft dann den "
        "Default aus load_policy_cfg, nicht die Datei"
    )
    assert str(raw["theta"]) == "0.1", (
        f"ausgelieferte theta={raw['theta']!r} weicht von der Kalibrierung ab"
    )

    # Und der echte Ladepfad — nicht `{"theta": "0.1"}` im Test.
    policy = BridgePolicy.from_config(load_policy_cfg(path))
    assert policy.theta == Decimal("0.1")


def test_shipped_run_policy_matches_defaults_except_theta_is_explicit() -> None:
    """Der Dateipfad und der Default-Pfad dürfen sich nicht unterscheiden.

    Wenn `load_policy_cfg(None)` und `load_policy_cfg(datei)` verschiedene
    Policies ergeben, läuft der Dienst anders, je nachdem ob das Argument
    gesetzt ist — und `ops/` ist der einzige Ort, an dem das auffiele.
    """
    path = (Path(__file__).resolve().parents[1] / "ops" / "run_policy.json")
    shipped = BridgePolicy.from_config(load_policy_cfg(path))
    defaulted = BridgePolicy.from_config(load_policy_cfg(None))

    assert shipped.theta == defaulted.theta
    assert shipped.max_news_age_s == defaulted.max_news_age_s
    assert shipped.snapshot() == defaulted.snapshot(), (
        "run_policy.json beschreibt eine andere Policy als der Default"
    )


def test_handover_protocol_has_three_states_not_two() -> None:
    """`☐ ja ☐ nein` ist kein Zustand, sondern ein Default (§5.4df).

    Zwei leere Kaestchen heissen "niemand hat hingesehen" und sehen aus wie
    "bewusst offengelassen". Der dritte Zustand ist der Unterschied
    zwischen einem Protokoll und einem Formular.
    """
    path = (Path(__file__).resolve().parents[1] / "ops"
            / "UEBERGABEPROTOKOLL.md")
    assert path.exists()
    text = path.read_text(encoding="utf-8")

    assert text.count("☐ nicht entschieden") >= 4, (
        "jedes Feld braucht den dritten Zustand"
    )
    assert "Grund:" in text, "nicht entschieden braucht einen Grund"
    assert "Dies ist der Entwurf" in text, (
        "der Entwurf muss sich als Entwurf ausweisen — sonst liest ihn "
        "in vier Wochen jemand fuer die Entscheidung"
    )
    assert "UEBERGABEPROTOKOLL-YYYY-MM-DD.md" in text, (
        "die unterschriebene Fassung braucht ein Datum im Namen"
    )


def test_sentiment_absence_never_logs_the_string_none() -> None:
    """`str(None)` ist `"None"` — eine ID, die wie ein Wert aussieht (§5.4de).

    Im Bestand 0 Zeilen (geprueft 17.10.), aber der Bestand entlastet die
    Codestelle nicht: ohne Pruefung kann sie es erzeugen.
    """
    import inspect
    from order_execution_engine import news_bridge

    src = inspect.getsource(news_bridge)
    assert "__no_item_id__" in src
    i = src.index("absent_sentiment")
    window = src[max(0, i - 700):i]
    assert 'in ("", "None")' in window, (
        "vor dem Log muss `None`/`''`/`'None'` abgefangen werden"
    )
