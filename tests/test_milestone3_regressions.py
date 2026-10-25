import unittest
import os
import json
from code.identity import IdentityResolver
from code.intent import RequestIntentClassifier
from code.evidence_index import EvidenceIndex, ObservedResource
from code.auditor import DeletionAuditor
from code.models import Step, sort_and_renumber_steps

class TestMilestone3Regressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset_dir = "dataset"
        cls.identities_csv = os.path.join(cls.dataset_dir, "user_identities.csv")
        cls.audit_log_csv = os.path.join(cls.dataset_dir, "user_audit_log.csv")
        cls.resolver = IdentityResolver(cls.identities_csv, cls.audit_log_csv)
        cls.index = EvidenceIndex(cls.dataset_dir)
        cls.auditor = DeletionAuditor(cls.index, cls.resolver)

    def test_snapshot_bundle_inner_timestamps(self):
        """Verify that individual snapshots inside snapshot bundles use their inner captured_at."""
        # Check evidence_02 (customer_data_snapshot_bundle_20260917.json)
        obs_list = self.index.observations_by_file.get("evidence_02", [])
        self.assertTrue(len(obs_list) > 0, "evidence_02 must contain parsed observations")

        # In evidence_02, security_audit_events has captured_at == 2026-09-15T12:00:00Z
        sec_obs = [o for o in obs_list if o.system_id == "security_service"]
        self.assertTrue(len(sec_obs) > 0, "evidence_02 must contain security_service observations")
        for o in sec_obs:
            self.assertEqual(o.captured_at, "2026-09-15T12:00:00Z",
                             f"Resource {o.resource_id} should have snapshot captured_at 2026-09-15T12:00:00Z")

    def test_log_line_iso_timestamp_extraction(self):
        """Verify that log lines with ISO timestamps extract the line timestamp rather than the file timestamp."""
        # Check evidence_06 (structured_service_events_eu_west_20260918.log)
        obs_list = self.index.observations_by_file.get("evidence_06", [])
        audit_4902 = [o for o in obs_list if o.resource_id == "audit_record_4902"]
        self.assertTrue(len(audit_4902) > 0, "audit_record_4902 must be found in evidence_06")
        # Line timestamp was 2026-09-16T08:52:59Z, while file capture was 2026-09-18
        self.assertEqual(audit_4902[0].captured_at, "2026-09-16T08:52:59Z",
                         "audit_record_4902 must use line timestamp 2026-09-16T08:52:59Z")

    def test_support_conversation_redaction_detection(self):
        """Verify that support conversations containing [REDACTED] are parsed as is_redacted=True."""
        obs_list = self.index.observations_by_file.get("evidence_02", [])
        support_4715 = [o for o in obs_list if o.resource_id == "support_4715"]
        self.assertTrue(len(support_4715) > 0, "support_4715 must be found in evidence_02")
        self.assertTrue(support_4715[0].is_redacted, "support_4715 with [REDACTED] must have is_redacted=True")

    def test_batch_activity_mapping(self):
        """Verify that multi-case batches correctly map account and analytics events from system_activity."""
        sample_requests = [
            {"case_id": "case_25", "email": "s.yoon04@gmail.com", "reported_at": "2026-09-02T12:00:00Z", "reported_status": "NOT_STARTED"},
            {"case_id": "case_26", "email": "almeida.mariana@gmail.com", "reported_at": "2026-09-02T12:00:00Z", "reported_status": "NOT_STARTED"}
        ]
        self.auditor.set_requests(sample_requests)
        self.assertEqual(self.auditor.batch_account_map.get("case_25"), "account_3136")
        self.assertEqual(self.auditor.batch_account_map.get("case_26"), "account_5684")

if __name__ == "__main__":
    unittest.main()
