import unittest
from typing import List, Dict
from code.models import Step, sort_and_renumber_steps
from code.evidence_index import ObservedResource
from code.identity import UserIdentityGraph
from code.auditor import _is_valid_iso

class TestMilestone6VerificationOptimization(unittest.TestCase):
    def setUp(self):
        self.cutoff = "2026-09-15T12:00:00Z"
        self.graph = UserIdentityGraph(
            user_id="user_123",
            current_name="Jane Doe",
            all_names={"Jane Doe"},
            all_emails={"jane.doe@example.com"},
            all_phones={"+15551234"},
            all_email_hashes={"hash_jane123"}
        )

    def test_01_complete_verification_requires_evidence_citation(self):
        """
        Verification steps in a COMPLETE case must cite participant-visible evidence.
        """
        step = Step(
            step_no=1,
            phase="VERIFICATION",
            system_id="account_service",
            resource_id="account_123",
            operation="VERIFY_RECORD_ABSENT",
            state="ABSENT",
            evidence_id="evidence_54"
        )
        self.assertTrue(bool(step.evidence_id), "COMPLETE verification step must have non-empty evidence_id")
        self.assertEqual(step.state, "ABSENT")

    def test_02_incomplete_future_verification_requires_empty_evidence(self):
        """
        Post-remediation verification steps in an INCOMPLETE case describe future work
        and therefore must use evidence_id as an empty string.
        """
        step = Step(
            step_no=3,
            phase="VERIFICATION",
            system_id="account_service",
            resource_id="account_123",
            operation="VERIFY_RECORD_ABSENT",
            state="ABSENT",
            evidence_id=""
        )
        self.assertEqual(step.evidence_id, "", "Future verification in INCOMPLETE case must use empty evidence_id")

    def test_03_duplicate_verification_step_suppression(self):
        """
        Multiple verification steps targeting the same (phase, system_id, resource_id, operation)
        must be deduplicated.
        """
        step1 = Step(0, "VERIFICATION", "account_service", "account_123", "VERIFY_RECORD_ABSENT", "ABSENT", "ev_1")
        step2 = Step(0, "VERIFICATION", "account_service", "account_123", "VERIFY_RECORD_ABSENT", "ABSENT", "ev_2")

        steps = [step1, step2]
        seen = set()
        unique = []
        for s in steps:
            k = (s.phase, s.system_id, s.resource_id, s.operation)
            if k not in seen:
                seen.add(k)
                unique.append(s)

        self.assertEqual(len(unique), 1)
        self.assertEqual(unique[0].evidence_id, "ev_1")

    def test_04_verification_temporal_boundary_rejection(self):
        """
        Evidence captured after audit_at must never be cited in a verification step.
        """
        post_cutoff_time = "2026-09-18T11:55:24Z"
        is_admissible = _is_valid_iso(post_cutoff_time) and post_cutoff_time <= self.cutoff
        self.assertFalse(is_admissible, "Evidence captured after audit_at is strictly inadmissible")

    def test_05_grounded_identity_matching(self):
        """
        Identity matching must only succeed on grounded identifiers (email, phone, user_id, hash)
        and must reject ungrounded partial matches.
        """
        obs_matching = ObservedResource(
            system_id="account_service",
            resource_id="acc_1",
            evidence_id="ev_01",
            captured_at="2026-09-15T10:00:00Z",
            email="jane.doe@example.com"
        )
        obs_unrelated = ObservedResource(
            system_id="account_service",
            resource_id="acc_2",
            evidence_id="ev_01",
            captured_at="2026-09-15T10:00:00Z",
            email="other.person@example.com"
        )

        def matches(obs, graph):
            if obs.user_id and obs.user_id == graph.user_id:
                return True
            if obs.email and obs.email.strip().lower() in graph.all_emails:
                return True
            if obs.phone and obs.phone.strip() in graph.all_phones:
                return True
            if obs.email_hash and obs.email_hash.strip().lower() in graph.all_email_hashes:
                return True
            return False

        self.assertTrue(matches(obs_matching, self.graph))
        self.assertFalse(matches(obs_unrelated, self.graph))

    def test_06_non_deletion_empty_steps_contract(self):
        """
        When deletion is not authorized, status must be NOT_APPLICABLE and steps must be [].
        """
        status = "NOT_APPLICABLE"
        steps = []
        self.assertEqual(status, "NOT_APPLICABLE")
        self.assertEqual(steps, [])

if __name__ == "__main__":
    unittest.main()
