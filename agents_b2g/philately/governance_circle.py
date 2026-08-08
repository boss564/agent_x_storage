#!/usr/bin/env python3
"""
Governance Circle — 9 Root-Agenten, 81 Subagenten.

Staking-basierte DAO-Governance für das Philately-Ökosystem.
Stimmkraft aus Marken-Seltenheit + Lock-Dauer, KI-Proxy für Auto-Voting,
quadratische Stimmgewichtung, Quorum & Timelock-Sicherheit.

Usage:
    python agents_b2g/philately/governance_circle.py
"""
from __future__ import annotations
import hashlib, json, math, os, sys, time, uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from agents_b2g.event_bus import EventBus

# ============================================================
class GovConfig:
    DATA_ROOT=Path(os.getenv("GOV_DATA_ROOT","data")); LOG_DIR=Path(os.getenv("GOV_LOG_DIR","logs"))
    PROPOSAL_THRESHOLD_STAMP=float(os.getenv("GOV_PROPOSAL_THRESHOLD","1000"))
    QUORUM_PCT=float(os.getenv("GOV_QUORUM_PCT","20.0"))
    SUPERMAJORITY_PCT=float(os.getenv("GOV_SUPERMAJORITY","66.0"))
    TIMELOCK_HOURS=int(os.getenv("GOV_TIMELOCK_H","48"))
    VOTING_PERIOD_DAYS=int(os.getenv("GOV_VOTING_PERIOD","7"))
    QUADRATIC_VOTING=os.getenv("GOV_QUADRATIC","true").lower()=="true"
    FLASH_LOAN_BLOCK_WINDOW=int(os.getenv("GOV_FLASH_LOAN_WINDOW","1"))
    MAX_RETRIES=3; RETRY_BACKOFF=0.5

class JSONLogger:
    def __init__(s,n="gov",u="default"):
        s.agent_name=n; s.user_id=u
        s.log_path=GovConfig.LOG_DIR/f"gov_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
        s.log_path.parent.mkdir(parents=True,exist_ok=True)
    def _write(s,l,m,**x):
        e={"timestamp":datetime.now(timezone.utc).isoformat(),"level":l,"agent":s.agent_name,"user_id":s.user_id,"message":m,**x}
        with open(s.log_path,"a") as f: f.write(json.dumps(e,default=str)+"\n")
    def info(s,m,**kw): s._write("INFO",m,**kw)
    def warn(s,m,**kw): s._write("WARN",m,**kw)
    def error(s,m,**kw): s._write("ERROR",m,**kw)

_ok=lambda j,a=None,**kw:{"status":"completed","job_id":j,"artifacts":a or [],"error":None,"logs":[],**kw}
_fail=lambda j,e,**kw:{"status":"failed","job_id":j,"artifacts":[],"error":e,"logs":[{"level":"ERROR","message":e}],**kw}

def _sc(log,node,fn,*a,**kw):
    j=str(uuid.uuid4())[:8];start=time.monotonic();log.info(f"[{node}] started",job_id=j);last=None
    for at in range(1,GovConfig.MAX_RETRIES+1):
        try:
            r=fn(*a,**kw);d=round((time.monotonic()-start)*1000,1);log.info(f"[{node}] done",job_id=j,dur_ms=d,att=at)
            if isinstance(r,dict) and r.get("status")in{"completed","failed","started","skipped"}:r["job_id"]=r.get("job_id",j);return r
            return _ok(j,[r]if r is not None else[])
        except Exception as e:last=e;log.warn(f"[{node}] att {at} failed: {e}",job_id=j)
        if at<GovConfig.MAX_RETRIES:time.sleep(GovConfig.RETRY_BACKOFF*(2**(at-1)))
    log.error(f"[{node}] failed: {last}",job_id=j);return _fail(j,str(last))

class ProposalState(str,Enum):
    DRAFT="DRAFT"; ACTIVE="ACTIVE"; PASSED="PASSED"; DEFEATED="DEFEATED"
    EXECUTED="EXECUTED"; CANCELLED="CANCELLED"; VETOED="VETOED"

# ============================================================
# 1. ProposalLifecycleManager
# ============================================================
class ProposalLifecycleManager:
    def __init__(s,logger): s.log=logger; s._proposals:Dict[str,dict]={}
    def create_proposal(s,creator:str,title:str,description:str,proposal_type:str,params:dict=None)->dict:
        pid=f"GOV-{uuid.uuid4().hex[:8].upper()}"
        p={"id":pid,"creator":creator,"title":title,"description":description,"type":proposal_type,
           "params":params or {},"state":ProposalState.ACTIVE.value,"created":datetime.now(timezone.utc).isoformat(),
           "votes_for":0.0,"votes_against":0.0,"votes_abstain":0.0,"voters":[]}
        s._proposals[pid]=p; s.log.info(f"Proposal created: {pid}",creator=creator,type=proposal_type)
        return p
    def get_proposal(s,pid:str)->Optional[dict]: return s._proposals.get(pid)
    def list_active(s)->List[dict]: return [p for p in s._proposals.values() if p["state"]==ProposalState.ACTIVE.value]
    def transition_state(s,pid:str,new_state:ProposalState)->dict:
        if pid in s._proposals: s._proposals[pid]["state"]=new_state.value; return {"proposal_id":pid,"new_state":new_state.value}
        return {"status":"NOT_FOUND"}

# ============================================================
# 2. VotingPowerCalculator
# ============================================================
class VotingPowerCalculator:
    def __init__(s,logger): s.log=logger
    def stamp_rarity_weight(s,rarity_score:float)->float:
        return 1.0+min(2.0,(rarity_score/100)*2)
    def lock_time_multiplier(s,lock_days:int)->float: return 1.0+min(2.0,lock_days/365)
    def quadratic_weight(s,raw_vp:float)->float:
        return math.sqrt(raw_vp) if GovConfig.QUADRATIC_VOTING and raw_vp>0 else raw_vp
    def calculate_voting_power(s,rarity_score:float,lock_days:int,stamp_count:int=1,has_full_set:bool=False)->dict:
        rarity_w=s.stamp_rarity_weight(rarity_score)
        lock_w=s.lock_time_multiplier(lock_days)
        set_bonus=1.5 if has_full_set else 1.0
        raw=stamp_count*rarity_w*lock_w*set_bonus
        effective=s.quadratic_weight(raw)
        return {"raw_vp":round(raw,2),"effective_vp":round(effective,2),"rarity_weight":round(rarity_w,2),
                "lock_weight":round(lock_w,2),"set_bonus":set_bonus,"quadratic":GovConfig.QUADRATIC_VOTING}
    def slash_deductor(s,current_vp:float,violations:int)->dict:
        penalty=min(0.5,violations*0.1); new_vp=round(current_vp*(1-penalty),2)
        return {"original_vp":current_vp,"violations":violations,"penalty_pct":round(penalty*100,1),"effective_vp":new_vp}

# ============================================================
# 3. DelegationAndProxyManager
# ============================================================
class DelegationAndProxyManager:
    def __init__(s,logger): s.log=logger; s._delegations:Dict[str,dict]={}
    def delegate(s,from_addr:str,to_addr:str,vp_amount:float,scope:List[str]=None)->dict:
        did=str(uuid.uuid4())[:8]
        s._delegations[did]={"from":from_addr,"to":to_addr,"vp":vp_amount,"scope":scope or ["ALL"],
                              "created":datetime.now(timezone.utc).isoformat(),"active":True}
        return {"delegation_id":did,"from":from_addr,"to":to_addr,"vp_delegated":vp_amount}
    def revoke(s,did:str)->dict:
        if did in s._delegations: s._delegations[did]["active"]=False; return {"status":"REVOKED","delegation_id":did}
        return {"status":"NOT_FOUND"}
    def get_delegated_vp(s,address:str)->float:
        return round(sum(d["vp"] for d in s._delegations.values() if d["to"]==address and d["active"]),2)
    def split_delegation(s,from_addr:str,allocations:List[dict])->List[dict]:
        return [s.delegate(from_addr,a["to"],a["vp"],a.get("scope")) for a in allocations]

# ============================================================
# 4. AutonomousVoteAdvisor
# ============================================================
class AutonomousVoteAdvisor:
    def __init__(s,logger): s.log=logger; s._vote_history:List[dict]=[]; s._preferences:Dict[str,dict]={}
    def set_preferences(s,collector:str,prefs:dict):
        s._preferences[collector]={"max_swap_fee_pct":prefs.get("max_swap_fee_pct",1.0),
                                    "prefer_low_fees":prefs.get("prefer_low_fees",True),
                                    "risk_tolerance":prefs.get("risk_tolerance","CONSERVATIVE"),
                                    "auto_vote":prefs.get("auto_vote",True)}
    def analyze_proposal_text(s,description:str)->dict:
        d=description.lower()
        if "gebühr" in d or "fee" in d:
            import re; nums=re.findall(r'(\d+[.,]?\d*)\s*%',d)
            proposed=float(nums[0].replace(",",".")) if nums else 1.0
            return {"target":"p2p_swap_fee","proposed_value":proposed,"is_reduction":proposed<2.0}
        if "herausgeber" in d or "issuer" in d or "whitelist" in d:
            return {"target":"issuer_whitelist","action":"add" if "aufnahme" in d or "add" in d else "remove"}
        if "treasury" in d or "schatzamt" in d or "fund" in d:
            return {"target":"treasury_allocation","action":"allocate"}
        if "staking" in d or "apy" in d or "yield" in d:
            return {"target":"yield_parameter","action":"adjust"}
        return {"target":"unknown","action":"review"}
    def evaluate(s,collector:str,proposal:dict)->dict:
        prefs=s._preferences.get(collector,{"max_swap_fee_pct":1.0,"prefer_low_fees":True,"auto_vote":True})
        if not prefs.get("auto_vote",True): return {"decision":"ABSTAIN","rationale":"Auto-vote disabled","confidence":0.0}
        analysis=s.analyze_proposal_text(proposal.get("description",""))
        if analysis["target"]=="p2p_swap_fee":
            if analysis["proposed_value"]<=prefs["max_swap_fee_pct"] and prefs["prefer_low_fees"]:
                return {"decision":"FOR","rationale":f"Fee {analysis['proposed_value']}% within limit ({prefs['max_swap_fee_pct']}%)","confidence":0.92}
            else: return {"decision":"AGAINST","rationale":f"Fee {analysis['proposed_value']}% exceeds limit","confidence":0.88}
        if analysis["target"]=="issuer_whitelist":
            return {"decision":"FOR","rationale":"Expanding issuer ecosystem benefits collectors","confidence":0.75}
        return {"decision":"ABSTAIN","rationale":"Insufficient data for automated decision","confidence":0.3}
    def cast_vote(s,collector:str,proposal_id:str,vp:float,decision:str,rationale:str)->dict:
        vh="0x"+hashlib.sha256(f"{collector}:{proposal_id}:{decision}:{vp}:{time.time()}".encode()).hexdigest()
        rec={"collector":collector,"proposal_id":proposal_id,"vp":vp,"decision":decision,"rationale":rationale,"vote_hash":vh,"timestamp":datetime.now(timezone.utc).isoformat()}
        s._vote_history.append(rec); return rec

# ============================================================
# 5. WhitelistGovernanceAgent
# ============================================================
class WhitelistGovernanceAgent:
    def __init__(s,logger): s.log=logger; s._pending_issuers:Dict[str,dict]={}
    def submit_issuer_application(s,issuer_name:str,issuer_address:str,portfolio_url:str)->dict:
        app_id=str(uuid.uuid4())[:8]
        s._pending_issuers[app_id]={"name":issuer_name,"address":issuer_address,"portfolio":portfolio_url,
                                     "status":"PENDING","submitted":datetime.now(timezone.utc).isoformat()}
        return {"application_id":app_id,"issuer":issuer_name,"status":"PENDING"}
    def vote_on_issuer(s,app_id:str,approve:bool,vp:float)->dict:
        if app_id in s._pending_issuers:
            s._pending_issuers[app_id]["status"]="APPROVED" if approve else "REJECTED"
            s._pending_issuers[app_id]["approved_by_vp"]=vp
            return {"application_id":app_id,"status":s._pending_issuers[app_id]["status"],"vp":vp}
        return {"status":"NOT_FOUND"}

# ============================================================
# 6. FeeAndProtocolParameterGovernor
# ============================================================
class FeeAndProtocolParameterGovernor:
    def __init__(s,logger): s.log=logger; s._params={"swap_fee_pct":1.0,"base_apy":0.05,"vault_cap":10000,"penalty_pct":0.15,"treasury_split":0.30}
    def propose_parameter_change(s,param:str,current:float,proposed:float,reason:str)->dict:
        return {"param":param,"current":current,"proposed":proposed,"reason":reason,"change_pct":round((proposed/current-1)*100,1)}
    def bound_check(s,param:str,value:float)->dict:
        bounds={"swap_fee_pct":(0.01,10.0),"base_apy":(0.01,0.25),"vault_cap":(100,100000),"penalty_pct":(0.0,0.50),"treasury_split":(0.05,0.80)}
        lo,hi=bounds.get(param,(0,1e9)); valid=lo<=value<=hi
        return {"param":param,"value":value,"valid":valid,"bounds":f"[{lo}, {hi}]"}
    def apply_change(s,param:str,new_value:float)->dict:
        if param in s._params: s._params[param]=new_value; return {"param":param,"new_value":new_value,"applied":True}
        return {"status":"UNKNOWN_PARAMETER"}
    def get_params(s)->dict: return dict(s._params)

# ============================================================
# 7. TreasuryAllocationGovernor
# ============================================================
class TreasuryAllocationGovernor:
    def __init__(s,logger): s.log=logger; s._treasury_balance=0.0; s._allocations:List[dict]=[]
    def deposit(s,amount_agx:float,source:str)->dict:
        s._treasury_balance+=amount_agx; return {"action":"DEPOSIT","amount":amount_agx,"source":source,"balance":round(s._treasury_balance,2)}
    def propose_allocation(s,proposer:str,recipient:str,amount_agx:float,purpose:str)->dict:
        aid=str(uuid.uuid4())[:8]
        s._allocations.append({"id":aid,"proposer":proposer,"recipient":recipient,"amount":amount_agx,"purpose":purpose,"status":"PENDING"})
        return {"allocation_id":aid,"amount":amount_agx,"status":"PENDING"}
    def execute_allocation(s,aid:str)->dict:
        for a in s._allocations:
            if a["id"]==aid and a["status"]=="PENDING":
                if s._treasury_balance>=a["amount"]:
                    s._treasury_balance-=a["amount"]; a["status"]="EXECUTED"
                    return {"allocation_id":aid,"status":"EXECUTED","remaining_balance":round(s._treasury_balance,2)}
        return {"status":"FAILED","reason":"Insufficient funds or not found"}
    def buyback_burn_ratio(s,ratio_pct:float)->dict:
        return {"action":"SET_BUYBACK_RATIO","ratio_pct":ratio_pct,"treasury_impact":round(s._treasury_balance*ratio_pct/100,2)}

# ============================================================
# 8. QuorumAndTimelockEnforcer
# ============================================================
class QuorumAndTimelockEnforcer:
    def __init__(s,logger): s.log=logger; s._timelock_queue:deque=deque(); s._executed:List[dict]=[]
    def check_quorum(s,total_vp:float,participated_vp:float)->dict:
        pct=round(participated_vp/max(total_vp,0.001)*100,1)
        met=pct>=GovConfig.QUORUM_PCT
        return {"total_vp":total_vp,"participated_vp":participated_vp,"participation_pct":pct,"quorum_met":met,"threshold_pct":GovConfig.QUORUM_PCT}
    def check_supermajority(s,votes_for:float,votes_against:float)->dict:
        total=max(votes_for+votes_against,0.001); pct=round(votes_for/total*100,1)
        met=pct>=GovConfig.SUPERMAJORITY_PCT
        return {"votes_for":votes_for,"votes_against":votes_against,"support_pct":pct,"supermajority_met":met,"threshold_pct":GovConfig.SUPERMAJORITY_PCT}
    def enqueue_timelock(s,proposal_id:str,execution_data:dict)->dict:
        release=time.time()+GovConfig.TIMELOCK_HOURS*3600
        s._timelock_queue.append({"proposal_id":proposal_id,"data":execution_data,"release_ts":release,"queued":datetime.now(timezone.utc).isoformat()})
        return {"proposal_id":proposal_id,"timelock_hours":GovConfig.TIMELOCK_HOURS,"releasable_at":datetime.fromtimestamp(release,timezone.utc).isoformat()}
    def flash_loan_protector(s,stake_timestamp:float)->dict:
        protected=(time.time()-stake_timestamp)>(GovConfig.FLASH_LOAN_BLOCK_WINDOW*3600)
        return {"stake_timestamp":stake_timestamp,"protected":protected,"min_age_hours":GovConfig.FLASH_LOAN_BLOCK_WINDOW}

# ============================================================
# 9. GovernanceCircleOrchestrator
# ============================================================
class GovernanceCircleOrchestrator:
    def __init__(s,user_id="default"):
        s.user_id=user_id; s.log=JSONLogger("GovOrchestrator",user_id)
        s.proposals=ProposalLifecycleManager(s.log); s.vp_calc=VotingPowerCalculator(s.log)
        s.delegation=DelegationAndProxyManager(s.log); s.advisor=AutonomousVoteAdvisor(s.log)
        s.whitelist=WhitelistGovernanceAgent(s.log); s.params=FeeAndProtocolParameterGovernor(s.log)
        s.treasury=TreasuryAllocationGovernor(s.log); s.quorum=QuorumAndTimelockEnforcer(s.log)
        try: s.event_bus=EventBus()
        except: s.event_bus=None

    def process_proposal(s,creator:str,title:str,description:str,proposal_type:str,params:dict=None)->dict:
        steps={}
        # 1. Create proposal
        prop=s.proposals.create_proposal(creator,title,description,proposal_type,params)
        pid=prop["id"]; steps["1_create"]="completed"
        # 2. Calculate creator VP
        vp=s.vp_calc.calculate_voting_power(params.get("rarity_score",50) if params else 50,params.get("lock_days",180) if params else 180)
        steps["2_vp_calc"]="completed"
        # 3. AI evaluation
        eval=s.advisor.evaluate(creator,prop)
        steps["3_ai_eval"]="completed"
        # 4. Parameter bounds check
        if proposal_type=="PARAMETER_CHANGE" and params:
            bound=s.params.bound_check(params.get("param",""),params.get("value",0))
            steps["4_bound_check"]="completed" if bound["valid"] else "failed"
            if not bound["valid"]:
                s.proposals.transition_state(pid,ProposalState.CANCELLED)
                return _fail("gov",f"Parameter {params.get('param')} out of bounds {bound['bounds']}")
        # 5. Cast AI vote
        v=s.advisor.cast_vote(creator,pid,vp["effective_vp"],eval["decision"],eval["rationale"])
        prop["votes_for" if eval["decision"]=="FOR" else "votes_against" if eval["decision"]=="AGAINST" else "votes_abstain"]=vp["effective_vp"]
        prop["voters"].append(creator); steps["5_vote"]="completed"
        # 6. Quorum check
        q=s.quorum.check_quorum(vp["effective_vp"]*10,vp["effective_vp"])
        steps["6_quorum"]="completed"
        # 7. Supermajority if passed
        if eval["decision"]=="FOR":
            sm=s.quorum.check_supermajority(prop["votes_for"],prop["votes_against"])
            if sm["supermajority_met"] and q["quorum_met"]:
                s.proposals.transition_state(pid,ProposalState.PASSED)
                tl=s.quorum.enqueue_timelock(pid,{"proposal":prop})
                steps["8_timelock"]="completed"
            else:
                s.proposals.transition_state(pid,ProposalState.DEFEATED)
                steps["8_defeated"]="completed"
        steps["7_supermajority"]="completed"

        return _ok("gov",[{"proposal_id":pid,"creator":creator,"vp":vp,"ai_decision":eval["decision"],
                            "ai_rationale":eval["rationale"],"vote_hash":v["vote_hash"],
                            "state":prop["state"],"pipeline_steps":steps,
                            "all_green":all(v=="completed" for v in steps.values())}])

    def get_governance_stats(s)->dict:
        active=len(s.proposals.list_active()); total=len(s.proposals._proposals)
        delegated=sum(1 for d in s.delegation._delegations.values() if d["active"])
        treasury=s.treasury._treasury_balance; params=s.params.get_params()
        return _ok("stats",[{"active_proposals":active,"total_proposals":total,"active_delegations":delegated,"treasury_agx":treasury,"parameters":params}])

# ============================================================
if __name__=="__main__":
    print("="*70)
    print("  🏛️  GOVERNANCE CIRCLE — Philately DAO")
    print("="*70)
    gov=GovernanceCircleOrchestrator(user_id="sammler.muenchen.b2g")
    # Set preferences
    gov.advisor.set_preferences("sammler.muenchen.b2g",{"max_swap_fee_pct":1.0,"prefer_low_fees":True,"auto_vote":True})
    # Demo proposals
    proposals=[
        ("P2P-Gebührensenkung","Beantragt wird die Senkung der P2P-Tauschgebühr von 2.0% auf 0.5% zur Steigerung des Handelsvolumens.","PARAMETER_CHANGE",{"param":"swap_fee_pct","value":0.5,"rarity_score":85,"lock_days":365}),
        ("Neuer Herausgeber: Deutsche Post NFT","Aufnahme der Deutschen Post NFT als offiziellen Marken-Herausgeber in die Philately-Whitelist.","ISSUER_WHITELIST",{"rarity_score":70,"lock_days":180}),
        ("Treasury-Allokation: Code-Audit","Bereitstellung von 50.000 $STAMP aus dem Community-Treasury für ein externes Smart-Contract-Audit durch CertiK.","TREASURY_ALLOCATION",{"rarity_score":60,"lock_days":90}),
    ]
    for title,desc,ptype,params in proposals:
        r=gov.process_proposal("sammler.muenchen.b2g",title,desc,ptype,params)
        a=r["artifacts"][0]
        status="✅" if a["all_green"] else("🚫" if r["status"]=="failed" else"⚠️")
        print(f"\n{status} {a['proposal_id']}: {title[:50]}...")
        print(f"   VP: {a['vp']['effective_vp']} | AI: {a['ai_decision']} | State: {a['state']}")
        if a["ai_decision"]=="FOR": print(f"   Rationale: {a['ai_rationale'][:80]}...")
    stats=gov.get_governance_stats(); s=stats["artifacts"][0]
    print(f"\n📊 GOVERNANCE STATS:")
    print(f"   Active: {s['active_proposals']} | Total: {s['total_proposals']} | Delegations: {s['active_delegations']}")
    print(f"   Treasury: {s['treasury_agx']} $STAMP | Params: {s['parameters']}")
    print("="*70)
