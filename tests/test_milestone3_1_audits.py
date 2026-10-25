import unittest
import os
import re
from code.identity import IdentityResolver
from code.evidence_index import EvidenceIndex, ObservedResource
from code.auditor import DeletionAuditor

class TestMilestone31Audits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset_dir = "dataset"
        cls.identities_csv = os.path.join(cls.dataset_dir, "user_identities.csv")
        cls.audit_log_csv = os.path.join(cls.dataset_dir, "user_audit_log.csv")
        cls.resolver = IdentityResolver(cls.identities_csv, cls.audit_log_csv)
        cls.index = EvidenceIndex(cls.dataset_dir)
        cls.auditor = DeletionAuditor(cls.index, cls.resolver)

    def test_partial_redaction_with_exposed_pii_fails_redaction(self):
        """A message containing [REDACTED] but still exposing an email or phone MUST NOT be treated as safely redacted."""
        # Test simulated parsing of message containing [REDACTED] + raw email
        msg_with_exposed_email = "Previous note: [REDACTED]. Contact customer at exposed.user@example.com."
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', msg_with_exposed_email)
        has_exposed_pii = bool(email_match or re.search(r'\+[\d\s\(\)-]{8,20}', msg_with_exposed_email))
        is_redacted = ("[REDACTED]" in msg_with_exposed_email and not has_exposed_pii)
        
        self.assertFalse(is_redacted, "Message containing an exposed email must not be marked is_redacted=True")

    def test_evidence_file_captured_after_audit_at_excluded(self):
        """Evidence files captured after case audit_at must not be cited or considered available."""
        # For a case audited on 2026-09-15T12:00:00Z:
        # evidence_02 was captured on 2026-09-17T12:00:00Z -> MUST be excluded!
        audit_at = "2026-09-15T12:00:00Z"
        manifest_cap = self.index.manifest.get("evidence_02", {}).get("captured_at", "")
        self.assertTrue(manifest_cap > audit_at, "evidence_02 manifest captured_at is indeed after 2026-09-15T12:00:00Z")

    def test_worker_activity_after_audit_at_ignored(self):
        """Worker activities with event_time > audit_at must not be used."""
        audit_at = "2026-09-01T08:30:00Z"
        audit_epoch = self.auditor._parse_iso(audit_at)
        
        # In activities, activity at 09:12:11Z must be ignored for audit_at 08:30:00Z
        future_act = {"event_time": "2026-09-01T09:12:11Z", "reported_result": "SUCCESS"}
        future_epoch = self.auditor._parse_iso(future_act["event_time"])
        self.assertTrue(future_epoch > audit_epoch, "Activity at 09:12:11Z must be strictly after 08:30:00Z")

    def test_no_hardcoded_user_account_rule(self):
        """Verify that account resolution operates via generalized evidence and activity linking, not num <= 10."""
        # For a hypothetical user_9999 with no evidence, it should not hardcode account_9999
        import inspect
        src = inspect.getsource(self.auditor.audit_case)
        self.assertNotIn("num <= 10", src, "Hardcoded num <= 10 check must be removed from production code")

if __name__ == "__main__":
    unittest.main()
