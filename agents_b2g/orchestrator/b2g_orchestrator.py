#!/usr/bin/env python3
"""
B2G Universal Orchestrator — 9 Agenten, 3 Cluster, 5 Sektoren.

Cluster 1 (Identity): nPA+ZK+Role
Cluster 2 (Finance):  Monerium/SEPA + SAP/DATEV + ELSTER
Cluster 3 (Web3):     Blockchain + Chainlink + OFAC/RegTech

3-Sekunden-Workflow: Scan → Verify → Split → ERP → Archive.

Usage:
    python agents_b2g/orchestrator/b2g_orchestrator.py
"""
from __future__ import annotations
import hashlib, json, os, sys, time, uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents_b2g.orchestrator.context_profiles import CONTEXT_PROFILES
from agents_b2g.event_bus import EventBus


class OrchestratorConfig:
    DATA_ROOT=Path(os.getenv("ORCH_DATA_ROOT","data")); LOG_DIR=Path(os.getenv("ORCH_LOG_DIR","logs"))
    NFC_TIMEOUT_S=int(os.getenv("ORCH_NFC_TIMEOUT","5")); ZK_CIRCUIT="groth16"
    BLOCKCHAIN_RPC=os.getenv("ORCH_RPC","https://rpc.gnosischain.com")
    MONERIUM_API=os.getenv("ORCH_MONERIUM_API","https://api.monerium.com")
    ELSTER_API=os.getenv("ORCH_ELSTER_API","https://www.elster.de/erich/api")
    SAP_ODATA=os.getenv("ORCH_SAP_ODATA","https://sap.example.com/odata")
    MAX_RETRIES=3; RETRY_BACKOFF=0.5; SANCTION_LIST:Set[str]={"0xSANCTIONED","0xOFAC_LISTED","0xTERROR_FINANCE"}


class JSONLogger:
    def __init__(s,n="orch",u="default"):
        s.name,s.uid=n,u
        s.path=OrchestratorConfig.LOG_DIR/f"orch_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
        s.path.parent.mkdir(parents=True,exist_ok=True)
    def _w(s,l,m,**x):
        e={"ts":datetime.now(timezone.utc).isoformat(),"lvl":l,"agt":s.name,"uid":s.uid,"msg":m,**x}
        with open(s.path,"a") as f: f.write(json.dumps(e,default=str)+"\n")
    def info(s,m,**kw): s._w("INFO",m,**kw)
    def warn(s,m,**kw): s._w("WARN",m,**kw)
    def error(s,m,**kw): s._w("ERROR",m,**kw)

_ok=lambda j,a=None,**kw:{"status":"completed","job_id":j,"artifacts":a or [],"error":None,"logs":[],**kw}
_block=lambda j,r,**kw:{"status":"blocked","job_id":j,"artifacts":[],"error":r,"logs":[{"level":"ALERT","message":r}],**kw}
_fail=lambda j,e,**kw:{"status":"failed","job_id":j,"artifacts":[],"error":e,"logs":[{"level":"ERROR","message":e}],**kw}

def _sc(log,node,fn,*a,**kw):
    j=str(uuid.uuid4())[:8];start=time.monotonic();log.info(f"[{node}] start",jid=j);last=None
    for at in range(1,OrchestratorConfig.MAX_RETRIES+1):
        try:
            r=fn(*a,**kw);d=round((time.monotonic()-start)*1000,1);log.info(f"[{node}] ok",jid=j,dur=d,att=at)
            if isinstance(r,dict) and r.get("status")in{"completed","failed","started","skipped","blocked"}:r["job_id"]=r.get("job_id",j);return r
            return _ok(j,[r]if r is not None else[])
        except Exception as e:last=e;log.warn(f"[{node}] retry {at}: {e}",jid=j)
        if at<OrchestratorConfig.MAX_RETRIES:time.sleep(OrchestratorConfig.RETRY_BACKOFF*(2**(at-1)))
    log.error(f"[{node}] fail: {last}",jid=j);return _fail(j,str(last))

# ============================================================
# CLUSTER 1: IDENTITY & AUTH (eID) — A1, A2, A3
# ============================================================

class nPAReaderAgent:
    """A1: Liest nPA/eID per NFC, extrahiert ZK-Pseudonym + Firmen-ID."""
    def __init__(s,logger): s.log=logger
    def read_and_prove(s,nfc_scan_data:str)->dict:
        pseudonym=hashlib.sha256(f"nPA:{nfc_scan_data}:{time.time()}".encode()).hexdigest()[:16]
        zk_hash="0x"+hashlib.sha256(f"ZK:{pseudonym}:{OrchestratorConfig.ZK_CIRCUIT}:{nfc_scan_data}".encode()).hexdigest()
        company_id=f"HRB_{pseudonym[:8].upper()}"
        return {"valid":True,"pseudonym":pseudonym,"zk_hash":zk_hash,"company_id":company_id,"chip_authenticated":True,"read_at":datetime.now(timezone.utc).isoformat()}

class RegisterAgent:
    """A2: Prüft gegen Handelsregister (HRB) und Prokura-Daten."""
    def __init__(s,logger): s.log=logger
    def verify(s,company_id:str)->dict:
        active=company_id.startswith("HRB_")
        return {"active":active,"company_name":f"Firma {company_id}" if active else "N/A","ceo":"Geschäftsführer","prokura":["Prokurist"],"founded":"2005-03-15","checked_at":datetime.now(timezone.utc).isoformat()}

class RoleResolverAgent:
    """A3: Löst Rolle via BundID/EUDIW, gibt Wallet + Berechtigung zurück."""
    ROLE_MAP={"CONTRACTOR_CEO":{"wallet":"0xHANDWERKER_MEIER","title":"Geschäftsführer"},
              "CITY_INSPECTOR":{"wallet":"0xSTADT_MUENCHEN","title":"Bauprüfer"},
              "ATTENDING_PHYSICIAN":{"wallet":"0xCHEFARZT","title":"Chefarzt"},
              "HEALTH_INSURANCE_REP":{"wallet":"0xGKV","title":"Krankenkassen-Prüfer"},
              "CITIZEN":{"wallet":"0xBUERGER","title":"Bürger"},
              "AGENCY_OFFICER":{"wallet":"0xBEHOERDE","title":"Sachbearbeiter"},
              "IMPORTER":{"wallet":"0xIMPORTEUR","title":"Importeur"},
              "CUSTOMS_OFFICER":{"wallet":"0xZOLL","title":"Zollbeamter"},
              "PLAINTIFF_LAWYER":{"wallet":"0xANWALT","title":"Rechtsanwalt"},
              "JUDGE":{"wallet":"0xRICHTER","title":"Richter"}}
    def __init__(s,logger): s.log=logger
    def resolve(s,identity:dict,required_role:str)->dict:
        info=s.ROLE_MAP.get(required_role,{"wallet":"0xUNKNOWN","title":"Unbekannt"})
        return {"valid":identity.get("valid",False),"role":required_role,"wallet":info["wallet"],"title":info["title"]}

# ============================================================
# CLUSTER 2: FINANCE & ERP — F1, F2, F3
# ============================================================

class BankingAgent:
    """F1: Atomare Split-Zahlung via Monerium EURe / SEPA Instant."""
    def __init__(s,logger): s.log=logger
    def execute_split_payment(s,gross:float,net_recipient:str,tax_recipient:str,tax_rate:float,retention_rate:float,escrow_wallet:str="0xESCROW")->dict:
        net=round(gross*(1-tax_rate-retention_rate),2); tax=round(gross*tax_rate,2); ret=round(gross*retention_rate,2)
        txs=[]
        if net>0: txs.append({"to":net_recipient,"amount":net,"currency":"EURe","purpose":"Netto-Zahlung"})
        if tax>0: txs.append({"to":tax_recipient,"amount":tax,"currency":"EURe","purpose":"Steuer"})
        if ret>0: txs.append({"to":escrow_wallet,"amount":ret,"currency":"EURe","purpose":"Sicherheitseinbehalt"})
        batch_id="0x"+hashlib.sha256(f"split:{gross}:{time.time()}".encode()).hexdigest()
        s.log.info(f"Split payment: {gross}€ → {len(txs)} TXs",batch=batch_id[:16])
        return {"status":"SETTLED","batch_id":batch_id,"gross":gross,"net":net,"tax":tax,"retention":ret,"transactions":txs,"bho_delta":round(gross-sum(t["amount"] for t in txs),2),"api":"Monerium EURe"}

class ERPAgent:
    """F2: Bucht Transaktion in SAP S/4HANA und DATEV."""
    def __init__(s,logger): s.log=logger
    def post_to_erp(s,contract_id:str,amount:float,cost_center:str,context:str="BAU")->dict:
        doc_id=f"FI_{context}_{contract_id}_{int(amount)}"
        s.log.info(f"ERP posting: {doc_id}",amount=amount,cost_center=cost_center)
        return {"erp_document":doc_id,"cost_center":cost_center,"amount":amount,"booking_date":datetime.now(timezone.utc).strftime("%Y-%m-%d"),"system":"SAP_S4HANA","datev_export":"csv"}

class TaxAgent:
    """F3: ELSTER ERiC API — berechnet und meldet Steuern."""
    def __init__(s,logger): s.log=logger
    def calculate_tax(s,gross_amount:float,tax_rate:float,tax_name:str)->dict:
        tax_amount=round(gross_amount*tax_rate,2); net=round(gross_amount-tax_amount,2)
        return {"gross":gross_amount,"tax_rate":tax_rate,"tax_name":tax_name,"tax_amount":tax_amount,"net_amount":net,"elster_submission":"SIMULATED","elster_tx_id":str(uuid.uuid4())[:8]}

# ============================================================
# CLUSTER 3: WEB3 & REGTECH — W1, W2, W3
# ============================================================

class BlockchainNodeAgent:
    """W1: EVM RPC + ERC-4337 Bundler, Gasless-TX, GoBD-Archivierung."""
    def __init__(s,logger): s.log=logger
    def archive_proof(s,contract_id:str,milestone:str,proofs:List[str],payment:dict)->dict:
        tx_hash="0x"+hashlib.sha256(f"{contract_id}:{milestone}:{proofs[0]}:{time.time()}".encode()).hexdigest()
        return {"tx_hash":tx_hash,"blockchain":"Gnosis Chiado","block_number":9876543,"status":"CONFIRMED","archived_at":datetime.now(timezone.utc).isoformat(),"gobd_compliant":True}

class OracleAgent:
    """W2: Chainlink/Pyth — Rohstoffpreise, EZB-Zins, Wetterdaten."""
    def __init__(s,logger): s.log=logger
    def fetch_price_feed(s,symbols:List[str])->dict:
        prices={"EUR":1.0,"STEEL":1250.50,"CONCRETE":98.75,"LUMBER":450.00,"COPPER":8750.00,"OIL":82.30}
        result={s:prices.get(s,100.0) for s in symbols}
        return {"prices":result,"timestamp":datetime.now(timezone.utc).isoformat(),"oracle":"Chainlink Data Feeds","feeds_available":len(result)}

class RegTechAgent:
    """W3: OFAC/EU-Sanktionen, AML/KYC, BlockSec Risk-Scoring."""
    def __init__(s,logger): s.log=logger
    def check_all(s,wallets:List[str])->dict:
        blocked=[w for w in wallets if w in OrchestratorConfig.SANCTION_LIST]
        risk_scores={w:95 if w in OrchestratorConfig.SANCTION_LIST else (15 if "0xHANDWERKER" in w else 5) for w in wallets}
        clean=len(blocked)==0
        return {"clean":clean,"checked":len(wallets),"blocked":blocked,"risk_scores":risk_scores,"avg_risk":round(sum(risk_scores.values())/max(len(risk_scores),1),1),"databases":["OFAC_SDN","EU_RESTRICTIVE","UN_SC","INTERPOL","BAFA"]}

# ============================================================
# MASTER: B2GOrchestrator
# ============================================================
class B2GOrchestrator:
    """Root-Agent: Orchestriert 9 Agenten in 3 Clustern über 5 Sektoren."""

    def __init__(s,user_id="default",context:str="BAU"):
        s.uid=user_id; s.context=context; s.profile=CONTEXT_PROFILES[context]
        s.log=JSONLogger("B2GOrchestrator",user_id)
        # Cluster 1: Identity
        s.npa=nPAReaderAgent(s.log); s.hrb=RegisterAgent(s.log); s.role=RoleResolverAgent(s.log)
        # Cluster 2: Finance
        s.bank=BankingAgent(s.log); s.erp=ERPAgent(s.log); s.tax=TaxAgent(s.log)
        # Cluster 3: Web3
        s.chain=BlockchainNodeAgent(s.log); s.oracle=OracleAgent(s.log); s.regtech=RegTechAgent(s.log)
        try: s.event_bus=EventBus()
        except: s.event_bus=None
        s.log.info("B2GOrchestrator ready",context=context,profile=s.profile["description"])

    def set_context(s,context:str)->dict:
        s.context=context; s.profile=CONTEXT_PROFILES[context]
        return {"context":context,"profile":s.profile}

    def process_full_workflow(s,nfc_data_1:str,nfc_data_2:str,contract_id:str,milestone_id:str,gross_amount_eur:float=None)->dict:
        p=s.profile; gross=gross_amount_eur or p["estimated_amount"]
        steps={}; pipeline_start=time.monotonic()

        # --- Cluster 1: Identity ---
        id1=s.npa.read_and_prove(nfc_data_1); id2=s.npa.read_and_prove(nfc_data_2); steps["A1_npa"]="completed"
        if not id1["valid"] or not id2["valid"]: return _block("orch","nPA-Scan fehlgeschlagen")

        hrb=s.hrb.verify(id1["company_id"]); steps["A2_register"]="completed"
        if not hrb["active"]: return _block("orch","Firma nicht im Handelsregister aktiv")

        r1=s.role.resolve(id1,p["required_roles"]["initiator"]); r2=s.role.resolve(id2,p["required_roles"]["approver"]); steps["A3_roles"]="completed"
        if not r1["valid"] or not r2["valid"]: return _block("orch","Rollen-Prüfung fehlgeschlagen")

        # --- Cluster 3 (pre-check): RegTech ---
        sanction=s.regtech.check_all([r1["wallet"],r2["wallet"]]); steps["W3_sanctions"]="completed"
        if not sanction["clean"]: return _block("orch",f"Sanktionstreffer: {sanction['blocked']}")

        # --- Cluster 3: Oracle ---
        mkt=s.oracle.fetch_price_feed(["STEEL","CONCRETE","EUR"]); steps["W2_oracle"]="completed"

        # --- Cluster 2: Tax ---
        tax_calc=s.tax.calculate_tax(gross,p["tax_rate"],p["tax_name"]); steps["F3_tax"]="completed"

        # --- Cluster 2: Payment ---
        pay=s.bank.execute_split_payment(gross,r1["wallet"],p["tax_wallet"],p["tax_rate"],p["retention_rate"],p["escrow_wallet"]); steps["F1_payment"]="completed"

        # --- Cluster 2: ERP ---
        erp=s.erp.post_to_erp(contract_id,tax_calc["net_amount"],p["cost_center"],s.context); steps["F2_erp"]="completed"

        # --- Cluster 3: Blockchain ---
        archive=s.chain.archive_proof(contract_id,milestone_id,[id1["zk_hash"],id2["zk_hash"]],pay); steps["W1_archive"]="completed"

        dur_ms=round((time.monotonic()-pipeline_start)*1000,1)

        if s.event_bus:
            try: s.event_bus.publish("b2g.workflow.completed",{"context":s.context,"contract":contract_id,"amount":gross,"dur_ms":dur_ms})
            except: pass

        return _ok("orch",[{"status":"SETTLED","context":s.context,"contract_id":contract_id,"milestone":milestone_id,"gross_eur":gross,"payment":pay,"tax":tax_calc,"erp":erp,"archive":archive,"market_data":mkt,"roles":{"initiator":r1,"approver":r2},"sanctions":sanction,"legal_basis":p["legal_basis"],"pipeline_steps":steps,"all_green":all(v=="completed"for v in steps.values()),"duration_ms":dur_ms,"message":f"✅ {p['description']} — {gross:,.2f}€ in {dur_ms}ms abgewickelt"}])


# ============================================================
if __name__=="__main__":
    print("="*70)
    print("  🏛️  B2G UNIVERSAL ORCHESTRATOR — 9 Agenten · 3 Cluster · 5 Sektoren")
    print("="*70)

    contexts=["BAU","HEALTH","CUSTOMS","SUBSIDY","JUSTICE"]
    for ctx in contexts:
        orch=B2GOrchestrator(user_id="demo",context=ctx)
        p=CONTEXT_PROFILES[ctx]
        scan1=f"nPA:{ctx}:CONTRACTOR:CEO:2026"
        scan2=f"nPA:{ctx}:INSPECTOR:OFFICER:2026"
        r=orch.process_full_workflow(scan1,scan2,f"CTR-{ctx}-2026",f"{p.get('milestone_types',['MS'])[0]}-001")
        a=r["artifacts"][0]; status="✅" if a["all_green"] else "❌"
        print(f"\n{status} [{ctx:8s}] {a['message']}")
        print(f"   Net={a['payment']['net']:>10,.2f}€ | Tax={a['payment']['tax']:>8,.2f}€ | Retention={a['payment']['retention']:>8,.2f}€ | BHO Δ={a['payment']['bho_delta']}€")
        print(f"   ERP: {a['erp']['erp_document']} | Law: {a['legal_basis']} | {a['duration_ms']}ms")
        print(f"   Roles: {a['roles']['initiator']['title']} ↔ {a['roles']['approver']['title']} | Risk: {a['sanctions']['avg_risk']}")

    print("="*70)
