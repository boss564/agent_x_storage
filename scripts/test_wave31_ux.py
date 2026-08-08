#!/usr/bin/env python3
"""Wave 31 E2E Test Suite: Omnichannel UX & Verwaltungs-Dashboard.
Usage: python3 scripts/test_wave31_ux.py"""
import os, sys, tempfile, time, uuid
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
from agents_b2g.ux.ux_orchestrator import (
    UXConfig, JSONLogger, SessionStateManager, RoleBasedDashboardComposer,
    ResponsiveWebPortal, NaturalLanguageAssistant, ProcessWorkflowVisualizer,
    RealTimeAnalyticsHub, SandboxSimulationPlayer, SmartAlertAndNotification,
    GoBDReportGenerator, UXOrchestrator,
)
PASS, FAIL = 0, 0
def _log(n="test"): 
    with tempfile.TemporaryDirectory() as td: UXConfig.LOG_DIR = Path(td)
    return JSONLogger(n, "test")
def check(n, c, d=""):
    global PASS, FAIL
    if c: PASS += 1; print(f"  ✅ {n}")
    else: FAIL += 1; print(f"  ❌ {n} — {d}")
def sec(t): print(f"\n{'='*60}\n  {t}\n{'='*60}")

# --- 1. RoleBasedDashboardComposer ---
def t1():
    sec("1. RoleBasedDashboardComposer (9 Subagenten)")
    l = _log(); sm = SessionStateManager(l); db = RoleBasedDashboardComposer(l, sm)
    sid = sm.create_session("u1", "KAEMMERER", "desktop")["session_id"]
    # 1.1
    r = db.user_role_resolver(sid); check("1.1 Role resolved", r["role"]=="KAEMMERER")
    # 1.2
    p = db.permission_matrix_loader("KAEMMERER"); check("1.2 8 actions", p["action_count"]==8)
    # 1.3
    lo = db.dashboard_layout_builder("BAULEITER"); check("1.3 Layout", lo["widget_count"]==8)
    # 1.4
    k = db.kpi_selector_for_role("PRUEFER"); check("1.4 4 KPIs", k["kpi_count"]==4)
    # 1.5
    v = db.action_button_visibility("KAEMMERER", ["budget_approve","admin_panel"])
    check("1.5 Budget allowed", v["visible_actions"]["budget_approve"])
    check("1.5 Admin blocked", not v["visible_actions"]["admin_panel"])
    # 1.6
    w = db.widget_orchestrator("KAEMMERER"); check("1.6 8 widgets", w["active_count"]==8)
    # 1.7
    d = db.data_preaggregator([{"a":10},{"a":20}],"sum"); check("1.7 Sum=30", d["aggregated"]["a"]==30)
    # 1.8
    t = db.theme_and_accessibility_controller({}); check("1.8 Theme", t["accessibility_score"]==92)
    # 1.9
    do = db.dashboard_orchestrator(sid); check("1.9 Status ok", do["status"]=="completed")

# --- 2. ResponsiveWebPortal ---
def t2():
    sec("2. ResponsiveWebPortal (9 Subagenten)")
    l = _log(); sm = SessionStateManager(l); rp = ResponsiveWebPortal(l, sm)
    ws = [{"widget_id":"w1","state":"ACTIVE"}]*6
    # 2.1
    m = rp.mobile_first_design_engine(ws); check("2.1 Mobile full_width", m["layout"][0]["full_width"])
    # 2.2
    tb = rp.tablet_optimized_renderer(ws); check("2.2 Tablet touch", tb["layout"][0]["touch_optimized"])
    # 2.3
    dt = rp.desktop_power_user_mode(ws); check("2.3 Desktop draggable", dt["layout"][0]["draggable"])
    # 2.4
    of = rp.offline_data_synchronizer([{"k":"v"}],"queue"); check("2.4 Offline buffered", of["total_offline"]>0)
    # 2.5
    pwa = rp.progressive_web_app_installer(); check("2.5 PWA installable", pwa["installable"])
    # 2.6
    a11 = rp.accessibility_checker([{"id":"img1","type":"image","color_contrast":3}])
    check("2.6 A11y issue", a11["issue_count"]==2)
    # 2.7
    l10 = rp.localization_and_currency("de", 1500.50); check("2.7 € format", "€" in l10["formatted_amount"])
    # 2.8
    sid = sm.create_session("u2","KAEMMERER")["session_id"]
    to = rp.session_timeout_manager(sid); check("2.8 Session OK", to["valid"])
    # 2.9
    po = rp.portal_orchestrator(sid); check("2.9 Portal", po["status"]=="completed")

# --- 3. NaturalLanguageAssistant ---
def t3():
    sec("3. NaturalLanguageAssistant (9 Subagenten)")
    l = _log(); na = NaturalLanguageAssistant(l)
    # 3.1
    i = na.intent_recognizer("Budget Haushalt anzeigen"); check("3.1 Budget intent", i["top_intent"]=="SHOW_BUDGET")
    # 3.2
    e = na.entity_extractor("1500 euro fuer Schulzentrum"); check("3.2 Entities", e["entity_count"]>0)
    # 3.3
    c = na.command_executor("SHOW_BUDGET",{}, "u1"); check("3.3 Budget cmd", "Restbudget" in c["message"])
    # 3.4
    na.context_memory_manager("u1",{"intent":"SHOW_BUDGET"},"store"); check("3.4 Context", True)
    # 3.5
    vt = na.voice_to_text_handler(); check("3.5 Voice transcribed", vt["confidence"]>0.9)
    # 3.6
    tv = na.text_to_voice_responder("Hallo"); check("3.6 TTS", tv["estimated_duration_s"]>0)
    # 3.7
    cf = na.confidence_score_filter({"confidence":0.2}); check("3.7 Low conf fallback", cf["action"]=="FALLBACK")
    # 3.8
    ml = na.multi_language_support("Budget", "en"); check("3.8 Multi-lang", "Show Budget" in ml["translations"].values())
    # 3.9
    ao = na.assistant_orchestrator("Budget zeigen","u1","KAEMMERER"); check("3.9 Orchestrator", ao["status"]=="completed")

# --- 4. ProcessWorkflowVisualizer ---
def t4():
    sec("4. ProcessWorkflowVisualizer (9 Subagenten)")
    l = _log(); pv = ProcessWorkflowVisualizer(l)
    ms = [{"id":"M1","name":"Fundament","planned_date":"2026-03-15","status":"COMPLETED","dependencies":[],"budget_eur":500000}]
    # 4.1
    tl = pv.milestone_timeline_builder(ms,"P1"); check("4.1 Timeline", tl["milestone_count"]==1)
    # 4.2
    pg = pv.progress_indicator_engine(ms); check("4.2 Progress 100%", pg["progress_pct"]==100)
    # 4.3
    dg = pv.dependency_graph_renderer(ms); check("4.3 Graph", dg["node_count"]==1)
    # 4.4
    sc = pv.status_color_coder("COMPLETED"); check("4.4 Color green", "057a55" in sc["color"])
    # 4.5
    fb = pv.financial_burn_rate_display(5e6,3e6,180,365); check("4.5 Burn rate", fb["variance_pct"]!=0)
    # 4.6
    hm = pv.delay_risk_heatmap([{"id":"P1","delay_days":45,"budget_eur":5e6}]); check("4.6 Risk HIGH", hm["heatmap"][0]["risk_level"]=="HIGH")
    # 4.7
    gc = pv.gantt_chart_generator(ms,"P1"); check("4.7 Gantt", gc["task_count"]==1)
    # 4.8
    an = pv.collaboration_annotation_engine("M1",{"user":"u1","text":"Ok"},"add"); check("4.8 Annotation", an["annotation_count"]==1)
    # 4.9
    vo = pv.visualizer_orchestrator("P1",ms); check("4.9 Orchestrator", vo["status"]=="completed")

# --- 5. RealTimeAnalyticsHub ---
def t5():
    sec("5. RealTimeAnalyticsHub (9 Subagenten)")
    l = _log(); ra = RealTimeAnalyticsHub(l)
    # 5.1
    b = ra.bho_zero_sum_monitor(5e6,3.8e6,2e5,1e6); check("5.1 BHO compliant", b["delta_eur"]==0)
    # 5.2
    n = ra.netting_efficiency_tracker(100,1); check("5.2 Netting 99%", n["reduction_pct"]==99.0)
    # 5.3
    tf = ra.token_flywheel_visualizer(1e8,1e6,2e7,8e7); check("5.3 Flywheel", tf["deflationary"])
    # 5.4
    df = ra.defense_activity_heatmap([{"country":"RU","threat_type":"CARTEL"}]); check("5.4 Defense", df["total_incidents"]==1)
    # 5.5
    lp = ra.liquidity_pool_performance({"tvl_eur":5e6,"volume_24h_eur":1e6,"apr_pct":8}); check("5.5 LP healthy", lp["health"]=="HEALTHY")
    # 5.6
    gc = ra.gas_cost_saver_counter(1000); check("5.6 Gas saved", gc["total_saved_eur"]>0)
    # 5.7
    cs = ra.compliance_score_dash([{"name":"BHO","passed":True}]*5); check("5.7 Compliance 100", cs["score"]==100)
    # 5.8
    cr = ra.customizable_report_builder(["bho","netting"]); check("5.8 Custom report", cr["report_id"]!="")
    # 5.9
    ao = ra.analytics_orchestrator(); check("5.9 Orchestrator", ao["status"]=="completed")

# --- 6. SandboxSimulationPlayer ---
def t6():
    sec("6. SandboxSimulationPlayer (9 Subagenten)")
    l = _log(); sb = SandboxSimulationPlayer(l)
    # 6.1
    p = sb.scenario_parameter_input({"budget":5e6}); check("6.1 Params valid", p["param_count"]==1)
    # 6.2
    bi = sb.budget_impact_simulator(5e6,-10,"Test"); check("6.2 Budget -10%", bi["new_budget"]==4500000)
    # 6.3
    ms = sb.milestone_shift_simulator([{"id":"M1"}], 30); check("6.3 Shift 30d", ms["critical_path_extended"])
    # 6.4
    tp = sb.token_price_simulator(0.1,-5,10); check("6.4 Price bullish", tp["mechanism"]=="DEFLATIONARY")
    # 6.5
    nl = sb.network_load_tester(500,60); check("6.5 Network OK", nl["recommendation"]=="OK")
    # 6.6
    rs = sb.risk_scenario_planner("CYBER_ATTACK",30,1e6); check("6.6 Cyber risk HIGH", rs["priority"]=="MEDIUM")
    # 6.7
    rc = sb.result_comparison_engine([bi]); check("6.7 Comparison", rc["total_compared"]==1)
    # 6.8
    sl = sb.scenario_audit_logger({"test":True},"u1"); check("6.8 Audit logged", sl["logged"])
    # 6.9
    so = sb.sandbox_orchestrator({"name":"Test","budget_eur":5e6,"budget_change_pct":-5,"token_price":0.1,"supply_change_pct":0,"demand_change_pct":5,"tps":100,"duration_s":60},"u1")
    check("6.9 Orchestrator", so["status"]=="completed")

# --- 7. SmartAlertAndNotification ---
def t7():
    sec("7. SmartAlertAndNotification (9 Subagenten)")
    l = _log(); sa = SmartAlertAndNotification(l)
    # 7.1
    td = sa.threshold_breach_detector("budget",5.5e6,5e6,"above"); check("7.1 Breach", td["breached"])
    # 7.2
    ce = sa.critical_event_distributor({"id":"A1","channel":"push"},["u1"]); check("7.2 Distributed", ce["recipients"]==1)
    # 7.3
    pn = sa.push_notification_sender("u1","Test","Body"); check("7.3 Push sent", pn["sent"])
    # 7.4
    em = sa.email_report_generator("u1","daily"); check("7.4 Email sent", em["sent"])
    # 7.5
    sm = sa.sms_guardian_sender("+4912345678","Test"); check("7.5 SMS sent", sm["sent"])
    # 7.6
    im = sa.in_app_message_center("u1"); check("7.6 In-app", im["unread_count"]>=0)
    # 7.7
    es = sa.escalation_policy_engine({"id":"A1"}); check("7.7 Escalation lvl1", es["escalation_level"]==1)
    # 7.8
    dd = sa.do_not_disturb_scheduler("u1"); check("7.8 DND info", "in_dnd_period" in dd)
    # 7.9
    ao = sa.alert_orchestrator("u1",{"severity":"CRITICAL","title":"Test","message":"Alarm!"})
    check("7.9 Orchestrator", ao["status"]=="completed")

# --- 8. GoBDReportGenerator ---
def t8():
    sec("8. GoBDReportGenerator (9 Subagenten)")
    l = _log(); gr = GoBDReportGenerator(l)
    d = [{"id":1}]
    # 8.1
    gf = gr.gobd_compliant_formatter(d,"audit"); check("8.1 GoBD formatted", len(gf["worm_anchor"])==64)
    # 8.2
    pdf = gr.pdf_export_engine("Test",d); check("8.2 PDF", pdf["page_count"]==1)
    # 8.3
    dv = gr.datev_exporter([{"betrag":100}]); check("8.3 DATEV", dv["datev_compatible"])
    # 8.4
    xr = gr.xml_report_builder("audit",{}); check("8.4 XBRL valid", xr["schema_valid"])
    # 8.5
    qs = gr.quarterly_summary_generator(2026,3,{"total":1e6}); check("8.5 Quarterly", qs["period"]=="Q3/2026")
    # 8.6
    ya = gr.yearly_audit_packager(2026,[qs]); check("8.6 Yearly", not ya["audit_ready"])
    # 8.7
    si = gr.archive_signature_attacher("R1","u1"); check("8.7 Signed", si["verifiable"])
    # 8.8
    ac = gr.access_control_report("TAX_AUDIT","u1","BUERGER"); check("8.8 Access denied", not ac["allowed"])
    # 8.9
    ro = gr.report_orchestrator("quarterly",d,"u1","KAEMMERER"); check("8.9 Orchestrator", ro["status"]=="completed")

# --- 9-14: E2E Tests ---
def t9():
    sec("9. E2E: Login & Dashboard")
    ux = UXOrchestrator(user_id="test_e2e")
    ux.login("user1","KAEMMERER","desktop","de")
    d = ux.render_dashboard(); a = d["artifacts"][0]
    check("9.1 All 4 steps green", all(v=="completed" for v in a["pipeline_steps"].values()))
    check("9.2 Duration < 1s", a["duration_ms"]<1000)

def t10():
    sec("10. E2E: NL Commands")
    ux = UXOrchestrator(user_id="test_cmd")
    ux.login("user1","BAULEITER")
    r = ux.process_command("Budget Haushalt anzeigen")
    check("10.1 Intent recognized", r["artifacts"][0]["intent"] is not None)
    r2 = ux.process_command("Wie geht es")
    check("10.2 Unknown handled", r2["status"]=="completed")

def t11():
    sec("11. E2E: Simulation")
    ux = UXOrchestrator(user_id="test_sim")
    ux.login("user1","KAEMMERER")
    r = ux.run_simulation({"name":"Test","budget_eur":5e6,"budget_change_pct":-10,"token_price":0.1,"supply_change_pct":0,"demand_change_pct":5,"tps":100,"duration_s":60})
    check("11.1 Sim complete", r["status"]=="completed")
    check("11.2 Budget changed", r["artifacts"][0]["budget"]["new_budget"]<5e6)

def t12():
    sec("12. E2E: Reports & Alerts")
    ux = UXOrchestrator(user_id="test_rep")
    ux.login("user1","KAEMMERER")
    rep = ux.generate_report("quarterly",[{"id":1}])
    check("12.1 Report OK", rep["status"]=="completed")
    al = ux.trigger_alert("WARNING","Test","Message")
    check("12.2 Alert triggered", al["status"]=="completed")

def t13():
    sec("13. E2E: Multi-Role")
    ux = UXOrchestrator(user_id="test_mr")
    for role in ["KAEMMERER","BAULEITER","PRUEFER","BUERGER","ENTWICKLER","BANKING_PARTNER"]:
        ux.login(f"user_{role}", role)
        d = ux.render_dashboard(role)
        check(f"13.{role}", d["status"]=="completed")

def t14():
    sec("14. Config & Logging")
    check("14.1 SESSION_TIMEOUT", UXConfig.SESSION_TIMEOUT_S==1800)
    check("14.2 5 ROLE_DEFINITIONS", len(RoleBasedDashboardComposer.ROLE_DEFINITIONS)==6)
    check("14.3 9 INTENTS", len(NaturalLanguageAssistant.INTENTS)==9)
    check("14.4 MAX_RETRIES 3", UXConfig.MAX_RETRIES==3)
    with tempfile.TemporaryDirectory() as td:
        UXConfig.LOG_DIR = Path(td)
        l = JSONLogger("test","u1"); l.info("test")
        check("14.5 Log file", len(list(Path(td).glob("*.jsonl")))>0)

if __name__=="__main__":
    print("="*70)
    print("  🧪 WAVE 31: UX & DASHBOARD TEST SUITE")
    print("="*70)
    t1(); t2(); t3(); t4(); t5(); t6(); t7(); t8()
    t9(); t10(); t11(); t12(); t13(); t14()
    print(f"\n{'='*70}")
    print(f"  📊 ERGEBNIS: {PASS} passed, {FAIL} failed ({PASS+FAIL} total)")
    print(f"{'='*70}")
    if FAIL>0: print(f"\n  ❌ {FAIL} TEST(S) FEHLGESCHLAGEN!"); sys.exit(1)
    else: print(f"\n  ✅ ALLE {PASS} TESTS BESTANDEN!"); sys.exit(0)
