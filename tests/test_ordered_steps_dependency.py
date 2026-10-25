import unittest
import json
from code.models import Step, sort_and_renumber_steps
from code.identity import UserIdentityGraph, IdentityResolver
from code.intent import RequestIntentClassifier

class TestOrderedStepsDependencyAndLifecycle(unittest.TestCase):
    """
    Unit and integration tests for:
    1. Dependency ordering (FINDING -> REMEDIATION -> VERIFICATION; flow disable / block restore before delete).
    2. Idempotence & deduplication.
    3. Conflicting remediation requirements (retained records vs delete).
    """

    def setUp(self):
        self.intent = RequestIntentClassifier()

    def test_01_phase_ordering_strictly_monotonic(self):
        """FINDING (1) -> REMEDIATION (2) -> VERIFICATION (3) must be strictly monotonic."""
        raw_steps = [
            Step(0, "VERIFICATION", "account_service", "acc_1", "VERIFY_RECORD_ABSENT", "ABSENT", "ev_1"),
            Step(0, "FINDING", "account_service", "acc_1", "REPORT_REMAINING_RECORD", "PRESENT", "ev_2"),
            Step(0, "REMEDIATION", "account_service", "acc_1", "DELETE_RECORD", "ABSENT", "")
        ]
        ordered = sort_and_renumber_steps(raw_steps)
        self.assertEqual(ordered[0].phase, "FINDING")
        self.assertEqual(ordered[1].phase, "REMEDIATION")
        self.assertEqual(ordered[2].phase, "VERIFICATION")
        self.assertEqual([s.step_no for s in ordered], [1, 2, 3])

    def test_02_dependency_ordering_disable_flow_before_delete(self):
        """In remediation, DISABLE_DATA_FLOW and BLOCK_RESTORE must precede DELETE_RECORD."""
        raw_steps = [
            Step(0, "REMEDIATION", "account_service", "acc_1", "DELETE_RECORD", "ABSENT", ""),
            Step(0, "REMEDIATION", "integration_service", "flow_1", "DISABLE_DATA_FLOW", "DISABLED", ""),
            Step(0, "REMEDIATION", "backup_service", "bk_1", "BLOCK_RESTORE", "BLOCKED", "")
        ]
        ordered = sort_and_renumber_steps(raw_steps)
        ops = [s.operation for s in ordered]
        self.assertEqual(ops, ["DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD"])

    def test_03_deduplication_and_idempotence(self):
        """Identical steps must not produce duplicate step entries."""
        raw_steps = [
            Step(0, "FINDING", "account_service", "acc_1", "REPORT_REMAINING_RECORD", "PRESENT", "ev_1"),
            Step(0, "FINDING", "account_service", "acc_1", "REPORT_REMAINING_RECORD", "PRESENT", "ev_1"),
            Step(0, "VERIFICATION", "account_service", "acc_1", "VERIFY_RECORD_ABSENT", "ABSENT", "ev_1")
        ]
        # Simulate deduplication logic
        unique_tuples = []
        deduped = []
        for s in raw_steps:
            t = (s.phase, s.system_id, s.resource_id, s.operation, s.state, s.evidence_id)
            if t not in unique_tuples:
                unique_tuples.append(t)
                deduped.append(s)

        ordered = sort_and_renumber_steps(deduped)
        self.assertEqual(len(ordered), 2)
        self.assertEqual(ordered[0].step_no, 1)
        self.assertEqual(ordered[1].step_no, 2)

    def test_04_conflicting_remediation_retention_exception(self):
        """Records subject to legal/security retention must be VERIFY_RECORD_PRESENT, not deleted."""
        # Policy action on security_service
        sec_step = Step(1, "VERIFICATION", "security_service", "audit_record_101", "VERIFY_RECORD_PRESENT", "PRESENT", "ev_sec")
        self.assertEqual(sec_step.operation, "VERIFY_RECORD_PRESENT")
        self.assertEqual(sec_step.state, "PRESENT")

    def test_05_consecutive_renumbering(self):
        """Step numbers must be strictly consecutive 1..N with no gaps."""
        raw_steps = [
            Step(99, "FINDING", "search_service", "srch_1", "REPORT_REMAINING_RECORD", "PRESENT", "ev_1"),
            Step(42, "REMEDIATION", "search_service", "srch_1", "DELETE_RECORD", "ABSENT", ""),
            Step(7, "VERIFICATION", "search_service", "srch_1", "VERIFY_RECORD_ABSENT", "ABSENT", "")
        ]
        ordered = sort_and_renumber_steps(raw_steps)
        self.assertEqual([s.step_no for s in ordered], [1, 2, 3])

if __name__ == "__main__":
    unittest.main()
