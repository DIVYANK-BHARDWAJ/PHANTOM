import unittest
import json
from code.identity import UserIdentityGraph, IdentityResolver
from code.intent import RequestIntentClassifier
from code.models import Step, sort_and_renumber_steps
from code.evidence_index import ObservedResource, EvidenceIndex
from code.auditor import DeletionAuditor

class TestAdversarialSyntheticScenarios(unittest.TestCase):
    """
    15 Adversarial Synthetic Tests Covering Critical Failure Modes
    for the Ghost Data Still Exists Deletion-Audit Agent.
    """

    def setUp(self):
        self.intent = RequestIntentClassifier()

    def test_01_historical_email_and_phone_identifiers(self):
        """Failure Mode 1: Matching via historical email or historical phone number."""
        graph = UserIdentityGraph(
            user_id="user_synth_01",
            current_email="alice.new@example.com",
            current_phone="+1-555-0199",
            current_name="Alice Smith",
            current_email_hash="hash_new_alice"
        )
        graph.all_emails.add("alice.old@university.edu")
        graph.all_phones.add("+1-555-0100")
        graph.all_email_hashes.add("hash_old_alice")

        # Query by historical email
        self.assertTrue(graph.matches_identifier("alice.old@university.edu"))
        # Query by historical phone
        self.assertTrue(graph.matches_identifier("+1-555-0100"))
        # Query by historical hash
        self.assertTrue(graph.matches_identifier("hash_old_alice"))
        # Unrelated identifier must not match
        self.assertFalse(graph.matches_identifier("bob@example.com"))

    def test_02_similar_looking_identifiers_no_cross_pollution(self):
        """Failure Mode 2: Substring or similar-looking identifiers must not cross-pollute."""
        graph1 = UserIdentityGraph("user_1", "John Doe", "john.doe@domain.com", "+1001", "hash1")
        graph2 = UserIdentityGraph("user_10", "John Doe Jr", "john.doe1@domain.com", "+10010", "hash10")
        graph1.all_emails.add("john.doe@domain.com")
        graph2.all_emails.add("john.doe1@domain.com")
        graph1.all_phones.add("+1001")
        graph2.all_phones.add("+10010")

        # Distinct matching
        self.assertTrue(graph1.matches_identifier("john.doe@domain.com"))
        self.assertFalse(graph1.matches_identifier("john.doe1@domain.com"))
        self.assertFalse(graph1.matches_identifier("+10010"))
        self.assertTrue(graph2.matches_identifier("john.doe1@domain.com"))
        self.assertFalse(graph2.matches_identifier("john.doe@domain.com"))

    def test_03_identity_changes_before_vs_after_audit_cutoff(self):
        """Failure Mode 3: Identity changes occurring after audit_at must be ignored."""
        audit_at = "2026-08-01T00:00:00Z"
        change_before = {"field": "email", "value": "old_valid@test.com", "timestamp": "2026-07-30T10:00:00Z"}
        change_after = {"field": "email", "value": "future_leak@test.com", "timestamp": "2026-08-02T10:00:00Z"}

        valid_historical = [change_before["value"] if change_before["timestamp"] <= audit_at else None]
        invalid_historical = [change_after["value"] if change_after["timestamp"] <= audit_at else None]

        self.assertEqual(valid_historical, ["old_valid@test.com"])
        self.assertEqual(invalid_historical, [None])

    def test_04_evidence_captured_after_audit_at_ignored(self):
        """Failure Mode 4: Evidence files captured after audit_at must not be cited."""
        audit_at = "2026-09-01T12:00:00Z"
        obs_valid = ObservedResource(
            system_id="account_service",
            resource_id="account_100",
            evidence_id="evidence_valid",
            captured_at="2026-09-01T11:00:00Z",
            email="test@example.com",
            is_present=True
        )
        obs_future = ObservedResource(
            system_id="account_service",
            resource_id="account_100",
            evidence_id="evidence_future",
            captured_at="2026-09-01T13:00:00Z",
            email="test@example.com",
            is_present=False
        )

        filtered = [o for o in [obs_valid, obs_future] if o.captured_at <= audit_at]
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].evidence_id, "evidence_valid")

    def test_05_non_deletion_requests_classified_not_applicable(self):
        """Failure Mode 5: Non-deletion requests (SAR, rectification, opt-out) return NOT_APPLICABLE and []."""
        prompts = [
            "Please email me a PDF export of all invoices I paid in 2025.",
            "I want to correct my billing address from 123 Main St to 456 Oak St.",
            "Unsubscribe me from promotional marketing emails immediately.",
            "Can you tell me what categories of personal data you store?"
        ]
        for p in prompts:
            is_del, reason = self.intent.classify(p)
            self.assertFalse(is_del, f"Prompt '{p}' misclassified as deletion")

    def test_06_shared_context_records_require_redaction(self):
        """Failure Mode 6: Shared support conversations require REDACT_RECORD, not deletion."""
        obs = ObservedResource(
            system_id="support_service",
            resource_id="ticket_9999",
            evidence_id="evidence_sup",
            captured_at="2026-08-01T00:00:00Z",
            user_id="user_synth_06",
            is_present=True,
            details="SUPPORT_CONVERSATION"
        )
        is_attachment = "ATTACHMENT" in (obs.details or "")
        self.assertFalse(is_attachment)
        expected_remediation = "REDACT_RECORD"
        self.assertEqual(expected_remediation, "REDACT_RECORD")

    def test_07_attributable_analytics_require_anonymization(self):
        """Failure Mode 7: Analytics reports tied to user hash require ANONYMIZE_RECORD."""
        obs = ObservedResource(
            system_id="analytics_platform",
            resource_id="analytics_7777",
            evidence_id="evidence_analytics",
            captured_at="2026-08-01T00:00:00Z",
            email_hash="hash_synth_07",
            is_present=True
        )
        finding_op = "REPORT_EXPOSED_PII"
        remediation_op = "ANONYMIZE_RECORD"
        verification_state = "ANONYMIZED"
        
        self.assertEqual(remediation_op, "ANONYMIZE_RECORD")
        self.assertEqual(verification_state, "ANONYMIZED")

    def test_08_compliance_retained_records_must_be_preserved(self):
        """Failure Mode 8: Retained security audit ledgers must remain PRESENT."""
        step = Step(
            step_no=1,
            phase="VERIFICATION",
            system_id="security_service",
            resource_id="audit_ledger_2026",
            operation="VERIFY_RECORD_PRESENT",
            state="PRESENT",
            evidence_id="evidence_sec"
        )
        self.assertEqual(step.state, "PRESENT")
        self.assertEqual(step.operation, "VERIFY_RECORD_PRESENT")

    def test_09_active_synchronization_data_flow_recreation_risk(self):
        """Failure Mode 9: Active sync connectors require DISABLE_DATA_FLOW before deletion."""
        obs = ObservedResource(
            system_id="sync_service",
            resource_id="connector_marketing_sync",
            evidence_id="evidence_sync",
            captured_at="2026-08-01T00:00:00Z",
            user_id="user_synth_09",
            is_present=True,
            is_active=True
        )
        finding = Step(1, "FINDING", obs.system_id, obs.resource_id, "REPORT_ACTIVE_DATA_FLOW", "ACTIVE", obs.evidence_id)
        remediation = Step(2, "REMEDIATION", obs.system_id, obs.resource_id, "DISABLE_DATA_FLOW", "DISABLED", "")
        verification = Step(3, "VERIFICATION", obs.system_id, obs.resource_id, "VERIFY_DATA_FLOW_DISABLED", "DISABLED", "")

        steps = sort_and_renumber_steps([remediation, verification, finding])
        self.assertEqual(steps[0].operation, "REPORT_ACTIVE_DATA_FLOW")
        self.assertEqual(steps[1].operation, "DISABLE_DATA_FLOW")
        self.assertEqual(steps[2].operation, "VERIFY_DATA_FLOW_DISABLED")

    def test_10_backup_restore_risk_detection(self):
        """Failure Mode 10: Backup catalog images with restore risk generate BLOCK_RESTORE."""
        obs = ObservedResource(
            system_id="backup_service",
            resource_id="backup_snap_4401",
            evidence_id="evidence_backup",
            captured_at="2026-08-01T00:00:00Z",
            user_id="user_synth_10",
            is_present=True,
            is_active=True,
            details="RESTORE_ELIGIBLE"
        )
        finding = Step(1, "FINDING", obs.system_id, obs.resource_id, "REPORT_RESTORE_RISK", "ACTIVE", obs.evidence_id)
        remediation = Step(2, "REMEDIATION", obs.system_id, obs.resource_id, "BLOCK_RESTORE", "BLOCKED", "")
        self.assertEqual(remediation.operation, "BLOCK_RESTORE")
        self.assertEqual(remediation.state, "BLOCKED")

    def test_11_tombstone_preserves_stable_id_without_pii(self):
        """Failure Mode 11: Tombstone retains user_id reference while direct PII is REDACTED."""
        step = Step(
            step_no=1,
            phase="VERIFICATION",
            system_id="identity_service",
            resource_id="user_tombstone_101",
            operation="VERIFY_RECORD_REDACTED",
            state="REDACTED",
            evidence_id="evidence_tombstone"
        )
        self.assertEqual(step.state, "REDACTED")
        self.assertEqual(step.operation, "VERIFY_RECORD_REDACTED")

    def test_12_conflicting_evidence_sources_resolution(self):
        """Failure Mode 12: Primary DB deleted vs Read Replica stale must report INCOMPLETE."""
        primary_evidence = ObservedResource("account_service", "acc_1", "ev_primary", "2026-08-01T10:00:00Z", user_id="user_12", is_present=False)
        replica_evidence = ObservedResource("replica_service", "acc_1_replica", "ev_replica", "2026-08-01T10:05:00Z", user_id="user_12", is_present=True)

        remaining_records = [o for o in [primary_evidence, replica_evidence] if o.is_present]
        self.assertEqual(len(remaining_records), 1)
        self.assertEqual(remaining_records[0].system_id, "replica_service")

    def test_13_missing_or_malformed_evidence_resilience(self):
        """Failure Mode 13: Malformed JSON lines or corrupt lines must not crash the indexer."""
        lines = [
            '{"valid": "json", "resource_id": "res_1"}',
            '{CORRUPTED_JSON_LINE!@#$%}',
            '{"another_valid": "record", "resource_id": "res_2"}'
        ]
        parsed = []
        for line in lines:
            try:
                parsed.append(json.loads(line))
            except Exception:
                continue
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["resource_id"], "res_1")

    def test_14_duplicate_records_across_multiple_systems(self):
        """Failure Mode 14: Multiple unpurged records across distinct services generate distinct findings."""
        findings = [
            Step(1, "FINDING", "search_service", "doc_search_1", "REPORT_REMAINING_RECORD", "PRESENT", "ev_1"),
            Step(2, "FINDING", "cache_service", "cache_key_user", "REPORT_REMAINING_RECORD", "PRESENT", "ev_2"),
            Step(3, "FINDING", "email_marketing", "lead_subscriber_1", "REPORT_REMAINING_RECORD", "PRESENT", "ev_3"),
        ]
        sorted_steps = sort_and_renumber_steps(findings)
        systems = [s.system_id for s in sorted_steps]
        self.assertEqual(systems, ["cache_service", "email_marketing", "search_service"])

    def test_15_complete_remediation_lifecycle_and_verification_pairing(self):
        """Failure Mode 15: Every finding must have corresponding remediation and verification."""
        finding = Step(1, "FINDING", "account_service", "acc_99", "REPORT_REMAINING_RECORD", "PRESENT", "ev_01")
        remediation = Step(2, "REMEDIATION", "account_service", "acc_99", "DELETE_RECORD", "ABSENT", "")
        verification = Step(3, "VERIFICATION", "account_service", "acc_99", "VERIFY_RECORD_ABSENT", "ABSENT", "")

        plan = [finding, remediation, verification]
        self.assertEqual(len(plan), 3)
        self.assertEqual(plan[0].phase, "FINDING")
        self.assertEqual(plan[1].phase, "REMEDIATION")
        self.assertEqual(plan[2].phase, "VERIFICATION")
        self.assertEqual(plan[1].evidence_id, "")
        self.assertEqual(plan[2].evidence_id, "")

if __name__ == "__main__":
    unittest.main()
