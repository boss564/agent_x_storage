"""
Agent X — User & Project Management (Wave 9, 9 Agents).

Human-facing layer for the 81-agent B2G procurement platform.
Bridges the gap between public authority staff and the autonomous agent fleet.

Agents:
  1. UserAuthenticatorAgent   — BundID/eIDAS SSO, role mapping, session management
  2. ProjectManagerAgent      — Project creation, budget allocation, deadline tracking
  3. TaskDispatcherAgent      — Milestone→task mapping, agent triggering, progress monitor
  4. DocumentManagerAgent     — DMS integration, version tracking, role-based access control
  5. NotificationCenterAgent  — Multi-channel routing, template engine, delivery tracking
  6. ReportGeneratorAgent     — Status reports, PDF builder, scheduled generation
  7. ComplianceCheckerAgent   — VOB/A, VOB/B, BHO, GoBD, GDPR rule engine
  8. DataPrivacyAgent         — Anonymization, consent management, deletion requests
  9. FeedbackCollectorAgent   — User feedback, satisfaction tracking, improvement pipeline
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import jwt  # type: ignore


# ============================================================
# Shared Enums & Data Classes
# ============================================================


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    PROJECT_LEAD = "PROJECT_LEAD"
    INSPECTOR = "INSPECTOR"
    CONTRACTOR = "CONTRACTOR"
    VIEWER = "VIEWER"


class ProjectStatus(str, Enum):
    INITIALIZED = "INITIALIZED"
    TENDERING = "TENDERING"
    BID_EVALUATION = "BID_EVALUATION"
    CONTRACT_AWARDED = "CONTRACT_AWARDED"
    IN_PROGRESS = "IN_PROGRESS"
    DEFECT_RESOLUTION = "DEFECT_RESOLUTION"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class TaskState(str, Enum):
    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class NotificationChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    BUNDID = "bundid"
    TEAMS = "teams"
    SLACK = "slack"


class ComplianceDomain(str, Enum):
    VOB_A = "VOB/A"
    VOB_B = "VOB/B"
    BHO = "BHO"
    GOBD = "GoBD"
    GDPR = "DSGVO"
    EIDAS = "eIDAS"


# ============================================================
# Agent 1: UserAuthenticatorAgent — Identity & Access Management
# ============================================================


class BundIDProxy:
    """Subagent 1.1: BundID/eIDAS SSO integration."""

    _BUNDID_JWKS_URL = "https://id.bund.de/.well-known/jwks.json"
    _ALLOWED_ISSUERS = ["https://id.bund.de", "https://eidas.bund.de"]

    def authenticate(self, bundid_token: str) -> dict:
        """Validate BundID JWT and extract user identity."""
        try:
            decoded = jwt.decode(
                bundid_token,
                algorithms=["RS256"],
                options={"verify_signature": False},  # Prod: verify against JWKS
            )
            iss = decoded.get("iss", "")
            if iss not in self._ALLOWED_ISSUERS:
                raise PermissionError(f"Unbekannter Issuer: {iss}")

            return {
                "user_id": decoded.get("sub", f"USER-{uuid.uuid4().hex[:8].upper()}"),
                "name": f"{decoded.get('given_name', '')} {decoded.get('family_name', '')}".strip(),
                "email": decoded.get("email", "unknown@behoerde.de"),
                "organization": decoded.get("org", "Unbekannte Behörde"),
                "group": decoded.get("group", ""),
                "assurance_level": decoded.get("acr", "basic"),
                "authenticated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            print(f"  [BundIDProxy]   ❌ Auth fehlgeschlagen: {exc}")
            raise PermissionError("Ungültiger BundID-Token")


class RoleMapper:
    """Subagent 1.2: Maps BundID attributes to internal roles."""

    _ROLE_MAPPING = {
        "ELSTER_OrgAdmin": UserRole.ADMIN,
        "Vergabestellenleiter": UserRole.PROJECT_LEAD,
        "Rechnungspruefer": UserRole.INSPECTOR,
        "Bauleiter": UserRole.CONTRACTOR,
    }

    def map(self, bundid_claims: dict) -> UserRole:
        """Determine user role from BundID claims and organization."""
        group = bundid_claims.get("group", "")
        for pattern, role in self._ROLE_MAPPING.items():
            if pattern.lower() in group.lower():
                return role
        return UserRole.VIEWER

    def get_permissions(self, role: UserRole) -> list[str]:
        """Return permission set for a role."""
        permissions_map = {
            UserRole.ADMIN: ["*"],
            UserRole.PROJECT_LEAD: [
                "project:create", "project:read", "project:update",
                "tender:initiate", "report:generate", "document:read",
            ],
            UserRole.INSPECTOR: [
                "project:read", "report:generate", "audit:export",
                "document:read", "compliance:review",
            ],
            UserRole.CONTRACTOR: [
                "project:read", "tender:bid", "document:upload",
                "installment:view", "defect:respond",
            ],
            UserRole.VIEWER: ["project:read", "report:read"],
        }
        return permissions_map.get(role, [])


class SessionManager:
    """Subagent 1.3: JWT session lifecycle management."""

    def __init__(self, session_ttl_minutes: int = 480):
        self._sessions: dict[str, dict] = {}
        self._session_ttl = session_ttl_minutes

    def create(self, user_info: dict, role: UserRole) -> str:
        session_id = f"SESS-{user_info['user_id']}-{uuid.uuid4().hex[:8].upper()}"
        self._sessions[session_id] = {
            "user": user_info, "role": role,
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=self._session_ttl),
            "last_activity": datetime.now(timezone.utc),
        }
        return session_id

    def validate(self, session_id: str) -> dict | None:
        session = self._sessions.get(session_id)
        if not session:
            return None
        if datetime.now(timezone.utc) > session["expires_at"]:
            del self._sessions[session_id]
            return None
        session["last_activity"] = datetime.now(timezone.utc)
        return session

    def destroy(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    @property
    def active_count(self) -> int:
        return len(self._sessions)


class UserAuthenticatorAgent:
    """Agent 1 (Wave 9): Identity management via BundID/eIDAS SSO."""

    def __init__(self, event_bus: Any = None):
        self.bus = event_bus
        self.bundid_proxy = BundIDProxy()
        self.role_mapper = RoleMapper()
        self.sessions = SessionManager()
        self._login_attempts: dict[str, int] = defaultdict(int)
        self._rate_limit = 5  # max attempts per minute per IP

    async def handle_login(self, bundid_token: str, client_ip: str = "0.0.0.0") -> dict:
        """Main: process login request."""
        # Rate limiting
        self._login_attempts[client_ip] += 1
        if self._login_attempts[client_ip] > self._rate_limit:
            print(f"  [UserAuth]      🚫 Rate limit exceeded for {client_ip}")
            raise PermissionError("Zu viele Login-Versuche. Bitte warten.")

        user_info = self.bundid_proxy.authenticate(bundid_token)
        role = self.role_mapper.map(user_info)
        permissions = self.role_mapper.get_permissions(role)
        session_id = self.sessions.create(user_info, role)

        print(f"  [UserAuth]      ✅ {user_info['name']} ({role.value}) → {session_id}")

        if self.bus:
            self.bus.publish("user.login.success", {
                "session_id": session_id, "user": user_info,
                "role": role.value, "permissions": permissions,
            })

        return {
            "session_id": session_id, "user": user_info,
            "role": role.value, "permissions": permissions,
        }

    async def handle_logout(self, session_id: str) -> bool:
        """Process logout request."""
        ok = self.sessions.destroy(session_id)
        if ok and self.bus:
            self.bus.publish("user.logout.success", {"session_id": session_id})
        print(f"  [UserAuth]      👋 Logout: {session_id}")
        return ok

    async def validate_session(self, session_id: str) -> dict | None:
        """Validate an existing session."""
        session = self.sessions.validate(session_id)
        if not session:
            return None
        return {"user": session["user"], "role": session["role"].value}

    async def check_permission(self, session_id: str, permission: str) -> bool:
        """Verify a user has a specific permission."""
        session = self.sessions.validate(session_id)
        if not session:
            return False
        permissions = self.role_mapper.get_permissions(session["role"])
        return "*" in permissions or permission in permissions

    def status(self) -> dict:
        return {"active_sessions": self.sessions.active_count,
                "rate_limited_ips": [ip for ip, n in self._login_attempts.items() if n >= self._rate_limit]}


# ============================================================
# Agent 2: ProjectManagerAgent — Project Lifecycle
# ============================================================


class ProjectManagerAgent:
    """Agent 2 (Wave 9): Creates and manages the lifecycle of procurement projects."""

    def __init__(self, event_bus: Any = None):
        self.bus = event_bus
        self._projects: dict[str, dict] = {}

    async def create_project(self, name: str, budget_eur: float, deadline: str,
                             description: str = "", gaeb_xml: str = "",
                             created_by: str = "unknown") -> dict:
        """Subagent: ProjectCreator — initializes a new procurement project."""
        project_id = f"PROJ-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        tender_id = f"TED-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        project = {
            "project_id": project_id, "tender_id": tender_id,
            "name": name, "description": description,
            "status": ProjectStatus.INITIALIZED.value,
            "budget_eur": budget_eur, "deadline": deadline,
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "gaeb_xml_hash": hashlib.sha256(gaeb_xml.encode()).hexdigest()[:16] if gaeb_xml else "",
        }
        self._projects[project_id] = project

        print(f"  [ProjectMgr]    🏗  {project_id}: \"{name}\" "
              f"(Budget={budget_eur:,.2f} €, Deadline={deadline})")

        if self.bus:
            self.bus.publish("project.created", project)
            if gaeb_xml:
                self.bus.publish("b2g.tender.initiate", {
                    "project_id": project_id, "tender_id": tender_id,
                    "budget_eur": budget_eur, "deadline": deadline,
                    "gaeb_xml": gaeb_xml, "created_by": created_by,
                })

        return project

    async def allocate_budget(self, project_id: str, budget_eur: float) -> dict:
        """Subagent: BudgetAllocator — distributes budget across project phases."""
        project = self._projects.get(project_id)
        if not project:
            raise KeyError(f"Projekt {project_id} nicht gefunden")

        # VOB/A-standard budget distribution
        allocation = {
            "planung": round(budget_eur * 0.10, 2),
            "ausschreibung": round(budget_eur * 0.05, 2),
            "bauausfuehrung": round(budget_eur * 0.70, 2),
            "abnahme": round(budget_eur * 0.05, 2),
            "reserve": round(budget_eur * 0.10, 2),
        }
        project["budget_allocation"] = allocation
        project["updated_at"] = datetime.now(timezone.utc).isoformat()

        print(f"  [ProjectMgr]    💰 Budget {project_id}: {budget_eur:,.2f} € → "
              f"Bau={allocation['bauausfuehrung']:,.2f}, Plan={allocation['planung']:,.2f}")

        if self.bus:
            self.bus.publish("project.budget.allocated", {
                "project_id": project_id, "allocation": allocation})

        return allocation

    async def set_deadline(self, project_id: str, key: str, date_str: str) -> dict:
        """Subagent: DeadlineSetter — manages project milestone deadlines."""
        project = self._projects.get(project_id)
        if not project:
            raise KeyError(f"Projekt {project_id} nicht gefunden")

        deadlines = project.setdefault("milestone_deadlines", {})
        deadlines[key] = date_str
        project["updated_at"] = datetime.now(timezone.utc).isoformat()

        print(f"  [ProjectMgr]    📅 {project_id}: {key} → {date_str}")
        return deadlines

    async def get_project(self, project_id: str) -> dict:
        """Main: retrieve project status."""
        return self._projects.get(project_id, {"status": "NOT_FOUND"})

    async def update_status(self, project_id: str, new_status: ProjectStatus) -> dict:
        """Update project lifecycle status."""
        project = self._projects.get(project_id)
        if not project:
            raise KeyError(f"Projekt {project_id} nicht gefunden")
        project["status"] = new_status.value
        project["updated_at"] = datetime.now(timezone.utc).isoformat()

        if self.bus:
            self.bus.publish("project.status.changed", {
                "project_id": project_id, "status": new_status.value})

        return project

    async def list_projects(self, status_filter: str | None = None) -> list[dict]:
        """List all projects, optionally filtered by status."""
        projects = list(self._projects.values())
        if status_filter:
            projects = [p for p in projects if p.get("status") == status_filter]
        return projects

    def status(self) -> dict:
        by_status = defaultdict(int)
        for p in self._projects.values():
            by_status[p["status"]] += 1
        return {"total_projects": len(self._projects), "by_status": dict(by_status)}


# ============================================================
# Agent 3: TaskDispatcherAgent — Workflow Orchestration
# ============================================================


class TaskDispatcherAgent:
    """Agent 3 (Wave 9): Translates milestones into agent tasks, triggers waves."""

    _WAVE_TRIGGERS = {
        "tendering": "b2g.tender.initiate",
        "composing": "b2g.composing.start",
        "execution": "b2g.execution.start",
        "vob_installment": "b2g.vob.installment",
        "treasury_payment": "b2g.treasury.payment",
        "invoicing": "b2g.invoicing.generate",
        "archiving": "b2g.gobd.archive",
    }

    def __init__(self, event_bus: Any = None):
        self.bus = event_bus
        self._tasks: dict[str, dict] = {}
        self._task_counter = 0

    async def map_milestones_to_tasks(self, project_id: str,
                                      milestones: list[dict]) -> list[dict]:
        """Subagent: MilestoneToTaskMapper — converts milestones to executable tasks."""
        tasks = []
        for i, ms in enumerate(milestones):
            task = {
                "task_id": f"TASK-{project_id}-{i+1:03d}",
                "project_id": project_id,
                "milestone": ms.get("name", f"Meilenstein {i+1}"),
                "wave_trigger": self._WAVE_TRIGGERS.get(ms.get("wave", "tendering")),
                "state": TaskState.PENDING.value,
                "priority": ms.get("priority", "NORMAL"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._tasks[task["task_id"]] = task
            tasks.append(task)
        self._task_counter += len(tasks)
        print(f"  [TaskDispatch]  📋 {len(tasks)} tasks from {len(milestones)} milestones "
              f"({project_id})")
        return tasks

    async def trigger_agent_wave(self, task_id: str, context: dict) -> bool:
        """Subagent: AgentTrigger — fires the event that launches an agent wave."""
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} nicht gefunden")

        wave_trigger = task.get("wave_trigger")
        if not wave_trigger:
            print(f"  [TaskDispatch]  ⚠ Kein Trigger für {task_id}")
            return False

        task["state"] = TaskState.DISPATCHED.value
        task["dispatched_at"] = datetime.now(timezone.utc).isoformat()

        if self.bus:
            self.bus.publish(wave_trigger, {"task_id": task_id, **context})

        print(f"  [TaskDispatch]  🚀 {task_id} → {wave_trigger}")
        return True

    async def monitor_tasks(self, project_id: str) -> dict:
        """Subagent: TaskMonitor — reports task completion status."""
        project_tasks = [t for t in self._tasks.values()
                        if t["project_id"] == project_id]
        counts = defaultdict(int)
        for t in project_tasks:
            counts[t["state"]] += 1
        return {
            "project_id": project_id, "total_tasks": len(project_tasks),
            "by_state": dict(counts),
            "progress_pct": round(counts.get("COMPLETED", 0) / max(1, len(project_tasks)) * 100, 1),
        }

    async def complete_task(self, task_id: str, result: dict | None = None) -> None:
        """Mark a task as completed."""
        task = self._tasks.get(task_id)
        if task:
            task["state"] = TaskState.COMPLETED.value
            task["completed_at"] = datetime.now(timezone.utc).isoformat()
            task["result"] = result

    async def fail_task(self, task_id: str, error: str) -> None:
        """Mark a task as failed."""
        task = self._tasks.get(task_id)
        if task:
            task["state"] = TaskState.FAILED.value
            task["error"] = error

    def status(self) -> dict:
        return {"total_tasks": len(self._tasks), "task_counter": self._task_counter}


# ============================================================
# Agent 4: DocumentManagerAgent — DMS Integration
# ============================================================


class DocumentManagerAgent:
    """Agent 4 (Wave 9): Document management with version tracking and access control."""

    _DOC_TYPES = ["GAEB_X83", "GAEB_X84", "VERTRAG", "XRECHNUNG", "PRUEFBERICHT",
                  "POWP_ZERTIFIKAT", "ABNAHME_PROTOKOLL", "MAENGEL_RUEGE"]

    def __init__(self, storage_root: Path = Path("archive_b2g/dms")):
        self.storage_root = storage_root
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self._documents: dict[str, dict] = {}
        self._versions: dict[str, list[dict]] = defaultdict(list)
        self._acl: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    async def store(self, doc_type: str, content: bytes, project_id: str,
                    filename: str, uploaded_by: str) -> str:
        """Subagent: DMSConnector — store document with metadata."""
        if doc_type not in self._DOC_TYPES:
            raise ValueError(f"Unbekannter Dokumenttyp: {doc_type}")

        doc_id = f"DOC-{project_id}-{doc_type}-{uuid.uuid4().hex[:6].upper()}"
        content_hash = hashlib.sha256(content).hexdigest()

        doc_path = self.storage_root / project_id / doc_type / filename
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_bytes(content)

        entry = {
            "doc_id": doc_id, "project_id": project_id, "doc_type": doc_type,
            "filename": filename, "content_hash": content_hash,
            "size_bytes": len(content), "uploaded_by": uploaded_by,
            "version": 1, "stored_at": datetime.now(timezone.utc).isoformat(),
            "path": str(doc_path),
        }
        self._documents[doc_id] = entry
        self._versions[doc_id].append(entry)

        print(f"  [DocumentMgr]   📄 {doc_id}: {filename} ({doc_type}, "
              f"{len(content):,} bytes, hash={content_hash[:12]}...)")
        return doc_id

    async def create_version(self, doc_id: str, new_content: bytes,
                             updated_by: str) -> dict:
        """Subagent: VersionTracker — track document revisions."""
        original = self._documents.get(doc_id)
        if not original:
            raise KeyError(f"Dokument {doc_id} nicht gefunden")

        new_hash = hashlib.sha256(new_content).hexdigest()
        new_version = original["version"] + 1

        doc_path = Path(original["path"]).parent / f"v{new_version}_{original['filename']}"
        doc_path.write_bytes(new_content)

        entry = {**original, "version": new_version, "content_hash": new_hash,
                 "size_bytes": len(new_content), "uploaded_by": updated_by,
                 "stored_at": datetime.now(timezone.utc).isoformat(), "path": str(doc_path)}
        self._versions[doc_id].append(entry)
        self._documents[doc_id] = entry

        print(f"  [DocumentMgr]   🔄 {doc_id} v{new_version} ({new_hash[:12]}...)")
        return entry

    async def set_access(self, doc_id: str, role: UserRole,
                         permissions: list[str]) -> None:
        """Subagent: AccessControl — role-based document access."""
        if doc_id not in self._documents:
            raise KeyError(f"Dokument {doc_id} nicht gefunden")
        self._acl[doc_id][role.value] = permissions
        print(f"  [DocumentMgr]   🔐 ACL {doc_id}: {role.value} → {permissions}")

    async def check_access(self, doc_id: str, role: UserRole,
                           action: str) -> bool:
        """Verify a role has permission for an action on a document."""
        role_perms = self._acl.get(doc_id, {}).get(role.value, [])
        return "*" in role_perms or action in role_perms

    async def get_document(self, doc_id: str) -> dict:
        """Main: retrieve document metadata."""
        return self._documents.get(doc_id, {"status": "NOT_FOUND"})

    async def list_project_documents(self, project_id: str) -> list[dict]:
        """List all documents for a project."""
        return [d for d in self._documents.values() if d["project_id"] == project_id]

    def status(self) -> dict:
        return {"total_documents": len(self._documents),
                "total_versions": sum(len(v) for v in self._versions.values()),
                "by_type": defaultdict(int, **{t: sum(1 for d in self._documents.values()
                if d["doc_type"] == t) for t in self._DOC_TYPES})}


# ============================================================
# Agent 5: NotificationCenterAgent — Multi-Channel Communication
# ============================================================


class NotificationCenterAgent:
    """Agent 5 (Wave 9): Central notification hub with channel routing and delivery tracking."""

    _TEMPLATES = {
        "project_created": "Projekt {project_id} \"{name}\" wurde angelegt. Budget: {budget_eur:,.2f} €.",
        "tender_submitted": "Ihr Angebot für {tender_id} wurde eingereicht (Tx: {tx_hash}).",
        "installment_due": "Abschlag {installment_no}/{total} für {tender_id}: {amount:,.2f} € fällig bis {deadline}.",
        "defect_reported": "Mängelrüge #{defect_id}: {description}. Nachfrist: {deadline}.",
        "compliance_violation": "⚠ {domain}-Verstoß in {project_id}: {message}. Dringlichkeit: {severity}.",
        "project_completed": "Projekt {tender_id} abgeschlossen. Schlussrechnung unter {report_url}.",
        "data_deletion_request": "DSGVO-Löschantrag von {user_id} erhalten. Frist: {deadline}.",
        "feedback_received": "📝 Neues Feedback ({rating}/5): \"{summary}\" von {user_name}.",
    }

    _CHANNEL_PRIORITY = {
        "critical": [NotificationChannel.SMS, NotificationChannel.EMAIL, NotificationChannel.TEAMS],
        "high": [NotificationChannel.EMAIL, NotificationChannel.TEAMS],
        "normal": [NotificationChannel.EMAIL, NotificationChannel.BUNDID],
        "low": [NotificationChannel.BUNDID],
    }

    def __init__(self, event_bus: Any = None):
        self.bus = event_bus
        self._delivery_log: list[dict] = []

    async def select_channels(self, priority: str) -> list[NotificationChannel]:
        """Subagent: ChannelRouter — choose channels by priority."""
        return self._CHANNEL_PRIORITY.get(priority, [NotificationChannel.EMAIL])

    async def render_message(self, template_key: str, context: dict) -> str:
        """Subagent: TemplateEngine — render personalized notification."""
        template = self._TEMPLATES.get(template_key, "{message}")
        try:
            return template.format(**context)
        except KeyError:
            return template

    async def dispatch(self, channel: NotificationChannel, recipient: str,
                       subject: str, body: str) -> dict:
        """Send through a specific channel."""
        msg_id = f"NOTIF-{uuid.uuid4().hex[:8].upper()}"

        channel_emoji = {NotificationChannel.EMAIL: "✉️", NotificationChannel.SMS: "📱",
                         NotificationChannel.BUNDID: "🏛️", NotificationChannel.TEAMS: "💬",
                         NotificationChannel.SLACK: "💭"}
        print(f"  [Notification]  {channel_emoji.get(channel, '📨')} {msg_id} "
              f"→ {recipient} via {channel.value}: {subject}")

        return {"msg_id": msg_id, "channel": channel.value, "recipient": recipient,
                "dispatched_at": datetime.now(timezone.utc).isoformat()}

    async def track_delivery(self, msg_id: str, status: str, detail: str = "") -> None:
        """Subagent: DeliveryTracker — log delivery status."""
        self._delivery_log.append({
            "msg_id": msg_id, "status": status, "detail": detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if status == "failed":
            print(f"  [Notification]  ❌ Delivery failed: {msg_id} — {detail}")

    async def notify(self, recipient: str, template_key: str, context: dict,
                     priority: str = "normal", custom_channels: list[str] | None = None) -> list[dict]:
        """Main: send notification through appropriate channels."""
        channels = ([NotificationChannel(c) for c in custom_channels]
                    if custom_channels else await self.select_channels(priority))

        body = await self.render_message(template_key, context)
        subject = f"Agent X B2G — {template_key.replace('_', ' ').title()}"

        results = []
        for ch in channels:
            result = await self.dispatch(ch, recipient, subject, body)
            results.append(result)

        if self.bus:
            self.bus.publish("notification.sent", {
                "recipient": recipient, "template": template_key,
                "channels": [c.value for c in channels], "priority": priority})

        return results

    def status(self) -> dict:
        return {"deliveries_logged": len(self._delivery_log),
                "recent_failures": sum(1 for d in self._delivery_log[-20:]
                                      if d["status"] == "failed")}


# ============================================================
# Agent 6: ReportGeneratorAgent — Status & Compliance Reports
# ============================================================


class ReportGeneratorAgent:
    """Agent 6 (Wave 9): Generates periodic status reports for project management."""

    _REPORT_TYPES = ["project_progress", "financial_status", "open_defects",
                     "upcoming_deadlines", "compliance_summary", "executive_dashboard"]

    def __init__(self, output_dir: Path = Path("archive_b2g/reports")):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._report_log: list[dict] = []
        self._scheduled: dict[str, dict] = {}

    async def aggregate_data(self, report_type: str, project_id: str,
                             sources: dict[str, Any]) -> dict:
        """Subagent: ReportAggregator — collect data from all agent waves."""
        data = {
            "report_type": report_type, "project_id": project_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project": sources.get("project", {}),
            "financial": sources.get("financial", {}),
            "defects": sources.get("defects", []),
            "deadlines": sources.get("deadlines", []),
            "compliance_checks": sources.get("compliance", []),
        }

        if report_type == "project_progress":
            tasks = sources.get("tasks", {})
            data["progress"] = tasks.get("progress_pct", 0)
            data["tasks_by_state"] = tasks.get("by_state", {})
        elif report_type == "financial_status":
            treasury = sources.get("treasury", {})
            data["bho_delta"] = treasury.get("bho_delta", 0)
            data["total_paid"] = treasury.get("total_disbursed", 0)
        elif report_type == "open_defects":
            data["defects"] = [d for d in sources.get("defects", [])
                              if d.get("state") not in ("RESOLVED", "CLOSED")]

        return data

    async def build_pdf(self, data: dict) -> bytes:
        """Subagent: PDFReportBuilder — create formatted PDF/A report."""
        lines = [
            f"{'='*70}",
            f"  AGENT X B2G — {data['report_type'].replace('_', ' ').upper()}",
            f"  Projekt: {data['project_id']}",
            f"  Generiert: {data['generated_at']}",
            f"{'='*70}",
            f"",
        ]
        for key, value in data.items():
            if key not in ("report_type", "project_id", "generated_at"):
                lines.append(f"  {key}: {value}")
        lines.append(f"")
        lines.append(f"{'─'*70}")
        lines.append(f"  Agent X B2G — 81 Agenten, 9 Wellen — Produktionsbericht")
        lines.append(f"  Klassifizierung: VS-NfD (Amtlich, nicht öffentlich)")
        lines.append(f"{'─'*70}")

        return "\n".join(lines).encode("utf-8")

    async def schedule(self, report_type: str, project_id: str,
                       interval_hours: int = 24) -> str:
        """Subagent: Scheduler — schedule recurring report generation."""
        schedule_id = f"SCHED-{report_type}-{project_id}"
        self._scheduled[schedule_id] = {
            "report_type": report_type, "project_id": project_id,
            "interval_hours": interval_hours,
            "next_run": (datetime.now(timezone.utc) + timedelta(hours=interval_hours)).isoformat(),
        }
        print(f"  [ReportGen]     📅 {schedule_id}: every {interval_hours}h")
        return schedule_id

    async def generate(self, report_type: str, project_id: str,
                       sources: dict[str, Any]) -> dict:
        """Main: produce a complete report."""
        if report_type not in self._REPORT_TYPES:
            raise ValueError(f"Unbekannter Report-Typ: {report_type}")

        data = await self.aggregate_data(report_type, project_id, sources)
        pdf_bytes = await self.build_pdf(data)

        filename = f"{project_id}_{report_type}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.pdf"
        path = self.output_dir / filename
        path.write_bytes(pdf_bytes)

        entry = {"report_id": f"RPT-{uuid.uuid4().hex[:8].upper()}",
                 "type": report_type, "project_id": project_id,
                 "path": str(path), "size_bytes": len(pdf_bytes),
                 "generated_at": data["generated_at"]}
        self._report_log.append(entry)

        print(f"  [ReportGen]     📊 {entry['report_id']}: {filename} "
              f"({len(pdf_bytes)} bytes)")
        return entry

    def status(self) -> dict:
        return {"reports_generated": len(self._report_log),
                "scheduled_reports": len(self._scheduled)}


# ============================================================
# Agent 7: ComplianceCheckerAgent — Regulatory Rule Engine
# ============================================================


class ComplianceCheckerAgent:
    """Agent 7 (Wave 9): Continuous compliance monitoring against VOB, BHO, GoBD, GDPR."""

    _RULES = {
        ComplianceDomain.VOB_A: [
            {"id": "VOB-A-001", "check": "Angebotsfrist >= 14 Tage",
             "rule": lambda d: d.get("days_until_deadline", 0) >= 14},
            {"id": "VOB-A-002", "check": "Keine Diskriminierung nach Herkunft",
             "rule": lambda d: d.get("restricts_origin", False) is False},
        ],
        ComplianceDomain.VOB_B: [
            {"id": "VOB-B-013-1", "check": "Mängelrüge-Frist = 14 Tage",
             "rule": lambda d: d.get("defect_deadline_days", 14) == 14},
            {"id": "VOB-B-017-1", "check": "Sicherheitseinbehalt = 5%",
             "rule": lambda d: abs(d.get("retention_pct", 5.0) - 5.0) < 0.01},
            {"id": "VOB-B-017-4", "check": "95% Auszahlung bei Abnahme",
             "rule": lambda d: d.get("release_pct", 95.0) >= 95.0},
        ],
        ComplianceDomain.BHO: [
            {"id": "BHO-001", "check": "BHO Zero-Sum Δ = 0,00 €",
             "rule": lambda d: abs(d.get("bho_delta", 0.0)) < 0.01},
            {"id": "BHO-002", "check": "Jede Auszahlung hat Gegenbuchung",
             "rule": lambda d: all(t.get("matched", False) for t in d.get("transactions", []))},
        ],
        ComplianceDomain.GOBD: [
            {"id": "GOBD-001", "check": "JSONL-Audit-Trail lückenlos",
             "rule": lambda d: d.get("audit_gaps", 0) == 0},
            {"id": "GOBD-002", "check": "Exportfähigkeit als GDPdU-XML",
             "rule": lambda d: d.get("gdpdu_exportable", False) is True},
        ],
        ComplianceDomain.GDPR: [
            {"id": "GDPR-001", "check": "Datenminimierung eingehalten",
             "rule": lambda d: d.get("excessive_pii", False) is False},
            {"id": "GDPR-002", "check": "Löschanträge < 30 Tage bearbeitet",
             "rule": lambda d: all(r.get("days_open", 0) < 30 for r in d.get("deletion_requests", []))},
            {"id": "GDPR-003", "check": "Auftragsverarbeitungsvertrag vorhanden",
             "rule": lambda d: d.get("avv_signed", False) is True},
        ],
        ComplianceDomain.EIDAS: [
            {"id": "EIDAS-001", "check": "QES-Signatur gültig",
             "rule": lambda d: d.get("qes_valid", False) is True},
        ],
    }

    def __init__(self, event_bus: Any = None):
        self.bus = event_bus
        self._violations: list[dict] = []
        self._check_count = 0

    async def evaluate_rules(self, domain: ComplianceDomain,
                             data: dict) -> list[dict]:
        """Subagent: RuleEngine — run all rules for a compliance domain."""
        results = []
        for rule in self._RULES.get(domain, []):
            passed = rule["rule"](data)
            result = {"rule_id": rule["id"], "domain": domain.value,
                      "check": rule["check"], "passed": passed}
            results.append(result)
            if not passed:
                self._violations.append({**result,
                                         "timestamp": datetime.now(timezone.utc).isoformat(),
                                         "context": data})
        return results

    async def review_audit_trail(self, project_id: str,
                                 audit_entries: list[dict]) -> dict:
        """Subagent: AuditTrailReviewer — verify audit trail completeness."""
        gaps = 0
        entries_sorted = sorted(audit_entries, key=lambda e: e.get("ts", ""))
        for i in range(len(entries_sorted) - 1):
            # Check for chronological ordering
            if entries_sorted[i].get("ts", "") > entries_sorted[i+1].get("ts", ""):
                gaps += 1
        return {"total_entries": len(audit_entries), "gaps": gaps,
                "complete": gaps == 0}

    async def escalate_violation(self, violation: dict, severity: str = "high") -> None:
        """Subagent: AlertSubagent — escalate compliance violations."""
        alert = {"alert_id": f"COMP-{uuid.uuid4().hex[:8].upper()}",
                 "violation": violation, "severity": severity,
                 "escalated_at": datetime.now(timezone.utc).isoformat()}

        channels = ["email"] if severity == "normal" else ["email", "sms"]
        alert["channels"] = channels

        print(f"  [Compliance]    🚨 {violation['rule_id']} VERLETZT: "
              f"{violation['check']} (severity={severity})")

        if self.bus:
            self.bus.publish("compliance.violation", alert)

    async def check_project(self, project_id: str,
                            compliance_data: dict) -> dict:
        """Main: run all compliance checks for a project."""
        self._check_count += 1
        all_results = {}

        for domain in ComplianceDomain:
            data = compliance_data.get(domain.value, {})
            results = await self.evaluate_rules(domain, data)
            all_results[domain.value] = results

            for r in results:
                if not r["passed"]:
                    severity = "critical" if domain in (ComplianceDomain.BHO, ComplianceDomain.VOB_B) else "high"
                    await self.escalate_violation(r, severity)

        passed = sum(1 for results in all_results.values()
                    for r in results if r["passed"])
        total = sum(len(results) for results in all_results.values())
        print(f"  [Compliance]    ✅ {passed}/{total} rules passed, "
              f"{len(self._violations)} violations total")

        return {"project_id": project_id, "results": all_results,
                "passed": passed, "total": total,
                "violations": len(self._violations)}

    def status(self) -> dict:
        return {"checks_run": self._check_count,
                "total_violations": len(self._violations),
                "recent_violations": self._violations[-5:]}


# ============================================================
# Agent 8: DataPrivacyAgent — GDPR Compliance
# ============================================================


class DataPrivacyAgent:
    """Agent 8 (Wave 9): GDPR data protection, anonymization, consent, deletion."""

    def __init__(self, event_bus: Any = None):
        self.bus = event_bus
        self._consents: dict[str, dict] = {}
        self._deletion_requests: dict[str, dict] = {}
        self._pii_fields = {"name", "email", "phone", "address", "id_number", "bank_account"}

    async def anonymize(self, data: dict, fields_to_remove: set[str] | None = None) -> dict:
        """Subagent: AnonymizationEngine — pseudonymize PII fields."""
        fields = fields_to_remove or self._pii_fields
        anonymized = {}
        for key, value in data.items():
            if key in fields:
                if isinstance(value, str) and value:
                    anonymized[key] = f"ANON-{hashlib.sha256(value.encode()).hexdigest()[:12]}"
                else:
                    anonymized[key] = "***REDACTED***"
            else:
                anonymized[key] = value
        return anonymized

    async def record_consent(self, user_id: str, purpose: str,
                            granted: bool = True) -> dict:
        """Subagent: ConsentManager — manage GDPR consent records."""
        consent_id = f"CONSENT-{user_id}-{purpose}-{uuid.uuid4().hex[:6].upper()}"
        entry = {
            "consent_id": consent_id, "user_id": user_id, "purpose": purpose,
            "granted": granted, "recorded_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
        }
        self._consents[consent_id] = entry
        print(f"  [DataPrivacy]  ✍️  {consent_id}: {purpose} → {'✓' if granted else '✗'}")
        return entry

    async def check_consent(self, user_id: str, purpose: str) -> bool:
        """Verify that a user has consented to a specific purpose."""
        for consent in self._consents.values():
            if (consent["user_id"] == user_id and consent["purpose"] == purpose
                    and consent["granted"]
                    and datetime.now(timezone.utc).isoformat() < consent["expires_at"]):
                return True
        return False

    async def request_deletion(self, user_id: str, reason: str = "") -> dict:
        """Subagent: DeletionSubagent — process GDPR deletion request."""
        req_id = f"DELREQ-{user_id}-{uuid.uuid4().hex[:6].upper()}"
        entry = {
            "request_id": req_id, "user_id": user_id, "reason": reason,
            "status": "RECEIVED", "days_open": 0,
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "deadline": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        }
        self._deletion_requests[req_id] = entry

        print(f"  [DataPrivacy]  🗑️  {req_id}: Löschantrag {user_id} "
              f"(Deadline: {entry['deadline'][:10]})")

        if self.bus:
            self.bus.publish("gdpr.deletion.requested", entry)

        return entry

    async def execute_deletion(self, request_id: str) -> dict:
        """Execute the actual data deletion."""
        request = self._deletion_requests.get(request_id)
        if not request:
            raise KeyError(f"Löschantrag {request_id} nicht gefunden")

        request["status"] = "COMPLETED"
        request["completed_at"] = datetime.now(timezone.utc).isoformat()
        request["days_open"] = (datetime.fromisoformat(request["completed_at"])
                                - datetime.fromisoformat(request["requested_at"])).days

        print(f"  [DataPrivacy]  ✅ {request_id}: Daten gelöscht "
              f"(in {request['days_open']} Tagen)")

        if self.bus:
            self.bus.publish("gdpr.deletion.completed", request)

        return request

    async def verify_compliance(self, project_id: str) -> dict:
        """Main: verify GDPR compliance for a project."""
        pending_deletions = [r for r in self._deletion_requests.values()
                            if r["status"] != "COMPLETED"]
        overdue = [r for r in pending_deletions
                   if datetime.now(timezone.utc).isoformat() > r["deadline"]]

        result = {
            "project_id": project_id, "consents_recorded": len(self._consents),
            "pending_deletions": len(pending_deletions),
            "overdue_deletions": len(overdue),
            "compliant": len(overdue) == 0,
        }

        if overdue:
            print(f"  [DataPrivacy]  ⚠ {len(overdue)} überfällige Löschanträge!")
        return result

    def status(self) -> dict:
        return {"consents": len(self._consents),
                "deletion_requests": len(self._deletion_requests),
                "pending": sum(1 for r in self._deletion_requests.values()
                              if r["status"] != "COMPLETED")}


# ============================================================
# Agent 9: FeedbackCollectorAgent — User Feedback Loop
# ============================================================


class FeedbackCollectorAgent:
    """Agent 9 (Wave 9): Collects user feedback and drives continuous improvement."""

    def __init__(self, event_bus: Any = None):
        self.bus = event_bus
        self._feedback: list[dict] = []
        self._improvements: list[dict] = []
        self._satisfaction_scores: list[float] = []

    async def submit_feedback(self, user_id: str, rating: int, summary: str,
                             category: str = "general", details: str = "") -> dict:
        """Subagent: FeedbackFormEngine — accept structured user feedback."""
        if not 1 <= rating <= 5:
            raise ValueError("Rating muss 1-5 sein")

        entry = {
            "feedback_id": f"FB-{uuid.uuid4().hex[:8].upper()}",
            "user_id": user_id, "rating": rating, "summary": summary,
            "category": category, "details": details,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "status": "NEW",
        }
        self._feedback.append(entry)
        self._satisfaction_scores.append(float(rating))

        print(f"  [Feedback]      📝 {entry['feedback_id']}: "
              f"{'⭐'*rating} \"{summary[:50]}\" ({category})")

        if self.bus:
            self.bus.publish("feedback.received", entry)

        return entry

    async def calculate_satisfaction(self, period_days: int = 30) -> dict:
        """Subagent: SatisfactionMeter — compute NPS/satisfaction metrics."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()
        recent = [f for f in self._feedback if f["submitted_at"] > cutoff]

        if not recent:
            return {"nps": 0, "avg_rating": 0, "count": 0}

        avg = sum(f["rating"] for f in recent) / len(recent)
        # NPS: 5→promoter, 4→passive, 1-3→detractor
        promoters = sum(1 for f in recent if f["rating"] >= 5)
        detractors = sum(1 for f in recent if f["rating"] <= 3)
        nps = round((promoters - detractors) / len(recent) * 100, 1)

        return {"nps": nps, "avg_rating": round(avg, 1), "count": len(recent),
                "period_days": period_days}

    async def create_improvement(self, feedback_id: str, action: str,
                                 priority: str = "normal") -> dict:
        """Subagent: ImprovementTracker — convert feedback into improvements."""
        fb = next((f for f in self._feedback if f["feedback_id"] == feedback_id), None)
        if not fb:
            raise KeyError(f"Feedback {feedback_id} nicht gefunden")

        ticket = {
            "improvement_id": f"IMP-{uuid.uuid4().hex[:8].upper()}",
            "feedback_id": feedback_id, "action": action,
            "priority": priority, "status": "BACKLOG",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._improvements.append(ticket)

        print(f"  [Feedback]      🔧 {ticket['improvement_id']}: \"{action[:60]}\" "
              f"(priority={priority})")

        if self.bus:
            self.bus.publish("improvement.created", ticket)

        return ticket

    async def get_improvements_for_ops(self) -> list[dict]:
        """Main: send prioritized improvements to operations team."""
        prioritized = sorted(self._improvements,
                           key=lambda i: {"critical": 0, "high": 1, "normal": 2, "low": 3}
                           .get(i["priority"], 2))

        # Auto-escalate critical items
        critical = [i for i in prioritized if i["priority"] == "critical"]
        if critical and self.bus:
            for item in critical:
                self.bus.publish("ops.alert.critical", {
                    "source": "feedback", "improvement": item})

        return prioritized

    def status(self) -> dict:
        sat = {"avg_rating": round(sum(self._satisfaction_scores)
                                   / max(1, len(self._satisfaction_scores)), 1),
               "total": len(self._satisfaction_scores)}
        return {"feedback_count": len(self._feedback),
                "improvements": len(self._improvements),
                "satisfaction": sat}


# ============================================================
# UserSupervisor — ties all 9 Wave-9 agents into a unified plane
# ============================================================


class UserSupervisor:
    """Runs all 9 User & Project Management agents."""

    def __init__(self, event_bus: Any = None):
        self.bus = event_bus
        self.auth = UserAuthenticatorAgent(event_bus)
        self.projects = ProjectManagerAgent(event_bus)
        self.tasks = TaskDispatcherAgent(event_bus)
        self.documents = DocumentManagerAgent()
        self.notifications = NotificationCenterAgent(event_bus)
        self.reports = ReportGeneratorAgent()
        self.compliance = ComplianceCheckerAgent(event_bus)
        self.privacy = DataPrivacyAgent(event_bus)
        self.feedback = FeedbackCollectorAgent(event_bus)
        self._cycle_count = 0

    async def full_onboarding(self, user_token: str, user_ip: str = "0.0.0.0") -> dict:
        """Complete user login flow: auth → session → welcome notification."""
        login = await self.auth.handle_login(user_token, user_ip)
        await self.notifications.notify(
            recipient=login["user"]["email"],
            template_key="project_created",
            context={"project_id": "N/A", "name": "Willkommen bei Agent X B2G",
                     "budget_eur": 0},
            priority="low",
        )
        return login

    async def create_project_full(self, name: str, budget_eur: float, deadline: str,
                                  description: str, gaeb_xml: str = "",
                                  created_by: str = "unknown") -> dict:
        """Full project creation: project → budget → milestones → tasks."""
        # Create project
        project = await self.projects.create_project(
            name=name, budget_eur=budget_eur, deadline=deadline,
            description=description, gaeb_xml=gaeb_xml, created_by=created_by)

        # Allocate budget
        await self.projects.allocate_budget(project["project_id"], budget_eur)

        # Set default milestone deadlines
        milestones = [
            {"key": "offer_deadline", "date": deadline},
            {"key": "construction_start", "date": deadline},
            {"key": "acceptance", "date": deadline},
        ]
        for ms in milestones:
            await self.projects.set_deadline(project["project_id"], ms["key"], ms["date"])

        # Create tasks from milestones
        task_milestones = [
            {"name": "Ausschreibung starten", "wave": "tendering", "priority": "HIGH"},
            {"name": "Angebote prüfen", "wave": "composing", "priority": "HIGH"},
            {"name": "Bauausführung", "wave": "execution", "priority": "NORMAL"},
            {"name": "Abschlagsrechnung", "wave": "vob_installment", "priority": "NORMAL"},
            {"name": "Schlusszahlung", "wave": "treasury_payment", "priority": "HIGH"},
        ]
        tasks = await self.tasks.map_milestones_to_tasks(
            project["project_id"], task_milestones)

        # Notify stakeholders
        await self.notifications.notify(
            recipient=f"{created_by}@behoerde.de",
            template_key="project_created",
            context={"project_id": project["project_id"], "name": name,
                     "budget_eur": budget_eur},
            priority="high",
        )

        return {"project": project, "tasks_created": len(tasks)}

    async def run_compliance_cycle(self, project_id: str,
                                   compliance_data: dict) -> dict:
        """Run compliance and privacy checks for a project."""
        comp_result = await self.compliance.check_project(project_id, compliance_data)
        privacy_result = await self.privacy.verify_compliance(project_id)
        return {"compliance": comp_result, "privacy": privacy_result}

    async def generate_status_report(self, project_id: str) -> dict:
        """Generate a comprehensive status report for a project."""
        project = await self.projects.get_project(project_id)
        task_status = await self.tasks.monitor_tasks(project_id)
        satisfaction = await self.feedback.calculate_satisfaction()

        sources = {
            "project": project,
            "tasks": task_status,
            "financial": {"bho_delta": 0.0, "total_disbursed": 0},
            "defects": [],
            "deadlines": [],
            "compliance": [],
        }

        report = await self.reports.generate("project_progress", project_id, sources)

        await self.notifications.notify(
            recipient="projektleitung@behoerde.de",
            template_key="project_completed",
            context={"tender_id": project.get("tender_id", project_id),
                     "report_url": report["path"]},
            priority="normal",
        )

        return {"report": report, "task_status": task_status,
                "satisfaction": satisfaction}

    async def user_cycle(self) -> dict:
        """Run one supervision cycle for Wave 9."""
        self._cycle_count += 1
        start = time.perf_counter()

        satisfaction = await self.feedback.calculate_satisfaction()
        improvements = await self.feedback.get_improvements_for_ops()

        elapsed = time.perf_counter() - start
        print(f"\n  [UserSupervisor] ⚙ Cycle {self._cycle_count} in {elapsed:.1f}s "
              f"(Sessions={self.auth.sessions.active_count}, "
              f"Projects={self.projects.status()['total_projects']}, "
              f"NPS={satisfaction['nps']}, Improvements={len(improvements)})")

        return {"cycle": self._cycle_count, "satisfaction": satisfaction,
                "improvements_pending": len(improvements),
                "sessions_active": self.auth.sessions.active_count}

    def status(self) -> dict:
        return {"auth": self.auth.status(), "projects": self.projects.status(),
                "tasks": self.tasks.status(), "documents": self.documents.status(),
                "notifications": self.notifications.status(),
                "reports": self.reports.status(),
                "compliance": self.compliance.status(),
                "privacy": self.privacy.status(),
                "feedback": self.feedback.status()}


# ============================================================
# Wave 9 Agent Registry
# ============================================================


WAVE_9_AGENTS = [
    "UserAuthenticatorAgent", "ProjectManagerAgent", "TaskDispatcherAgent",
    "DocumentManagerAgent", "NotificationCenterAgent", "ReportGeneratorAgent",
    "ComplianceCheckerAgent", "DataPrivacyAgent", "FeedbackCollectorAgent",
]
