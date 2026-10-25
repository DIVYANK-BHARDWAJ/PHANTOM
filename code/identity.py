import csv
import hashlib
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field

@dataclass
class UserIdentityGraph:
    user_id: str
    current_name: Optional[str] = None
    current_email: Optional[str] = None
    current_phone: Optional[str] = None
    current_email_hash: Optional[str] = None
    all_emails: Set[str] = field(default_factory=set)
    all_phones: Set[str] = field(default_factory=set)
    all_names: Set[str] = field(default_factory=set)
    all_email_hashes: Set[str] = field(default_factory=set)

    def matches_identifier(self, identifier: str) -> bool:
        if not identifier:
            return False
        ident = identifier.strip().lower()
        if ident == self.user_id.lower():
            return True
        if ident in {e.lower() for e in self.all_emails}:
            return True
        if ident in self.all_phones or identifier.strip() in self.all_phones:
            return True
        if ident in self.all_email_hashes:
            return True
        return False

class IdentityResolver:
    def __init__(self, identities_csv_path: str, audit_log_csv_path: str):
        self.identities_by_id: Dict[str, Dict[str, str]] = {}
        self.email_to_id: Dict[str, str] = {}
        self.historical_email_to_id: Dict[str, str] = {}
        self.audit_records_by_user: Dict[str, List[Dict[str, str]]] = {}
        
        self._load_identities(identities_csv_path)
        self._load_audit_log(audit_log_csv_path)

    def _load_identities(self, path: str):
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = row['user_id'].strip()
                email = row['email'].strip().lower()
                self.identities_by_id[uid] = row
                self.email_to_id[email] = uid

    def _load_audit_log(self, path: str):
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = row['user_id'].strip()
                if uid not in self.audit_records_by_user:
                    self.audit_records_by_user[uid] = []
                self.audit_records_by_user[uid].append(row)
                
                field_name = row['field_name'].strip()
                old_val = row['old_value'].strip()
                if field_name == 'email' and old_val:
                    self.historical_email_to_id[old_val.lower()] = uid

    def resolve_user_id(self, email: str) -> Optional[str]:
        norm_email = email.strip().lower()
        if norm_email in self.email_to_id:
            return self.email_to_id[norm_email]
        if norm_email in self.historical_email_to_id:
            return self.historical_email_to_id[norm_email]
        return None

    def get_identity_graph(self, email: str) -> Optional[UserIdentityGraph]:
        uid = self.resolve_user_id(email)
        if not uid:
            return None
        
        ident = self.identities_by_id.get(uid, {})
        graph = UserIdentityGraph(
            user_id=uid,
            current_name=ident.get('name'),
            current_email=ident.get('email'),
            current_phone=ident.get('phone'),
            current_email_hash=ident.get('email_hash')
        )
        
        # Populate current identifiers
        if graph.current_email:
            e = graph.current_email.strip().lower()
            graph.all_emails.add(e)
            graph.all_email_hashes.add(hashlib.sha256(e.encode('utf-8')).hexdigest())
        if graph.current_phone:
            graph.all_phones.add(graph.current_phone.strip())
        if graph.current_name:
            graph.all_names.add(graph.current_name.strip())
        if graph.current_email_hash:
            graph.all_email_hashes.add(graph.current_email_hash.strip().lower())
            
        # Add the querying email itself
        q_email = email.strip().lower()
        graph.all_emails.add(q_email)
        graph.all_email_hashes.add(hashlib.sha256(q_email.encode('utf-8')).hexdigest())

        # Collect historical values from audit log
        for record in self.audit_records_by_user.get(uid, []):
            fname = record['field_name'].strip()
            old_v = record['old_value'].strip()
            new_v = record['new_value'].strip()
            
            for v in (old_v, new_v):
                if not v:
                    continue
                if fname == 'email':
                    v_low = v.lower()
                    graph.all_emails.add(v_low)
                    graph.all_email_hashes.add(hashlib.sha256(v_low.encode('utf-8')).hexdigest())
                elif fname == 'email_hash':
                    graph.all_email_hashes.add(v.lower())
                elif fname == 'phone':
                    graph.all_phones.add(v)
                elif fname == 'name':
                    graph.all_names.add(v)
                    
        return graph
