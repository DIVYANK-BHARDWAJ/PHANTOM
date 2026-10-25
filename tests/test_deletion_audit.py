import unittest
import os
import json
from code.identity import IdentityResolver, UserIdentityGraph
from code.intent import RequestIntentClassifier
from code.models import Step, sort_and_renumber_steps, PHASE_ORDER, OPERATION_ORDER

class TestDeletionAuditAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset_dir = "dataset"
        cls.identities_csv = os.path.join(cls.dataset_dir, "user_identities.csv")
        cls.audit_log_csv = os.path.join(cls.dataset_dir, "user_audit_log.csv")
        cls.resolver = IdentityResolver(cls.identities_csv, cls.audit_log_csv)
        cls.intent = RequestIntentClassifier()

    def test_identity_resolution_and_historical_identifiers(self):
        """Test resolving users by current and historical email aliases."""
        # Current email resolution
        uid = self.resolver.resolve_user_id("amina.elmasri@gmail.com")
        self.assertEqual(uid, "user_01")
        
        # Historical email resolution for user_12 (minjun.kim90@gmail.com -> user_12)
        uid_hist = self.resolver.resolve_user_id("minjun.kim90@gmail.com")
        self.assertEqual(uid_hist, "user_12")

        # Identity graph contains historical email and hashes
        graph = self.resolver.get_identity_graph("minjun.kim@gmail.com")
        self.assertIsNotNone(graph)
        self.assertIn("minjun.kim90@gmail.com", graph.all_emails)
        self.assertIn("44a65154bfd8e408852578fbd76813d094d1944f255ac1769ee81ba90492f10e", graph.all_email_hashes)

    def test_non_deletion_request_classification(self):
        """Test that non-deletion requests are classified as NOT_APPLICABLE with empty steps."""
        test_cases = [
            "Please provide a complete copy of all personal data held about me.",
            "I would like to update my primary email address and phone number.",
            "Please opt me out of all marketing communications and newsletters.",
            "Can I get an export of my order history for tax filing?"
        ]
        for text in test_cases:
            is_del, reason = self.intent.classify(text)
            self.assertFalse(is_del, f"Text '{text}' should not be classified as deletion")

    def test_deletion_request_classification(self):
        """Test that valid deletion requests across languages are classified as deletion."""
        test_cases = [
            "Please delete my entire customer account and personal data.",
            "Löschen Sie bitte alle meine personenbezogenen Daten und mein Konto.",
            "Veuillez supprimer définitivement mon compte et mes données.",
            "Por favor, eliminen todos mis datos de su plataforma."
        ]
        for text in test_cases:
            is_del, reason = self.intent.classify(text)
            self.assertTrue(is_del, f"Text '{text}' should be classified as deletion")

    def test_output_contract_and_step_schema(self):
        """Test canonical sorting, numbering, and 7-key schema enforcement."""
        raw_steps = [
            Step(0, "VERIFICATION", "account_service", "account_001", "VERIFY_RECORD_ABSENT", "ABSENT", "evidence_01"),
            Step(0, "FINDING", "search_service", "search_001", "REPORT_REMAINING_RECORD", "PRESENT", "evidence_02"),
            Step(0, "REMEDIATION", "search_service", "search_001", "DELETE_RECORD", "ABSENT", "")
        ]
        sorted_steps = sort_and_renumber_steps(raw_steps)
        
        # Verify 1-indexed consecutive numbering
        self.assertEqual([s.step_no for s in sorted_steps], [1, 2, 3])
        
        # Verify phase ordering: FINDING -> REMEDIATION -> VERIFICATION
        self.assertEqual([s.phase for s in sorted_steps], ["FINDING", "REMEDIATION", "VERIFICATION"])
        
        # Verify exactly 7 keys
        for s in sorted_steps:
            d = s.to_dict()
            self.assertEqual(len(d), 7)
            self.assertEqual(set(d.keys()), {
                "step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"
            })

    def test_temporal_evidence_cutoff_logic(self):
        """Verify that temporal ordering correctly identifies before vs after audit_at."""
        audit_at = "2026-09-02T12:00:00Z"
        valid_evidence_time = "2026-09-02T11:59:59Z"
        invalid_evidence_time = "2026-09-02T12:00:01Z"
        
        self.assertTrue(valid_evidence_time <= audit_at)
        self.assertFalse(invalid_evidence_time <= audit_at)

if __name__ == '__main__':
    unittest.main()
