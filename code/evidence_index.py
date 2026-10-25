import csv
import json
import os
import re
import sqlite3
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
try:
    import pymupdf as fitz  # type: ignore
except ImportError:
    try:
        import fitz  # type: ignore
    except ImportError:
        fitz = None

@dataclass
class ObservedResource:
    system_id: str
    resource_id: str
    evidence_id: str
    captured_at: str
    user_id: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    email_hash: Optional[str] = None
    is_present: bool = False
    is_active: bool = False
    is_redacted: bool = False
    is_anonymized: bool = False
    is_blocked: bool = False
    is_disabled: bool = False
    source_resource_id: Optional[str] = None
    retention_until: Optional[str] = None
    details: Optional[str] = None

class EvidenceIndex:
    def __init__(self, dataset_dir: str = "dataset"):
        self.dataset_dir = dataset_dir
        self.manifest: Dict[str, Dict[str, str]] = {}
        self.activities: List[Dict[str, str]] = []
        self.observations_by_file: Dict[str, List[ObservedResource]] = {}
        
        self._load_manifest()
        self._load_system_activity()
        self._parse_all_evidence()

    def _load_manifest(self):
        mpath = os.path.join(self.dataset_dir, "evidence_files.csv")
        with open(mpath, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                self.manifest[row["file_id"]] = row

    def _load_system_activity(self):
        apath = os.path.join(self.dataset_dir, "system_activity.csv")
        with open(apath, "r", encoding="utf-8") as f:
            self.activities = list(csv.DictReader(f))

    def _parse_all_evidence(self):
        for fid, meta in self.manifest.items():
            fpath = os.path.join(self.dataset_dir, meta["file_path"])
            if not os.path.exists(fpath):
                continue
            
            captured_at = meta["captured_at"]
            items: List[ObservedResource] = []
            
            ext = fpath.split(".")[-1].lower()
            if ext == "json":
                items = self._parse_json_file(fid, fpath, captured_at)
            elif ext == "sql":
                items = self._parse_sql_file(fid, fpath, captured_at)
            elif ext == "log":
                items = self._parse_log_file(fid, fpath, captured_at)
            elif ext == "txt":
                items = self._parse_txt_file(fid, fpath, captured_at)
            elif ext == "pdf":
                items = self._parse_pdf_file(fid, fpath, captured_at)
                
            self.observations_by_file[fid] = items

    def _parse_json_file(self, fid: str, path: str, captured_at: str) -> List[ObservedResource]:
        res = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return res

        # Case 1: service_resource_export (e.g. evidence_92)
        if isinstance(data, dict) and "service_exports" in data:
            sexports = data["service_exports"]
            for sys_name, sdata in sexports.items():
                if sys_name == "account_service":
                    for item in sdata.get("profile_lookups", []):
                        rid = item.get("resource_id")
                        prof = item.get("profile") or {}
                        is_pres = (item.get("status_code") != 404 and bool(prof))
                        res.append(ObservedResource(
                            system_id="account_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=prof.get("customer_reference"),
                            email=prof.get("email"),
                            phone=prof.get("phone"),
                            name=prof.get("full_name"),
                            is_present=is_pres
                        ))
                elif sys_name == "search_service":
                    for item in sdata.get("index_queries", []):
                        rid = item.get("resource_id")
                        hits = item.get("hits", {})
                        docs = hits.get("documents", [])
                        total = hits.get("total", 0)
                        for d in docs:
                            res.append(ObservedResource(
                                system_id="search_service",
                                resource_id=rid,
                                evidence_id=fid,
                                captured_at=captured_at,
                                user_id=d.get("customer_reference"),
                                email=d.get("email") or item.get("query"),
                                phone=d.get("phone"),
                                is_present=(total > 0)
                            ))
                elif sys_name == "analytics_platform":
                    for item in sdata.get("profiles", []):
                        rid = item.get("resource_id")
                        em = item.get("email")
                        uid = item.get("customer_reference")
                        has_pii = bool(em or uid or item.get("phone") or item.get("email_hash"))
                        res.append(ObservedResource(
                            system_id="analytics_platform",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=uid,
                            email=em,
                            phone=item.get("phone"),
                            email_hash=item.get("email_hash"),
                            is_present=True,
                            is_anonymized=(not has_pii)
                        ))
                elif sys_name == "support_platform":
                    for item in sdata.get("tickets", []):
                        rid = item.get("resource_id")
                        em = item.get("requester_email")
                        uid = item.get("customer_reference")
                        has_pii = bool(em or item.get("requester_name") or item.get("requester_phone"))
                        res.append(ObservedResource(
                            system_id="support_platform",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=uid,
                            email=em,
                            phone=item.get("requester_phone"),
                            name=item.get("requester_name"),
                            is_present=True,
                            is_redacted=(not has_pii)
                        ))
                elif sys_name == "integration_service":
                    for item in sdata.get("connectors", []):
                        rid = item.get("resource_id")
                        en = item.get("enabled", False)
                        res.append(ObservedResource(
                            system_id="integration_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=item.get("customer_reference"),
                            email=item.get("customer_email"),
                            is_present=True,
                            is_active=en,
                            is_disabled=(not en)
                        ))
                elif sys_name == "backup_service":
                    for item in sdata.get("restore_entries", []):
                        rid = item.get("resource_id")
                        ra = item.get("restore_allowed", False)
                        res.append(ObservedResource(
                            system_id="backup_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=item.get("customer_reference"),
                            email=item.get("customer_email"),
                            is_present=True,
                            is_active=ra,
                            is_blocked=(not ra)
                        ))
                elif sys_name == "export_service":
                    for item in sdata.get("exports", []):
                        rid = item.get("resource_id")
                        res.append(ObservedResource(
                            system_id="export_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=item.get("customer_reference"),
                            email=item.get("owner_email"),
                            phone=item.get("owner_phone"),
                            is_present=True
                        ))
                elif sys_name == "security_service":
                    for item in sdata.get("audit_records", []):
                        rid = item.get("resource_id")
                        res.append(ObservedResource(
                            system_id="security_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=item.get("subject_reference"),
                            is_present=True,
                            retention_until=item.get("retention_until")
                        ))

        # Case 2: customer_data_snapshot_bundle (e.g. evidence_51)
        elif isinstance(data, dict) and "snapshots" in data:
            for snap in data["snapshots"]:
                snap_cap = snap.get("captured_at") or captured_at
                coll = snap.get("collection", "")
                data_store = snap.get("data_store", "")
                records = snap.get("records", [])
                
                if coll == "customer_profiles" or data_store == "account_service":
                    for rec in records:
                        res.append(ObservedResource(
                            system_id="account_service",
                            resource_id=rec.get("resource_id"),
                            evidence_id=fid,
                            captured_at=snap_cap,
                            user_id=rec.get("customer_reference") or rec.get("user_id"),
                            email=rec.get("email"),
                            phone=rec.get("phone"),
                            name=rec.get("name") or rec.get("full_name"),
                            is_present=True
                        ))
                elif coll == "customer_analytics_reports" or data_store == "analytics_platform":
                    for rec in records:
                        rid = rec.get("resource_id")
                        uid = rec.get("user_id") or rec.get("customer_reference")
                        em = rec.get("email")
                        ph = rec.get("phone")
                        eh = rec.get("email_hash")
                        has_pii = bool(em or uid or ph or eh)
                        res.append(ObservedResource(
                            system_id="analytics_platform",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=snap_cap,
                            user_id=uid,
                            email=em,
                            phone=ph,
                            email_hash=eh,
                            is_present=True,
                            is_anonymized=(not has_pii)
                        ))
                elif coll == "backup_catalog" or data_store in ["backup_service", "backup_restore_service"]:
                    for rec in records:
                        rid = rec.get("resource_id")
                        sub = rec.get("subject_reference") or rec.get("customer_reference")
                        ra = rec.get("restore_allowed", False)
                        em = sub if (sub and "@" in sub) else None
                        uid = sub if (sub and sub.startswith("user_")) else None
                        res.append(ObservedResource(
                            system_id="backup_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=snap_cap,
                            user_id=uid,
                            email=em,
                            is_present=True,
                            is_active=ra,
                            is_blocked=(not ra)
                        ))
                elif coll == "customer_export_jobs" or data_store == "export_service":
                    for rec in records:
                        rid = rec.get("resource_id")
                        res.append(ObservedResource(
                            system_id="export_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=snap_cap,
                            user_id=rec.get("customer_reference"),
                            email=rec.get("owner_email"),
                            phone=rec.get("owner_phone"),
                            is_present=rec.get("download_available", True)
                        ))
                elif coll == "connector_configurations" or data_store == "integration_service":
                    for rec in records:
                        rid = rec.get("resource_id")
                        sub = rec.get("subject_selector") or rec.get("customer_reference")
                        en = rec.get("enabled", False)
                        em = sub if (sub and "@" in sub) else None
                        uid = sub if (sub and sub.startswith("user_")) else None
                        res.append(ObservedResource(
                            system_id="integration_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=snap_cap,
                            user_id=uid,
                            email=em,
                            is_present=True,
                            is_active=en,
                            is_disabled=(not en)
                        ))
                elif coll == "customer_search_documents" or data_store == "search_service":
                    for rec in records:
                        rid = rec.get("resource_id")
                        doc = rec.get("document", {})
                        res.append(ObservedResource(
                            system_id="search_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=snap_cap,
                            user_id=doc.get("customer_reference"),
                            email=doc.get("email"),
                            name=doc.get("display_name"),
                            is_present=True
                        ))
                elif coll == "ticket_attachments":
                    for rec in records:
                        rid = rec.get("resource_id")
                        res.append(ObservedResource(
                            system_id="support_platform",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=snap_cap,
                            email=rec.get("uploaded_by"),
                            details="ATTACHMENT",
                            is_present=True
                        ))
                elif coll == "support_conversations":
                    for rec in records:
                        rid = rec.get("resource_id")
                        sub = rec.get("subject_reference")
                        msg = rec.get("message_text", "")
                        
                        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', msg)
                        phone_match = re.search(r'\+[\d\s\(\)-]{8,20}', msg)
                        msg_email = email_match.group(0).lower() if email_match else None
                        msg_phone = phone_match.group(0).strip() if phone_match else None
                        
                        has_exposed_pii = bool(msg_email or msg_phone)
                        is_red = ("[REDACTED]" in msg) and (not has_exposed_pii)
                        
                        res.append(ObservedResource(
                            system_id="support_platform",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=snap_cap,
                            user_id=sub if (sub and sub.startswith("user_")) else None,
                            email=msg_email or (sub if (sub and "@" in sub) else None),
                            phone=msg_phone,
                            details=msg,
                            is_present=True,
                            is_redacted=is_red
                        ))
                elif coll == "deleted_customer_references" or data_store == "identity_service":
                    for rec in records:
                        rid = rec.get("resource_id")
                        uid = rec.get("subject_reference") or rec.get("user_id")
                        has_pii = bool(rec.get("name") or rec.get("email") or rec.get("phone") or rec.get("email_hash"))
                        res.append(ObservedResource(
                            system_id="identity_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=snap_cap,
                            user_id=uid,
                            email=rec.get("email"),
                            phone=rec.get("phone"),
                            name=rec.get("name"),
                            email_hash=rec.get("email_hash"),
                            is_present=True,
                            is_redacted=(not has_pii)
                        ))
                elif coll == "security_audit_events" or data_store == "security_service":
                    for rec in records:
                        rid = rec.get("resource_id")
                        res.append(ObservedResource(
                            system_id="security_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=snap_cap,
                            user_id=rec.get("subject_reference") or rec.get("user_id"),
                            is_present=True,
                            retention_until=rec.get("retention_until")
                        ))

        # Case 3: customer_analytics_report (e.g. evidence_56)
        elif isinstance(data, dict) and "records" in data and "analytics" in path:
            for rec in data["records"]:
                rid = rec.get("resource_id")
                uid = rec.get("user_id")
                em = rec.get("email")
                has_pii = bool(em or uid or rec.get("phone") or rec.get("email_hash"))
                res.append(ObservedResource(
                    system_id="analytics_platform",
                    resource_id=rid,
                    evidence_id=fid,
                    captured_at=captured_at,
                    user_id=uid,
                    email=em,
                    phone=rec.get("phone"),
                    email_hash=rec.get("email_hash"),
                    is_present=True,
                    is_anonymized=(not has_pii)
                ))

        # Case 4: customer_export_jobs (e.g. evidence_59)
        elif isinstance(data, dict) and ("export_jobs" in data or data.get("collection") == "customer_export_jobs" or "export_jobs" in path):
            job_list = data.get("records") or data.get("export_jobs", [])
            for job in job_list:
                res.append(ObservedResource(
                    system_id="export_service",
                    resource_id=job.get("resource_id"),
                    evidence_id=fid,
                    captured_at=captured_at,
                    user_id=job.get("customer_reference"),
                    email=job.get("owner_email"),
                    phone=job.get("owner_phone"),
                    is_present=job.get("download_available", True)
                ))

        return res

    def _parse_sql_file(self, fid: str, path: str, captured_at: str) -> List[ObservedResource]:
        res = []
        try:
            conn = sqlite3.connect(":memory:")
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                conn.executescript(f.read())
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [t[0] for t in cursor.fetchall() if t[0] != "snapshot_scope"]
            
            for tname in tables:
                cursor.execute(f"PRAGMA table_info({tname});")
                cols = [c[1].lower() for c in cursor.fetchall()]
                cursor.execute(f"SELECT * FROM {tname};")
                rows = cursor.fetchall()
                
                # Check if table has record_json / payload_json column (e.g. customer_data_read_replica_20260921.sql)
                json_col = None
                for candidate in ["record_json", "payload_json"]:
                    if candidate in cols:
                        json_col = candidate
                        break

                if json_col:
                    p_idx = cols.index(json_col)
                    s_idx = None
                    for sc in ["origin_system", "system_id"]:
                        if sc in cols:
                            s_idx = cols.index(sc)
                            break
                    r_idx = cols.index("resource_id") if "resource_id" in cols else None
                    
                    for r in rows:
                        rid = r[r_idx] if r_idx is not None else None
                        sys_id = r[s_idx] if s_idx is not None else None
                        try:
                            payload = json.loads(r[p_idx])
                        except Exception:
                            payload = {}
                            
                        uid = payload.get("customer_reference") or payload.get("subject_reference") or payload.get("user_id")
                        em = payload.get("email") or payload.get("customer_email") or payload.get("requester_email") or payload.get("subject_selector")
                        if not em and "document" in payload:
                            doc = payload["document"]
                            em = doc.get("email")
                            uid = uid or doc.get("customer_reference")
                            
                        # If email is in message_text (e.g. support conversations)
                        if not em and "message_text" in payload:
                            m_em = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", payload["message_text"])
                            if m_em:
                                em = m_em.group(0)

                        ph = payload.get("phone") or payload.get("requester_phone")
                        nm = payload.get("display_name") or payload.get("full_name") or payload.get("name")
                        eh = payload.get("email_hash")
                        
                        is_pres = True
                        is_act = False
                        is_red = False
                        is_anon = False
                        is_blk = False
                        is_dis = False
                        
                        if sys_id == "analytics_platform":
                            has_pii = bool(em or uid or ph or eh)
                            is_anon = (not has_pii)
                        elif sys_id == "support_platform":
                            has_pii = bool(em or ph or nm or ("message_text" in payload and "[REDACTED]" not in payload["message_text"]))
                            is_red = (not has_pii)
                        elif sys_id == "integration_service":
                            en = payload.get("enabled", False)
                            is_act = en
                            is_dis = (not en)
                        elif sys_id == "backup_service":
                            ra = payload.get("restore_allowed", False)
                            is_act = ra
                            is_blk = (not ra)
                            
                        res.append(ObservedResource(
                            system_id=sys_id,
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=uid,
                            email=em,
                            phone=ph,
                            name=nm,
                            email_hash=eh,
                            is_present=is_pres,
                            is_active=is_act,
                            is_redacted=is_red,
                            is_anonymized=is_anon,
                            is_blocked=is_blk,
                            is_disabled=is_dis,
                            retention_until=payload.get("retention_until")
                        ))
                    continue

                # Case: search_documents_primary (evidence_57)
                if tname == "search_documents_primary":
                    for r in rows:
                        row_dict = {cols[i]: r[i] for i in range(len(cols))}
                        res.append(ObservedResource(
                            system_id="search_service",
                            resource_id=row_dict.get("resource_id"),
                            evidence_id=fid,
                            captured_at=captured_at,
                            email=row_dict.get("email"),
                            name=row_dict.get("display_name"),
                            source_resource_id=row_dict.get("source_resource_id"),
                            is_present=True
                        ))
                    continue

                # Standard structured inventory tables
                for r in rows:
                    row_dict = {cols[i]: r[i] for i in range(len(cols))}
                    rid = row_dict.get("resource_id")
                    uid = row_dict.get("customer_reference") or row_dict.get("subject_reference") or row_dict.get("user_id")
                    em = row_dict.get("email") or row_dict.get("owner_email") or row_dict.get("requester_email") or row_dict.get("customer_email")
                    ph = row_dict.get("phone") or row_dict.get("owner_phone") or row_dict.get("requester_phone")
                    nm = row_dict.get("full_name") or row_dict.get("display_name") or row_dict.get("name") or row_dict.get("requester_name")
                    eh = row_dict.get("email_hash")
                    
                    if "customer_profiles" in tname:
                        res.append(ObservedResource(
                            system_id="account_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=uid,
                            email=em,
                            phone=ph,
                            name=nm,
                            email_hash=eh,
                            is_present=True
                        ))
                    elif "search" in tname:
                        res.append(ObservedResource(
                            system_id="search_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=uid,
                            email=em,
                            phone=ph,
                            name=nm,
                            email_hash=eh,
                            is_present=True
                        ))
                    elif "analytics" in tname:
                        has_pii = bool(em or uid or ph or eh)
                        res.append(ObservedResource(
                            system_id="analytics_platform",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=uid,
                            email=em,
                            phone=ph,
                            email_hash=eh,
                            is_present=True,
                            is_anonymized=(not has_pii)
                        ))
                    elif "support" in tname:
                        has_pii = bool(em or ph or nm)
                        res.append(ObservedResource(
                            system_id="support_platform",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=uid,
                            email=em,
                            phone=ph,
                            name=nm,
                            is_present=True,
                            is_redacted=(not has_pii)
                        ))
                    elif "export" in tname:
                        res.append(ObservedResource(
                            system_id="export_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=uid,
                            email=em,
                            phone=ph,
                            name=nm,
                            is_present=True
                        ))
                    elif "connector" in tname:
                        en = bool(row_dict.get("enabled", 0))
                        res.append(ObservedResource(
                            system_id="integration_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=uid,
                            email=em,
                            is_present=True,
                            is_active=en,
                            is_disabled=(not en)
                        ))
                    elif "backup" in tname:
                        ra = bool(row_dict.get("restore_allowed", 0))
                        res.append(ObservedResource(
                            system_id="backup_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=uid,
                            email=em,
                            is_present=True,
                            is_active=ra,
                            is_blocked=(not ra)
                        ))
                    elif "security" in tname or "audit" in tname:
                        res.append(ObservedResource(
                            system_id="security_service",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=captured_at,
                            user_id=uid,
                            is_present=True,
                            retention_until=row_dict.get("retention_until")
                        ))
            conn.close()
        except Exception:
            pass
        return res

    def _parse_log_file(self, fid: str, path: str, captured_at: str) -> List[ObservedResource]:
        res = []
        try:
            traces: Dict[str, Dict[str, Any]] = {}
            standalone_lines: List[Dict[str, Any]] = []

            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    iso_match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)", line)
                    line_ts = iso_match.group(1) if iso_match else captured_at

                    # Parse JSON or key-value format
                    data = None
                    if "{" in line and "}" in line:
                        idx = line.find("{")
                        try:
                            data = json.loads(line[idx:].strip())
                        except Exception:
                            pass
                    if not data:
                        data = dict(re.findall(r'(\w+)=["\']?([^"\'\s]+)["\']?', line))

                    if "event_time" not in data and line_ts:
                        data["event_time"] = line_ts

                    tid = data.get("trace_id")
                    if tid:
                        if tid not in traces:
                            traces[tid] = {}
                        traces[tid].update(data)
                    elif data.get("resource_id"):
                        standalone_lines.append(data)

            # Process all traces and standalone entries
            all_records = list(traces.values()) + standalone_lines

            for parts in all_records:
                rid = parts.get("resource_id")
                if not rid:
                    continue
                rec_cap = parts.get("event_time") or captured_at
                service = parts.get("service")
                lookup_key = parts.get("lookup_key") or parts.get("match_key") or parts.get("correlation_key") or parts.get("subject_key")

                if not service:
                    pref = rid.split("_")[0]
                    sys_map = {
                        "account": "account_service", "search": "search_service",
                        "support": "support_platform", "analytics": "analytics_platform",
                        "data": "integration_service", "backup": "backup_service",
                        "audit": "security_service", "export": "export_service"
                    }
                    service = sys_map.get(pref, "account_service")

                uid = parts.get("customer_reference") or parts.get("subject_reference") or parts.get("subject_ref")
                if uid == "null": uid = None
                em = parts.get("email") or parts.get("requester_email") or parts.get("customer_email") or parts.get("matched_value")
                if em == "null": em = None
                if not em and lookup_key and "@" in lookup_key:
                    em = lookup_key
                if not uid and lookup_key and lookup_key.startswith("user_"):
                    uid = lookup_key

                ph = parts.get("phone") or parts.get("requester_phone")
                if ph == "null": ph = None
                nm = parts.get("name") or parts.get("requester_name")
                if nm == "null": nm = None
                eh = parts.get("email_hash")
                corr = parts.get("correlation_key")
                if not eh and corr and len(corr) == 64 and all(c in "0123456789abcdefABCDEF" for c in corr):
                    eh = corr.lower()

                if service == "account_service":
                    http_status = str(parts.get("http_status", ""))
                    rows = int(parts.get("rows", "0")) if str(parts.get("rows", "")).isdigit() else 0
                    is_pres = (http_status != "404" and rows > 0)
                    res.append(ObservedResource(
                        system_id="account_service",
                        resource_id=rid,
                        evidence_id=fid,
                        captured_at=rec_cap,
                        user_id=uid,
                        email=em,
                        is_present=is_pres
                    ))
                elif service == "search_service":
                    result = parts.get("result")
                    total = int(parts.get("total_hits", "0")) if str(parts.get("total_hits", "")).isdigit() else 0
                    res.append(ObservedResource(
                        system_id="search_service",
                        resource_id=rid,
                        evidence_id=fid,
                        captured_at=rec_cap,
                        user_id=uid,
                        email=em,
                        is_present=(result == "hit" or total > 0)
                    ))
                elif service == "analytics_platform":
                    has_pii = bool(em or uid or ph or eh)
                    # If email_opt_in is present and true, or contact rows > 0 with opt-in
                    is_remaining = (str(parts.get("email_opt_in", "")).lower() == "true")
                    res.append(ObservedResource(
                        system_id="analytics_platform",
                        resource_id=rid,
                        evidence_id=fid,
                        captured_at=rec_cap,
                        user_id=uid,
                        email=em,
                        phone=ph,
                        email_hash=eh,
                        details="REMAINING" if is_remaining else "",
                        is_present=True,
                        is_anonymized=(not has_pii and not is_remaining)
                    ))
                elif service in ["support_platform", "support_replica"]:
                    ev_name = parts.get("event", "")
                    marker_found = str(parts.get("marker_found", "")).lower()
                    rows = int(parts.get("rows", "0")) if str(parts.get("rows", "")).isdigit() else 0
                    is_attachment = (marker_found == "false" or "attachment" in rid or "ATTACHMENT" in ev_name)
                    if "pii_scan" in ev_name or "matched_value" in parts:
                        res.append(ObservedResource(
                            system_id="support_platform",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=rec_cap,
                            user_id=uid,
                            email=em,
                            phone=ph,
                            name=nm,
                            details="ATTACHMENT" if is_attachment else "",
                            is_present=True,
                            is_redacted=False
                        ))
                    else:
                        has_pii = bool(em or ph or nm)
                        res.append(ObservedResource(
                            system_id="support_platform",
                            resource_id=rid,
                            evidence_id=fid,
                            captured_at=rec_cap,
                            user_id=uid,
                            email=em,
                            phone=ph,
                            name=nm,
                            details="ATTACHMENT" if is_attachment else "",
                            is_present=True,
                            is_redacted=(not has_pii and not is_attachment)
                        ))
                elif service == "integration_service":
                    en = (str(parts.get("enabled", "")).lower() == "true")
                    res.append(ObservedResource(
                        system_id="integration_service",
                        resource_id=rid,
                        evidence_id=fid,
                        captured_at=rec_cap,
                        user_id=uid,
                        email=em,
                        is_present=True,
                        is_active=en,
                        is_disabled=(not en)
                    ))
                elif service == "backup_service":
                    restore_allowed = str(parts.get("restore_allowed", "")).lower()
                    eligible = str(parts.get("eligible", "")).lower()
                    deletion_block = str(parts.get("deletion_block", "")).lower()
                    ra = (restore_allowed == "true" or (eligible == "true" and deletion_block != "true"))
                    res.append(ObservedResource(
                        system_id="backup_service",
                        resource_id=rid,
                        evidence_id=fid,
                        captured_at=rec_cap,
                        user_id=uid,
                        email=em,
                        is_present=True,
                        is_active=ra,
                        is_blocked=(not ra)
                    ))
                elif service == "security_service":
                    res.append(ObservedResource(
                        system_id="security_service",
                        resource_id=rid,
                        evidence_id=fid,
                        captured_at=rec_cap,
                        user_id=uid,
                        is_present=True,
                        retention_until=parts.get("retention_until")
                    ))
        except Exception:
            pass
        return res

    def _parse_txt_file(self, fid: str, path: str, captured_at: str) -> List[ObservedResource]:
        res = []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            for line in content.splitlines():
                if not line.strip().startswith("-"):
                    continue
                parts = [p.strip() for p in line.strip("- ").split("|")]
                if len(parts) >= 6:
                    ts, sys_id, rid, cat, status, target = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
                    em = target if "@" in target else None
                    uid = target if target.startswith("user_") else None
                    
                    is_pres = (status != "NOT_FOUND")
                    is_act = (status == "ACTIVE")
                    is_red = (status == "REDACTED")
                    is_anon = (status == "ANONYMIZED")
                    is_blk = (status == "BLOCKED")
                    is_dis = (status == "DISABLED")
                    
                    res.append(ObservedResource(
                        system_id=sys_id,
                        resource_id=rid,
                        evidence_id=fid,
                        captured_at=captured_at,
                        user_id=uid,
                        email=em,
                        details=cat,
                        is_present=is_pres,
                        is_active=is_act,
                        is_redacted=is_red,
                        is_anonymized=is_anon,
                        is_blocked=is_blk,
                        is_disabled=is_dis
                    ))
        except Exception:
            pass
        return res

    def _parse_pdf_file(self, fid: str, path: str, captured_at: str) -> List[ObservedResource]:
        res = []
        if fitz is None:
            return res
        try:
            doc = fitz.open(path)
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n"
            
            # e.g. delivery_correction_attachment.pdf -> support_001
            m_res = re.search(r"\b(support_\w+|account_\w+|legal_\w+|audit_record_\w+)\b", full_text)
            if m_res:
                rid = m_res.group(1)
                m_em = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", full_text)
                em = m_em.group(0).lower() if m_em else None
                m_ph = re.search(r"\+[\d\s\(\)-]{8,20}", full_text)
                ph = m_ph.group(0).strip() if m_ph else None
                
                res.append(ObservedResource(
                    system_id="support_platform",
                    resource_id=rid,
                    evidence_id=fid,
                    captured_at=captured_at,
                    email=em,
                    phone=ph,
                    details="ATTACHMENT",
                    is_present=True,
                    is_redacted=False
                ))
        except Exception:
            pass
        return res
