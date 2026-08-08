#!/usr/bin/env python3
"""Wave 32 E2E Test Suite: Crypto-Philately & Digital Stamp Protocol."""
import os, sys, tempfile, time, uuid
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
from agents_b2g.philately.philately_orchestrator import (
    PhilatelyConfig, JSONLogger, PhilatelyOrchestrator,
    StampMintAndIssuanceEngine, MessagePostageValidator,
    CancellationAndPostmarkEngine, RarityAndEditionClassifier,
    PhilatelicAlbumManager, SecondaryMarketTrader,
    MuseumExhibitionCurator, StampStakingVault,
)
PASS, FAIL = 0, 0
def _log(n="test"):
    with tempfile.TemporaryDirectory() as td: PhilatelyConfig.LOG_DIR = Path(td)
    return JSONLogger(n, "test")
def check(n, c, d=""):
    global PASS, FAIL
    if c: PASS += 1; print(f"  ✅ {n}")
    else: FAIL += 1; print(f"  ❌ {n} — {d}")
def sec(t): print(f"\n{'='*60}\n  {t}\n{'='*60}")

def t1():
    sec("1. StampMintAndIssuanceEngine (9 Subagenten)")
    l=_log(); sm=StampMintAndIssuanceEngine(l)
    s=sm.standard_stamp_minter(); check("1.1 Standard", s["rarity"]=="COMMON" and s["status"]=="ISSUED")
    c=sm.commemorative_stamp_designer("100. VOB/B-Meilenstein")
    check("1.2 Commemorative", c["rarity"]=="EPIC")
    ser=sm.series_stamp_creator("Test Serie","Saison",3)
    check("1.3 Series", len(ser)==3 and ser[0]["series"]=="Test Serie")
    fv=sm.face_value_assigner("Jubilaeum","express")
    check("1.4 Face value express", fv==10.0)
    cl=sm.circulation_limit_controller("Genesis")
    check("1.5 Circulation", cl["issued"]==0)
    mc=sm.metadata_composer(s["stamp_id"],{"artist":"Test"})
    check("1.6 Metadata", mc["metadata"]["artist"]=="Test")
    ad=sm.airdrop_distributor(["u1","u2"]); check("1.7 Airdrop", ad["airdrop_count"]==2)
    tr=sm.treasury_reserve_allocator("Jubilaeum"); check("1.8 Treasury", tr["treasury_reserved"]==50)
    mo=sm.mint_orchestrator([{"edition":"Standard","count":2}]); check("1.9 Orchestrator", mo["artifacts"][0]["minted"]==2)

def t2():
    sec("2. MessagePostageValidator (9 Subagenten)")
    l=_log(); sm=StampMintAndIssuanceEngine(l); mv=MessagePostageValidator(l)
    s=sm.standard_stamp_minter(); sid=s["stamp_id"]
    mv._ownership["sender1"][sid]=True
    o=mv.stamp_ownership_verifier(sid,"sender1"); check("2.1 Owned", o["owned"])
    f=mv.face_value_sufficiency_checker(sid,100,sm._stamp_registry); check("2.2 Sufficient", f["sufficient"])
    e=mv.expiry_date_validator(s); check("2.3 Not expired", not e["expired"])
    b=mv.blacklisted_stamp_filter(sid); check("2.4 Not blacklisted", not b["blacklisted"])
    sp=mv.spam_score_calculator([{}]*5); check("2.8 No spam", sp["spam_score"]==0)
    vo=mv.validator_orchestrator(sid,"sender1",100,sm._stamp_registry)
    check("2.9 Validator OK", vo["status"]=="completed")

def t3():
    sec("3. CancellationAndPostmarkEngine (9 Subagenten)")
    l=_log(); ce=CancellationAndPostmarkEngine(l)
    s={"stamp_id":"STAMP-STD-000001","rarity":"COMMON","metadata":{}}
    c=ce.cancel_stamp(s,"A","B","msg",50000)
    check("3.x Postmarked", c["status"]=="POSTMARKED" and c["postmark"]["tx_amount_eur"]==50000)
    img=ce.postmark_image_generator(c); check("3.7 SVG", "svg" in img["svg"])
    mp=ce.original_metadata_preserver(c); check("3.8 Preserved", mp["preserved"])
    co=ce.cancellation_orchestrator([s],"A","B","msg",1000)
    check("3.9 Orchestrator", co["artifacts"][0]["cancelled"]==1)

def t4():
    sec("4. RarityAndEditionClassifier (9 Subagenten)")
    rc=RarityAndEditionClassifier()
    h=rc.historical_significance_scorer(2_000_000); check("4.1 Major TX", h==20)
    p=rc.signatory_prominence_analyzer("kaemmerer.muenchen","oberbuergermeister")
    check("4.2 Prominence", p==13)
    m=rc.edition_rarity_multiplier("MYTHIC"); check("4.3 Mythic mult", m==10.0)
    c={"stamp_id":"S-1","rarity":"LEGENDARY","mint_number":1,"mint_date":"2026-01-01T00:00:00Z",
       "postmark":{"tx_amount_eur":2_000_000}}
    co=rc.classifier_orchestrator(c,"kaemmerer","generalunternehmer")
    cl=co["artifacts"][0]; check("4.9 MYTHIC", cl["final_rarity"]=="MYTHIC" and cl["rarity_score"]>=95)

def t5():
    sec("5. PhilatelicAlbumManager (9 Subagenten)")
    l=_log(); pa=PhilatelicAlbumManager(l)
    s={"stamp_id":"STAMP-001","rarity":"RARE","series":"Test","postmark":{"timestamp":"2026-08-01T00:00:00Z","tx_amount_eur":5000}}
    r=pa.stamp_inserter("owner1",s); check("5.2 Added", r["status"]=="ADDED")
    r2=pa.stamp_inserter("owner1",s); check("5.7 Duplicate", r2["status"]=="DUPLICATE")
    ct=pa.completeness_tracker("owner1","Test"); check("5.4 Tracker", ct["collected"]==1)
    tl=pa.historical_timeline_sorter("owner1"); check("5.8 Timeline", len(tl["timeline"])==1)
    ao=pa.album_orchestrator("owner1"); check("5.9 Orchestrator", ao["artifacts"][0]["total_stamps"]==1)

def t6():
    sec("6. SecondaryMarketTrader (9 Subagenten)")
    l=_log(); sm=SecondaryMarketTrader(l)
    li=sm.listing_agent("STAMP-001","seller1",50.0)
    check("6.1 Listed", li["ask_price_agx"]==50.0)
    pd=sm.price_discovery_engine("EPIC",5); check("6.3 Price", pd>10)
    rb=sm.rarity_based_pricing_advisor({"stamp_id":"S-1","rarity":"LEGENDARY","mint_number":1})
    check("6.6 Advisor", rb["suggested_price_agx"]>100)
    mo=sm.marketplace_orchestrator(); check("6.9 Market", mo["status"]=="completed")

def t7():
    sec("7. MuseumExhibitionCurator (9 Subagenten)")
    l=_log(); me=MuseumExhibitionCurator(l)
    sl=me.spotlight_selector([{"stamp_id":"S1","rarity":"COMMON"},{"stamp_id":"S2","rarity":"LEGENDARY"}])
    check("7.2 Spotlight", sl["spotlight_stamp_id"]=="S2")
    n=me.storyteller_narrative({"postmark":{"tx_amount_eur":2_000_000,"sender":"A","recipient":"B"}})
    check("7.5 Narrative", "Historische" in n)
    eo=me.exhibition_orchestrator("owner1",{"stamps":[{"stamp_id":"S1","rarity":"COMMON","postmark":{}}]})
    check("7.9 Exhibition", eo["status"]=="completed")

def t8():
    sec("8. StampStakingVault (9 Subagenten)")
    l=_log(); sv=StampStakingVault(l)
    cv=sv.completeness_verifier(["S1","S2","S3","S4","S5"])
    check("8.1 Complete", cv["complete"])
    rc=sv.staking_reward_calculator(2,1,True); check("8.2 Reward", rc["total_reward_agx"]>0)
    gb=sv.governance_boost_allocator(3); check("8.4 Gov boost", gb["governance_boost_pct"]==1.5)
    so=sv.staking_orchestrator("owner1",{"stamps":[{"rarity":"LEGENDARY"}]*2,"series":{"S1":["a"]*5}})
    check("8.9 Staking OK", so["status"]=="completed")

def t9():
    sec("9. E2E: Full Stamp Lifecycle")
    orch=PhilatelyOrchestrator(user_id="test_e2e")
    r=orch.process_stamp_lifecycle("sender.b2g","recipient.b2g","Test message",500000,"Historisch","Test Series")
    a=r["artifacts"][0]
    check("9.1 All 8 green", a["all_green"])
    check("9.2 Duration < 1s", a["duration_ms"]<1000)
    check("9.3 Rarity scored", a["rarity_score"]>0)
    check("9.4 Stamp ID", a["stamp_id"].startswith("STAMP-HIS-"))

def t10():
    sec("10. E2E: Multiple Editions")
    orch=PhilatelyOrchestrator(user_id="test_ed")
    editions=["Standard","Saison","Jubilaeum","Genesis"]
    results=[]
    for ed in editions:
        r=orch.process_stamp_lifecycle("sender.b2g","recipient.b2g","msg",10000,ed)
        results.append(r["artifacts"][0])
    check("10.1 All editions", all(r["all_green"] for r in results))
    check("10.2 Genesis MYTHIC", any(r["rarity"]=="MYTHIC" for r in results))

def t11():
    sec("11. E2E: Collection & Staking")
    orch=PhilatelyOrchestrator(user_id="test_col")
    for i in range(5):
        orch.process_stamp_lifecycle("s.b2g","collector.b2g",f"msg {i}",50000,"Saison","Serie A")
    s=orch.get_collection_status("collector.b2g")
    a=s["artifacts"][0]
    check("11.1 5 stamps", a["total_stamps"]==5)
    check("11.2 Series complete", a["series"]["Serie A"]["complete"])

def t12():
    sec("12. Config & Logging")
    check("12.1 EDITIONS", len(PhilatelyConfig.EDITIONS)==5)
    check("12.2 SERIES_SIZE 5", PhilatelyConfig.SERIES_SIZE_FOR_COMPLETION==5)
    check("12.3 MAX_RETRIES 3", PhilatelyConfig.MAX_RETRIES==3)
    with tempfile.TemporaryDirectory() as td:
        PhilatelyConfig.LOG_DIR=Path(td)
        l=JSONLogger("test","u1"); l.info("test")
        check("12.4 Log file", len(list(Path(td).glob("*.jsonl")))>0)

if __name__=="__main__":
    print("="*70)
    print("  🧪 WAVE 32: CRYPTO-PHILATELY TEST SUITE")
    print("="*70)
    t1(); t2(); t3(); t4(); t5(); t6(); t7(); t8()
    t9(); t10(); t11(); t12()
    print(f"\n{'='*70}")
    print(f"  📊 ERGEBNIS: {PASS} passed, {FAIL} failed ({PASS+FAIL} total)")
    print(f"{'='*70}")
    if FAIL>0: print(f"\n  ❌ {FAIL} TEST(S) FEHLGESCHLAGEN!"); sys.exit(1)
    else: print(f"\n  ✅ ALLE {PASS} TESTS BESTANDEN!"); sys.exit(0)
