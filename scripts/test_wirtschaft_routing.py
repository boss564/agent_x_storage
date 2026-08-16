"""Baustein 4 tests: KlassenResolver + envelope/AgentMessage adapter + router."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.protocol import PayloadType
from agents_b2g.wirtschaft import KompetenzKlasse, build_schwarm
from agents_b2g.wirtschaft.routing_adapter import (
    KlassenResolver, WirtschaftsRouter,
    envelope_to_agent_message, agent_message_to_envelope,
)

TEST_PAYLOAD_TYPE = list(PayloadType)[0]   # any valid member


# --- KlassenResolver ---

def test_resolver_single_member():
    r = KlassenResolver()
    r.register(KompetenzKlasse.GOVERNANCE, "retention-1")
    assert r.resolve(KompetenzKlasse.GOVERNANCE) == "retention-1"


def test_resolver_deterministic_tie_break():
    r = KlassenResolver()
    for aid in ["a-1", "a-2", "a-3"]:
        r.register(KompetenzKlasse.KAPITAL, aid)
    picks = {r.resolve(KompetenzKlasse.KAPITAL, tie_break_seed="s") for _ in range(5)}
    assert len(picks) == 1   # same seed -> always the same agent


def test_resolver_health_priority():
    r = KlassenResolver()
    r.register(KompetenzKlasse.KAPITAL, "low-1")
    r.register(KompetenzKlasse.KAPITAL, "high-1")
    r.set_health("low-1", 0.1)
    r.set_health("high-1", 0.9)
    assert r.resolve(KompetenzKlasse.KAPITAL) == "high-1"


def test_resolver_empty_returns_none():
    assert KlassenResolver().resolve(KompetenzKlasse.AUSFUEHRUNG) is None


def test_parse_klasse():
    assert KlassenResolver.parse_klasse("klasse.C") == KompetenzKlasse.GOVERNANCE
    assert KlassenResolver.parse_klasse("klasse.A") == KompetenzKlasse.KAPITAL
    assert KlassenResolver.parse_klasse("C") == KompetenzKlasse.GOVERNANCE
    assert KlassenResolver.parse_klasse("unknown") is None


# --- Adapter roundtrip ---

def test_envelope_to_agent_message():
    env = {"topic": "agent.liq-1.klasse.C.request", "sender": "liq-1",
           "target": "klasse.C", "kind": "request",
           "payload": {"typ": "FREIGABE_REQUEST", "aktion": "token.mint"}}
    msg = envelope_to_agent_message(env, TEST_PAYLOAD_TYPE)
    assert msg.sender == "liq-1"
    assert msg.receiver == "klasse.C"
    assert msg.content["payload"]["typ"] == "FREIGABE_REQUEST"


def test_adapter_roundtrip():
    env = {"topic": "agent.x.y.request", "sender": "x", "target": "y",
           "kind": "request", "payload": {"k": 1}}
    back = agent_message_to_envelope(envelope_to_agent_message(env, TEST_PAYLOAD_TYPE))
    assert back["sender"] == "x"
    assert back["target"] == "y"
    assert back["kind"] == "request"
    assert back["payload"] == {"k": 1}


# --- WirtschaftsRouter ---

def _router_from_schwarm():
    schwarm, agents = build_schwarm()
    by_id = {a.id: a for a in agents.values()}
    resolver = KlassenResolver()
    for klasse, ids in schwarm.class_members.items():
        for aid in ids:
            resolver.register(klasse, aid)
    return WirtschaftsRouter(resolver, by_id, TEST_PAYLOAD_TYPE), resolver


def test_router_resolves_class_to_concrete_agent():
    router, resolver = _router_from_schwarm()
    env = {"topic": "agent.minter-1.klasse.C.request", "sender": "minter-1",
           "target": "klasse.C", "kind": "request",
           "payload": {"typ": "FREIGABE_REQUEST", "aktion": "token.mint"}}
    msg = router.route(env)
    assert msg is not None
    assert msg.receiver in resolver.members(KompetenzKlasse.GOVERNANCE)
    assert msg.receiver != "klasse.C"   # class address was resolved


def test_router_no_members_returns_none():
    resolver = KlassenResolver()
    router = WirtschaftsRouter(resolver, {}, TEST_PAYLOAD_TYPE)
    env = {"sender": "x", "target": "klasse.C", "kind": "request", "payload": {}}
    assert router.route(env) is None
