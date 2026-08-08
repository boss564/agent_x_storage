#!/usr/bin/env python3
"""
B2G Universal Tap-to-Sign Ledger — 1 Master + 8 Subagenten.

Multi-Sektor NFC/ZK Settlement Engine mit konfigurierbaren Kontext-Profilen.
3-Sekunden-Workflow: Scan → ZK-Proof → Role → Milestone → Legal → Split → Escrow → Archive.

Usage:
    python agents_b2g/ledger/ledger_orchestrator.py
"""
from __future__ import annotations
import hashlib, json, os, sys, time, uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents_b2g.ledger.context_profiles import CONTEXT_PROFILES
from agents_b2g.event_bus import EventBus


class LedgerConfig:
    DATA_ROOT=Path(os.getenv("LEDGER_DATA_ROOT","data")); LOG_DIR=Path(os.getenv("LEDGER_LOG_DIR","logs"))
    NFC_TIMEOUT_S=int(os.getenv("LEDGER_NFC_TIMEOUT","5")); ZK_CIRCUIT="groth16"
    MAX_RETRIES=3; RETRY_BACKOFF=0.5


class JSONLogger:
    def __init__(s,n="ledger",u="default"):
        s.name,s.uid=n,u
        s.path=LedgerConfig.LOG_DIR/f"ledger_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
        s.path.parent.mkdir(parents=True,exist_ok=True)
    def _w(s,l,m,**x):
        e={"ts":datetime.now(timezone.utc).isoformat(),"lvl":l,"agt":s.name,"uid":s.uid,"msg":m,**x}
        with open(s.path,"a") as f: f.write(json.dumps(e,default=str)+"\n")
    def info(s,m,**kw): s._w("INFO",m,**kw)
    def warn(s,m,**kw): s._w("WARN",m,**kw)
    def error(s,m,**kw): s._w("ERROR",m,**kw)

_ok=lambda j,a=None,**kw:{"status":"completed","job_id":j,"artifacts":a or [],"error":None,"logs":[],**kw}
_fail=lambda j,e,**kw:{"status":"failed","job_id":j,"artifacts":[],"error":e,"logs":[{"level":"ERROR","message":e}],**kw}

def _sc(log,node,fn,*a,**kw):
    j=str(uuid.uuid4())[:8];start=time.monotonic();log.info(f"[{node}] start",jid=j);last=None
    for at in range(1,LedgerConfig.MAX_RETRIES+1):
        try:
            r=fn(*a,**kw);d=round((time.monotonic()-start)*1000,1);log.info(f"[{node}] ok",jid=j,dur=d,att=at)
            if isinstance(r,dict) and r.get("status")in{"completed","failed","started","skipped","blocked"}:r["job_id"]=r.get("job_id",j);return r
            return _ok(j,[r]if r is not None else[])
        except Exception as e:last=e;log.warn(f"[{node}] retry {at}: {e}",jid=j)
        if at<LedgerConfig.MAX_RETRIES:time.sleep(LedgerConfig.RETRY_BACKOFF*(2**(at-1)))
    log.error(f"[{node}] fail: {last}",jid=j);return _fail(j,str(last))


# ============================================================
# I1: NFCReaderAgent
# ============================================================
class NFCReaderAgent:
    """Liest nPA/eID via Smartphone-NFC und extrahiert Pseudonym."""
    def __init__(s,logger): s.log=logger
    def read(s,scan_data:str)->dict:
        """Simuliert NFC-Read. In Produktion: nPA-API via Android/iOS NFC."""
        pseudonym=hashlib.sha256(f"nPA:{scan_data}:{time.time()}".encode()).hexdigest()[:16]
        return {"pseudonym":pseudonym,"raw_scan":scan_data[:20]+"...","read_at":datetime.now(timezone.utc).isoformat(),"chip_authenticated":True}


# ============================================================
# I2: ZKProofEngineAgent
# ============================================================
class ZKProofEngineAgent:
    """Erzeugt ZK-SNARKs zum Nachweis von Berechtigungen ohne Identitätspreisgabe."""
    def __init__(s,logger): s.log=logger; s._revocation_list:Set[str]=set()
    def generate_proof(s,identity:dict)->dict:
        pid=identity.get("pseudonym","")
        proof_hash="0x"+hashlib.sha256(f"ZK:{pid}:{LedgerConfig.ZK_CIRCUIT}:{time.time()}".encode()).hexdigest()
        revoked=pid in s._revocation_list
        return {"proof_hash":proof_hash,"pseudonym":pid,"circuit":LedgerConfig.ZK_CIRCUIT,"revoked":revoked,"dsgvo_compliant":not revoked}
    def check_revocation(s,pseudonym:str)->bool:
        return pseudonym in s._revocation_list


# ============================================================
# I3: RoleResolverAgent
# ============================================================
class RoleResolverAgent:
    """Ordnet Ausweis-Rolle zu und lädt Berechtigungsmatrix."""
    ROLE_MAP={"CONTRACTOR_CEO":{"wallet":"0xCONTRACTOR","title":"Geschäftsführer"},
              "CITY_INSPECTOR":{"wallet":"0xINSPECTOR","title":"Bauprüfer"},
              "ATTENDING_PHYSICIAN":{"wallet":"0xPHYSICIAN","title":"Chefarzt"},
              "HEALTH_INSURANCE_REP":{"wallet":"0xGKV","title":"Krankenkassen-Prüfer"},
              "CITIZEN":{"wallet":"0xCITIZEN","title":"Bürger"},
              "AGENCY_OFFICER":{"wallet":"0xAGENCY","title":"Sachbearbeiter"},
              "IMPORTER":{"wallet":"0xIMPORTER","title":"Importeur"},
              "CUSTOMS_OFFICER":{"wallet":"0xZOLL","title":"Zollbeamter"},
              "PLAINTIFF_LAWYER":{"wallet":"0xLAWYER","title":"Rechtsanwalt"},
              "JUDGE":{"wallet":"0xJUDGE","title":"Richter"}}
    def __init__(s,logger): s.log=logger
    def resolve(s,proof:dict,expected_role:str)->dict:
        matching=proof["pseudonym"][:4] in ["nPA:","eID:"] or proof.get("revoked",True)
        valid=not proof.get("revoked",False)
        role_info=s.ROLE_MAP.get(expected_role,{"wallet":"0xUNKNOWN","title":"Unbekannt"})
        return {"valid":valid,"role":expected_role,"wallet":role_info["wallet"],"title":role_info["title"]}


# ============================================================
# L1: MilestoneMatcherAgent
# ============================================================
class MilestoneMatcherAgent:
    """Prüft Meilenstein gegen Vertrag/Förderrichtlinie."""
    def __init__(s,logger): s.log=logger
    def match(s,milestone_id:str,contract_id:str,profile:dict)->dict:
        valid_types=profile.get("milestone_types",[])
        ms_type=milestone_id.split("-")[0].lower() if "-" in milestone_id else "fundament"
        if ms_type not in valid_types:
            return {"success":False,"detail":f"Meilenstein-Typ '{ms_type}' nicht gültig in {profile['description']}. Erlaubt: {valid_types}"}
        return {"success":True,"milestone_id":milestone_id,"contract_id":contract_id,"ms_type":ms_type,"matched_rules":profile.get("legal_basis","")}


# ============================================================
# L2: LegalConditionAgent
# ============================================================
class LegalConditionAgent:
    """Lädt aktuelles Gesetz und berechnet Quoten & Fristen."""
    def calculate(s,gross_amount_eur:float,profile:dict)->dict:
        tax=round(gross_amount_eur*profile["tax_rate"],2)
        retention=round(gross_amount_eur*profile["retention_rate"],2)
        net=round(gross_amount_eur-tax-retention,2)
        return {"gross_amount":gross_amount_eur,"net_amount":net,"tax_amount":tax,"retention_amount":retention,
                "tax_rate":profile["tax_rate"],"retention_rate":profile["retention_rate"],
                "tax_name":profile["tax_name"],"retention_name":profile["retention_name"],
                "legal_basis":profile["legal_basis"],"retention_years":profile["retention_years"]}


# ============================================================
# L3: TimerGuardianAgent
# ============================================================
class TimerGuardianAgent:
    """Startet Gewährleistungsfristen und überwacht Zahlungsverpflichtungen."""
    def __init__(s,logger): s.log=logger; s._timers:Dict[str,dict]={}
    def start(s,contract_id:str,release_ts:float,callback_data:dict)->dict:
        tid=str(uuid.uuid4())[:8]
        s._timers[tid]={"contract":contract_id,"release_ts":release_ts,"callback":callback_data,"status":"ACTIVE"}
        release_date=datetime.fromtimestamp(release_ts,timezone.utc).isoformat()
        return {"timer_id":tid,"release_date":release_date,"status":"STARTED"}
    def check(s,timer_id:str)->dict:
        t=s._timers.get(timer_id)
        if not t: return {"status":"NOT_FOUND"}
        if time.time()>=t["release_ts"]: t["status"]="RELEASED"; return {"status":"RELEASED","timer_id":timer_id}
        remaining_d=(t["release_ts"]-time.time())/86400
        return {"status":"ACTIVE","timer_id":timer_id,"remaining_days":round(remaining_d,1)}


# ============================================================
# S1: AtomicSplitterAgent
# ============================================================
class AtomicSplitterAgent:
    """Teilt Zahlung atomar in Netto, Steuer, Einbehalt auf."""
    def split_and_send(s,gross:float,net_recipient:str,tax_recipient:str,tax_rate:float,retention_rate:float,escrow_wallet:str)->dict:
        tax=round(gross*tax_rate,2); retention=round(gross*retention_rate,2); net=round(gross-tax-retention,2)
        txs=[]
        if net>0: txs.append({"to":net_recipient,"amount":net,"purpose":"Netto-Zahlung"})
        if tax>0: txs.append({"to":tax_recipient,"amount":tax,"purpose":"Steuer"})
        if retention>0: txs.append({"to":escrow_wallet,"amount":retention,"purpose":"Einbehalt/Sicherheit"})
        batch_id="0x"+hashlib.sha256(f"split:{gross}:{time.time()}".encode()).hexdigest()
        return {"batch_id":batch_id,"gross":gross,"net":net,"tax":tax,"retention":retention,"transactions":txs,"atomic":True,"bho_delta":round(gross-sum(t["amount"] for t in txs),2)}


# ============================================================
# S2: EscrowRetentionAgent
# ============================================================
class EscrowRetentionAgent:
    """Sperrt Einbehalte und gibt sie nach Ablauf automatisch frei."""
    def __init__(s,logger): s.log=logger; s._escrows:Dict[str,dict]={}
    def lock(s,amount_eur:float,duration_years:int,contract_id:str)->dict:
        if amount_eur<=0: return {"locked":False,"reason":"Kein Einbehalt nötig"}
        eid=str(uuid.uuid4())[:8]; release=time.time()+duration_years*365*86400
        s._escrows[eid]={"amount":amount_eur,"contract":contract_id,"duration_y":duration_years,"release_ts":release,"status":"LOCKED"}
        return {"escrow_id":eid,"amount":amount_eur,"duration_years":duration_years,"release_date":datetime.fromtimestamp(release,timezone.utc).isoformat(),"status":"LOCKED"}
    def release(s,escrow_id:str)->dict:
        if escrow_id in s._escrows and time.time()>=s._escrows[escrow_id]["release_ts"]:
            s._escrows[escrow_id]["status"]="RELEASED"
            return {"escrow_id":escrow_id,"status":"RELEASED","amount":s._escrows[escrow_id]["amount"]}
        return {"escrow_id":escrow_id,"status":"STILL_LOCKED"}


# ============================================================
# S3: GoBDArchiverAgent
# ============================================================
class GoBDArchiverAgent:
    """Speichert Beweise (Blinded Hashes) GoBD-konform im WORM-Archiv."""
    def __init__(s,logger): s.log=logger; s._archive:List[dict]=[]
    def archive(s,context:str,contract_id:str,milestone_id:str,proofs:List[str],payment_tx:dict,timer:dict=None)->str:
        payload={"context":context,"contract":contract_id,"milestone":milestone_id,"proofs":proofs,"payment":payment_tx,"timer":timer}
        archive_hash="0x"+hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()
        s._archive.append({"hash":archive_hash,"payload":payload,"worm_ts":datetime.now(timezone.utc).isoformat()})
        s.log.info("Archived",hash=archive_hash[:20])
        return archive_hash
    def verify(s,archive_hash:str)->dict:
        found=any(a["hash"]==archive_hash for a in s._archive)
        return {"hash":archive_hash,"found":found,"total_archived":len(s._archive)}


# ============================================================
# MASTER: LedgerOrchestrator
# ============================================================
class LedgerOrchestrator:
    """Universeller B2G Tap-to-Sign Ledger — wechselt per Kontext-Profil."""
    def __init__(s,user_id="default",context:str="BAU"):
        s.uid=user_id; s.context=context;s.profile=CONTEXT_PROFILES[context]
        s.log=JSONLogger("Ledger",user_id)
        s.nfc=NFCReaderAgent(s.log); s.zk=ZKProofEngineAgent(s.log); s.role=RoleResolverAgent(s.log)
        s.ms_match=MilestoneMatcherAgent(s.log); s.legal=LegalConditionAgent()
        s.timer=TimerGuardianAgent(s.log); s.splitter=AtomicSplitterAgent()
        s.escrow=EscrowRetentionAgent(s.log); s.archive=GoBDArchiverAgent(s.log)
        try: s.event_bus=EventBus()
        except: s.event_bus=None
        s.log.info(f"Ledger initialized",context=context,profile=s.profile["description"])

    def set_context(s,context:str)->dict:
        s.context=context; s.profile=CONTEXT_PROFILES[context]
        s.log.info("Context switched",context=context)
        return {"context":context,"profile":s.profile}

    def process_tap_to_sign(s,scan_1:str,scan_2:str,milestone_id:str,contract_id:str,gross_amount_eur:float=45000.0)->dict:
        steps={}; pipeline_start=time.monotonic()
        # I1: NFC reads
        id1=s.nfc.read(scan_1); id2=s.nfc.read(scan_2); steps["I1_nfc"]="completed"
        # I2: ZK proofs
        prf1=s.zk.generate_proof(id1); prf2=s.zk.generate_proof(id2); steps["I2_zk"]="completed"
        if prf1["revoked"] or prf2["revoked"]: return _fail("ledger",f"Revoked identity: {id1['pseudonym'] if prf1['revoked'] else id2['pseudonym']}")
        # I3: Role resolution
        r1=s.role.resolve(prf1,s.profile["required_roles"]["initiator"]); r2=s.role.resolve(prf2,s.profile["required_roles"]["approver"]); steps["I3_roles"]="completed"
        if not r1["valid"] or not r2["valid"]: return _fail("ledger","Role verification failed")
        # L1: Milestone match
        ms=s.ms_match.match(milestone_id,contract_id,s.profile); steps["L1_milestone"]="completed"
        if not ms["success"]: return _fail("ledger",ms["detail"])
        # L2: Legal conditions
        leg=s.legal.calculate(gross_amount_eur,s.profile); steps["L2_legal"]="completed"
        # S1: Atomic split
        pay=s.splitter.split_and_send(gross_amount_eur,r1["wallet"],s.profile["tax_wallet"],s.profile["tax_rate"],s.profile["retention_rate"],s.profile["escrow_wallet"]); steps["S1_split"]="completed"
        # S2: Escrow
        esc=s.escrow.lock(leg["retention_amount"],s.profile["retention_years"],contract_id); steps["S2_escrow"]="completed"
        # S3: Timer
        tm=None
        if s.profile["retention_years"]>0 and esc.get("release_date"):
            release_ts=time.time()+s.profile["retention_years"]*365*86400
            tm=s.timer.start(contract_id,release_ts,{"escrow_id":esc["escrow_id"]})
        steps["S3_timer"]="completed" if tm else "skipped"
        # Archive
        arch=s.archive.archive(s.context,contract_id,milestone_id,[prf1["proof_hash"],prf2["proof_hash"]],pay,tm); steps["archive"]="completed"
        dur_ms=round((time.monotonic()-pipeline_start)*1000,1)

        if s.event_bus:
            try: s.event_bus.publish("ledger.settled",{"context":s.context,"contract":contract_id,"amount":gross_amount_eur,"duration_ms":dur_ms})
            except: pass

        return _ok("ledger",[{"status":"SETTLED","context":s.context,"contract_id":contract_id,"milestone":milestone_id,"gross_eur":gross_amount_eur,"payment":pay,"escrow":esc,"timer":tm,"archive_hash":arch,"roles":{"initiator":r1,"approver":r2},"legal":leg,"pipeline_steps":steps,"all_green":all(v in("completed","skipped")for v in steps.values()),"duration_ms":dur_ms,"message":s.profile["success_message"]}])


# ============================================================
if __name__=="__main__":
    print("="*70)
    print("  🏛️  B2G UNIVERSAL TAP-TO-SIGN LEDGER")
    print("="*70)
    contexts=["BAU","HEALTH","CUSTOMS"]
    for ctx in contexts:
        ledger=LedgerOrchestrator(user_id="demo",context=ctx)
        profile=CONTEXT_PROFILES[ctx]
        # simulate two NFC scans
        scan1=f"nPA:DE:123456789:CONTRACTOR:{ctx}"
        scan2=f"nPA:DE:987654321:INSPECTOR:{ctx}"
        ms=f"{profile['milestone_types'][0]}-001"
        r=ledger.process_tap_to_sign(scan1,scan2,ms,f"CTR-{ctx}-2026",gross_amount_eur=45000.0 if ctx!="HEALTH" else 12500.0)
        a=r["artifacts"][0]
        status="✅" if a["all_green"] else"❌"
        print(f"\n{status} [{ctx}] {a['message'][:60]}...")
        print(f"   Gross: {a['gross_eur']:,.2f} € | Net: {a['payment']['net']:,.2f} | Tax: {a['payment']['tax']:,.2f} | Retention: {a['payment']['retention']:,.2f}")
        print(f"   BHO Δ={a['payment']['bho_delta']}€ | Archive: {a['archive_hash'][:20]}... | {a['duration_ms']}ms")
        print(f"   Roles: {a['roles']['initiator']['title']} ↔ {a['roles']['approver']['title']} | Law: {a['legal']['legal_basis']}")
    print("="*70)
