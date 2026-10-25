import unittest
import copy
from typing import Dict, List, Any
from code.identity import UserIdentityGraph, IdentityResolver
from code.evidence_index import ObservedResource, EvidenceIndex
from code.auditor import DeletionAuditor
from code.models import Step

class MockEvidenceIndex:
    def __init__(self):
        self.manifest: Dict[str, Dict[str, str]] = {}
        self.activities: List[Dict[str, str]] = []
        self.observations_by_file: Dict[str, List[ObservedResource]] = {}

class MockIdentityResolver:
    def __init__(self):
        self.graphs: Dict[str, UserIdentityGraph] = {}

    def get_identity_graph(self, email: str) -> UserIdentityGraph:
        return self.graphs.get(email.strip().lower())

class TestMilestone4AdversarialScenarios(unittest.TestCase):
    """
    Milestone 4: Adversarial Robustness & Correctness Audit
    Comprehensive test suite covering Priority Zero Batch-Attribution Collision,
    Metamorphic Cross-Case Isolation, and 12 Adversarial Scenarios.
    """

    def setUp(self):
        self.index = MockEvidenceIndex()
        self.resolver = MockIdentityResolver()

    def test_scenario_01_two_users_close_in_time(self):
        """Scenario 1: Two users have requests close together in time."""
        # Setup User A and User B
        gA = UserIdentityGraph("user_101", "User A", "user.a@test.com", "+1001", "hashA")
        gA.all_emails.add("user.a@test.com")
        gB = UserIdentityGraph("user_102", "User B", "user.b@test.com", "+1002", "hashB")
        gB.all_emails.add("user.b@test.com")
        self.resolver.graphs["user.a@test.com"] = gA
        self.resolver.graphs["user.b@test.com"] = gB

        self.index.manifest = {
            "ev_A": {"captured_at": "2026-09-01T12:00:00Z"},
            "ev_B": {"captured_at": "2026-09-01T12:00:00Z"}
        }
        self.index.observations_by_file = {
            "ev_A": [ObservedResource("account_service", "account_101", "ev_A", "2026-09-01T11:00:00Z", email="user.a@test.com", is_present=False)],
            "ev_B": [ObservedResource("account_service", "account_102", "ev_B", "2026-09-01T11:00:05Z", email="user.b@test.com", is_present=False)]
        }

        auditor = DeletionAuditor(self.index, self.resolver)
        reqA = {"case_id": "c1", "email": "user.a@test.com", "requested_at": "2026-08-30T10:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-09-01T12:00:00Z", "audit_at": "2026-09-01T12:00:00Z", "request_text": "Delete my account."}
        reqB = {"case_id": "c2", "email": "user.b@test.com", "requested_at": "2026-08-30T10:00:05Z", "reported_status": "COMPLETE", "reported_at": "2026-09-01T12:00:00Z", "audit_at": "2026-09-01T12:00:00Z", "request_text": "Delete my account."}

        stA, stepsA = auditor.audit_case(reqA)
        stB, stepsB = auditor.audit_case(reqB)

        self.assertEqual(stA, "COMPLETE")
        self.assertEqual(stB, "COMPLETE")
        accA = [s.resource_id for s in stepsA if s.system_id == "account_service"]
        accB = [s.resource_id for s in stepsB if s.system_id == "account_service"]
        self.assertEqual(accA, ["account_101"])
        self.assertEqual(accB, ["account_102"])

    def test_scenario_02_shared_batch_different_users(self):
        """Scenario 2: Two cases share a batch timestamp but refer to different users."""
        g1 = UserIdentityGraph("user_201", "User 1", "u1@test.com", "+2001", "hash1")
        g1.all_emails.add("u1@test.com")
        g2 = UserIdentityGraph("user_202", "User 2", "u2@test.com", "+2002", "hash2")
        g2.all_emails.add("u2@test.com")
        self.resolver.graphs["u1@test.com"] = g1
        self.resolver.graphs["u2@test.com"] = g2

        self.index.manifest = {"ev_1": {"captured_at": "2026-09-01T12:00:00Z"}}
        # User 1 has known account in evidence
        self.index.observations_by_file = {
            "ev_1": [ObservedResource("account_service", "account_201", "ev_1", "2026-09-01T11:00:00Z", email="u1@test.com", is_present=False)]
        }
        # Activities have events for both
        self.index.activities = [
            {"activity_id": "act_1", "event_time": "2026-09-01T11:10:00Z", "source_system": "deletion_worker", "target_system": "account_service", "resource_id": "account_201", "reported_result": "SUCCESS"},
            {"activity_id": "act_2", "event_time": "2026-09-01T11:20:00Z", "source_system": "deletion_worker", "target_system": "account_service", "resource_id": "account_202", "reported_result": "SUCCESS"}
        ]

        auditor = DeletionAuditor(self.index, self.resolver)
        reqs = [
            {"case_id": "c1", "email": "u1@test.com", "requested_at": "2026-08-30T10:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-09-01T12:00:00Z", "audit_at": "2026-09-01T12:00:00Z", "request_text": "Delete me."},
            {"case_id": "c2", "email": "u2@test.com", "requested_at": "2026-08-30T10:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-09-01T12:00:00Z", "audit_at": "2026-09-01T12:00:00Z", "request_text": "Delete me."}
        ]
        auditor.set_requests(reqs)

        st1, steps1 = auditor.audit_case(reqs[0])
        st2, steps2 = auditor.audit_case(reqs[1])

        acc1 = [s.resource_id for s in steps1 if s.system_id == "account_service"]
        acc2 = [s.resource_id for s in steps2 if s.system_id == "account_service"]

        self.assertEqual(acc1, ["account_201"])
        self.assertEqual(acc2, ["account_202"])

    def test_scenario_03_single_batch_multiple_users_events(self):
        """Scenario 3: A single batch contains events belonging to multiple users."""
        gA = UserIdentityGraph("user_301", "Alice", "alice@test.com", "+3001", "hashA")
        gA.all_emails.add("alice@test.com")
        self.resolver.graphs["alice@test.com"] = gA

        self.index.manifest = {"ev_1": {"captured_at": "2026-09-01T12:00:00Z"}}
        self.index.observations_by_file = {
            "ev_1": [
                ObservedResource("search_service", "search_alice", "ev_1", "2026-09-01T11:00:00Z", email="alice@test.com", is_present=True),
                ObservedResource("search_service", "search_bob", "ev_1", "2026-09-01T11:00:00Z", email="bob@test.com", is_present=True)
            ]
        }

        auditor = DeletionAuditor(self.index, self.resolver)
        reqA = {"case_id": "cA", "email": "alice@test.com", "requested_at": "2026-08-30T10:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-09-01T12:00:00Z", "audit_at": "2026-09-01T12:00:00Z", "request_text": "Delete my account."}

        stA, stepsA = auditor.audit_case(reqA)
        # Alice must only have search_alice finding, never search_bob
        rids = {s.resource_id for s in stepsA}
        self.assertIn("search_alice", rids)
        self.assertNotIn("search_bob", rids)

    def test_scenario_04_similar_timestamps_unrelated_users(self):
        """Scenario 4: Similar timestamps occur across unrelated users."""
        g = UserIdentityGraph("user_401", "User 401", "u401@test.com", "+4001", "hash401")
        g.all_emails.add("u401@test.com")
        self.resolver.graphs["u401@test.com"] = g

        self.index.manifest = {"ev_1": {"captured_at": "2026-09-01T12:00:00Z"}}
        # Event at 11:00:01 belongs to User 401, event at 11:00:02 belongs to stranger
        self.index.observations_by_file = {
            "ev_1": [
                ObservedResource("support_platform", "support_401", "ev_1", "2026-09-01T11:00:01Z", email="u401@test.com", is_present=True, is_redacted=False),
                ObservedResource("support_platform", "support_999", "ev_1", "2026-09-01T11:00:02Z", email="stranger@test.com", is_present=True, is_redacted=False)
            ]
        }

        auditor = DeletionAuditor(self.index, self.resolver)
        req = {"case_id": "c401", "email": "u401@test.com", "requested_at": "2026-08-30T10:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-09-01T12:00:00Z", "audit_at": "2026-09-01T12:00:00Z", "request_text": "Delete everything."}

        st, steps = auditor.audit_case(req)
        rids = {s.resource_id for s in steps}
        self.assertIn("support_401", rids)
        self.assertNotIn("support_999", rids)

    def test_scenario_05_multiple_identities_same_activity_cluster(self):
        """Scenario 5: Interleaved activity cluster does not merge distinct users."""
        gA = UserIdentityGraph("user_501", "User 501", "u501@test.com", "+5001", "hash501")
        gA.all_emails.add("u501@test.com")
        self.resolver.graphs["u501@test.com"] = gA

        self.index.manifest = {"ev_1": {"captured_at": "2026-09-01T12:00:00Z"}}
        self.index.activities = [
            {"activity_id": "act_1", "event_time": "2026-09-01T10:00:00Z", "source_system": "profile_service", "target_system": "account_service", "resource_id": "account_501", "reported_result": "SUCCESS"},
            {"activity_id": "act_2", "event_time": "2026-09-01T10:01:00Z", "source_system": "profile_service", "target_system": "account_service", "resource_id": "account_OTHER", "reported_result": "SUCCESS"}
        ]
        self.index.observations_by_file = {
            "ev_1": [ObservedResource("account_service", "account_501", "ev_1", "2026-09-01T10:00:00Z", email="u501@test.com", is_present=True)]
        }

        auditor = DeletionAuditor(self.index, self.resolver)
        req = {"case_id": "c501", "email": "u501@test.com", "requested_at": "2026-08-30T10:00:00Z", "reported_status": "NOT_STARTED", "reported_at": "2026-09-01T12:00:00Z", "audit_at": "2026-09-01T12:00:00Z", "request_text": "Delete my account."}

        st, steps = auditor.audit_case(req)
        rids = {s.resource_id for s in steps}
        self.assertIn("account_501", rids)
        self.assertNotIn("account_OTHER", rids)

    def test_scenario_06_user_id_in_event_vs_metadata(self):
        """Scenario 6: User ID in event while another user appears in surrounding metadata."""
        g = UserIdentityGraph("user_601", "User 601", "u601@test.com", "+6001", "hash601")
        g.all_emails.add("u601@test.com")
        self.resolver.graphs["u601@test.com"] = g

        self.index.manifest = {"ev_1": {"captured_at": "2026-09-01T12:00:00Z"}}
        self.index.observations_by_file = {
            "ev_1": [
                ObservedResource("backup_service", "backup_601", "ev_1", "2026-09-01T11:00:00Z", user_id="user_601", is_present=True, is_active=True),
                ObservedResource("backup_service", "backup_602", "ev_1", "2026-09-01T11:00:00Z", user_id="user_OTHER", is_present=True, is_active=True)
            ]
        }

        auditor = DeletionAuditor(self.index, self.resolver)
        req = {"case_id": "c601", "email": "u601@test.com", "requested_at": "2026-08-30T10:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-09-01T12:00:00Z", "audit_at": "2026-09-01T12:00:00Z", "request_text": "Delete all data."}

        st, steps = auditor.audit_case(req)
        rids = {s.resource_id for s in steps}
        self.assertIn("backup_601", rids)
        self.assertNotIn("backup_602", rids)

    def test_scenario_07_missing_null_malformed_attribution(self):
        """Scenario 7: Missing, null, malformed user attribution is safely ignored."""
        g = UserIdentityGraph("user_701", "User 701", "u701@test.com", "+7001", "hash701")
        g.all_emails.add("u701@test.com")
        self.resolver.graphs["u701@test.com"] = g

        self.index.manifest = {"ev_1": {"captured_at": "2026-09-01T12:00:00Z"}}
        self.index.observations_by_file = {
            "ev_1": [
                ObservedResource("export_service", "export_null", "ev_1", "2026-09-01T11:00:00Z", user_id=None, email=None, is_present=True),
                ObservedResource("export_service", "export_701", "ev_1", "2026-09-01T11:00:00Z", user_id="user_701", email="u701@test.com", is_present=True)
            ]
        }

        auditor = DeletionAuditor(self.index, self.resolver)
        req = {"case_id": "c701", "email": "u701@test.com", "requested_at": "2026-08-30T10:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-09-01T12:00:00Z", "audit_at": "2026-09-01T12:00:00Z", "request_text": "Delete my account."}

        st, steps = auditor.audit_case(req)
        rids = {s.resource_id for s in steps}
        self.assertIn("export_701", rids)
        self.assertNotIn("export_null", rids)

    def test_scenario_08_reused_resource_ids_across_systems(self):
        """Scenario 8: Same resource number across different systems is never conflated."""
        g = UserIdentityGraph("user_801", "User 801", "u801@test.com", "+8001", "hash801")
        g.all_emails.add("u801@test.com")
        self.resolver.graphs["u801@test.com"] = g

        self.index.manifest = {"ev_1": {"captured_at": "2026-09-01T12:00:00Z"}}
        # search_500 belongs to user_801, but support_500 belongs to stranger
        self.index.observations_by_file = {
            "ev_1": [
                ObservedResource("search_service", "search_500", "ev_1", "2026-09-01T11:00:00Z", user_id="user_801", email="u801@test.com", is_present=True),
                ObservedResource("support_platform", "support_500", "ev_1", "2026-09-01T11:00:00Z", user_id="user_STRANGER", email="stranger@test.com", is_present=True)
            ]
        }

        auditor = DeletionAuditor(self.index, self.resolver)
        req = {"case_id": "c801", "email": "u801@test.com", "requested_at": "2026-08-30T10:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-09-01T12:00:00Z", "audit_at": "2026-09-01T12:00:00Z", "request_text": "Delete."}

        st, steps = auditor.audit_case(req)
        systems = {s.system_id for s in steps}
        self.assertIn("search_service", systems)
        self.assertNotIn("support_platform", systems)

    def test_scenario_09_batch_contains_relevant_and_irrelevant_events(self):
        """Scenario 9: Unrelated operational activities do not interfere with deletion audit."""
        g = UserIdentityGraph("user_901", "User 901", "u901@test.com", "+9001", "hash901")
        g.all_emails.add("u901@test.com")
        self.resolver.graphs["u901@test.com"] = g

        self.index.manifest = {"ev_1": {"captured_at": "2026-09-01T12:00:00Z"}}
        self.index.observations_by_file = {
            "ev_1": [ObservedResource("account_service", "account_901", "ev_1", "2026-09-01T11:00:00Z", user_id="user_901", email="u901@test.com", is_present=False)]
        }
        self.index.activities = [
            {"activity_id": "act_bg1", "event_time": "2026-09-01T11:10:00Z", "source_system": "notification_service", "target_system": "email_service", "resource_id": "email_999", "reported_result": "SUCCESS"},
            {"activity_id": "act_bg2", "event_time": "2026-09-01T11:15:00Z", "source_system": "account_service", "target_system": "search_service", "resource_id": "search_888", "reported_result": "SUCCESS"}
        ]

        auditor = DeletionAuditor(self.index, self.resolver)
        req = {"case_id": "c901", "email": "u901@test.com", "requested_at": "2026-08-30T10:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-09-01T12:00:00Z", "audit_at": "2026-09-01T12:00:00Z", "request_text": "Delete."}

        st, steps = auditor.audit_case(req)
        self.assertEqual(st, "COMPLETE")
        rids = {s.resource_id for s in steps}
        self.assertIn("account_901", rids)
        self.assertNotIn("email_999", rids)
        self.assertNotIn("search_888", rids)

    def test_scenario_10_delayed_and_reordered_events(self):
        """Scenario 10: State resolution evaluates observations chronologically up to audit_at."""
        g = UserIdentityGraph("user_1001", "User 1001", "u1001@test.com", "+10001", "hash1001")
        g.all_emails.add("u1001@test.com")
        self.resolver.graphs["u1001@test.com"] = g

        self.index.manifest = {
            "ev_early": {"captured_at": "2026-08-10T12:00:00Z"},
            "ev_late": {"captured_at": "2026-08-25T12:00:00Z"}
        }
        # Initially present at early date, deleted by late date
        self.index.observations_by_file = {
            "ev_early": [ObservedResource("account_service", "account_1001", "ev_early", "2026-08-10T12:00:00Z", email="u1001@test.com", is_present=True)],
            "ev_late": [ObservedResource("account_service", "account_1001", "ev_late", "2026-08-25T12:00:00Z", email="u1001@test.com", is_present=False)]
        }

        auditor = DeletionAuditor(self.index, self.resolver)
        req = {"case_id": "c1001", "email": "u1001@test.com", "requested_at": "2026-08-01T10:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-08-26T12:00:00Z", "audit_at": "2026-08-30T12:00:00Z", "request_text": "Delete."}

        st, steps = auditor.audit_case(req)
        # Latest observation as of audit_at is ev_late (ABSENT), so case is COMPLETE
        self.assertEqual(st, "COMPLETE")
        acc_steps = [s for s in steps if s.system_id == "account_service"]
        self.assertEqual(len(acc_steps), 1)
        self.assertEqual(acc_steps[0].operation, "VERIFY_RECORD_ABSENT")

    def test_scenario_11_event_before_cutoff_in_post_cutoff_file(self):
        """Scenario 11: File captured after audit_at must be excluded even if inner event time is before cutoff."""
        g = UserIdentityGraph("user_1101", "User 1101", "u1101@test.com", "+11001", "hash1101")
        g.all_emails.add("u1101@test.com")
        self.resolver.graphs["u1101@test.com"] = g

        # Inner event time 2026-09-01, but file captured_at 2026-09-20 (post-cutoff 2026-09-15)
        self.index.manifest = {
            "ev_post": {"captured_at": "2026-09-20T12:00:00Z"}
        }
        self.index.observations_by_file = {
            "ev_post": [ObservedResource("support_platform", "support_leak", "ev_post", "2026-09-01T10:00:00Z", email="u1101@test.com", is_present=True, is_redacted=False)]
        }

        auditor = DeletionAuditor(self.index, self.resolver)
        req = {"case_id": "c1101", "email": "u1101@test.com", "requested_at": "2026-08-30T10:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-09-02T12:00:00Z", "audit_at": "2026-09-15T12:00:00Z", "request_text": "Delete."}

        st, steps = auditor.audit_case(req)
        # ev_post must be excluded because captured_at (2026-09-20) > audit_at (2026-09-15)
        cited_ev = {s.evidence_id for s in steps if s.evidence_id}
        self.assertNotIn("ev_post", cited_ev)

    def test_scenario_12_metamorphic_cross_user_isolation(self):
        """
        Scenario 12: Metamorphic isolation test.
        Adding unrelated evidence and activities for User B MUST NOT alter User A's status or audit steps.
        """
        gA = UserIdentityGraph("user_1201", "Alice", "alice12@test.com", "+12001", "hashA12")
        gA.all_emails.add("alice12@test.com")
        gB = UserIdentityGraph("user_1202", "Bob", "bob12@test.com", "+12002", "hashB12")
        gB.all_emails.add("bob12@test.com")
        self.resolver.graphs["alice12@test.com"] = gA
        self.resolver.graphs["bob12@test.com"] = gB

        self.index.manifest = {"ev_clean": {"captured_at": "2026-09-01T12:00:00Z"}}
        self.index.observations_by_file = {
            "ev_clean": [
                ObservedResource("account_service", "account_alice", "ev_clean", "2026-09-01T11:00:00Z", email="alice12@test.com", is_present=False),
                ObservedResource("support_platform", "support_alice", "ev_clean", "2026-09-01T11:00:00Z", email="alice12@test.com", is_present=True, is_redacted=True)
            ]
        }

        auditor = DeletionAuditor(self.index, self.resolver)
        reqA = {"case_id": "cA", "email": "alice12@test.com", "requested_at": "2026-08-30T10:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-09-01T12:00:00Z", "audit_at": "2026-09-01T12:00:00Z", "request_text": "Delete everything."}

        # Step 1: Run Alice in isolation
        st_baseline, steps_baseline = auditor.audit_case(reqA)
        baseline_dicts = [s.to_dict() for s in steps_baseline]

        # Step 2: Inject noise, activities, and observations for unrelated Bob
        self.index.manifest["ev_bob"] = {"captured_at": "2026-09-01T12:00:00Z"}
        self.index.observations_by_file["ev_bob"] = [
            ObservedResource("account_service", "account_bob", "ev_bob", "2026-09-01T11:00:00Z", email="bob12@test.com", is_present=True),
            ObservedResource("search_service", "search_bob", "ev_bob", "2026-09-01T11:00:00Z", email="bob12@test.com", is_present=True)
        ]
        self.index.activities = [
            {"activity_id": "act_bob1", "event_time": "2026-09-01T11:05:00Z", "source_system": "deletion_worker", "target_system": "account_service", "resource_id": "account_bob", "reported_result": "FAILED"},
            {"activity_id": "act_bob2", "event_time": "2026-09-01T11:06:00Z", "source_system": "deletion_worker", "target_system": "search_service", "resource_id": "search_bob", "reported_result": "SUCCESS"}
        ]

        # Step 3: Re-run Alice in the presence of Bob's noise
        st_after, steps_after = auditor.audit_case(reqA)
        after_dicts = [s.to_dict() for s in steps_after]

        # Verification: Alice's status and steps must remain 100% IDENTICAL
        self.assertEqual(st_baseline, st_after)
        self.assertEqual(len(baseline_dicts), len(after_dicts))
        for s1, s2 in zip(baseline_dicts, after_dicts):
            self.assertEqual(s1["phase"], s2["phase"])
            self.assertEqual(s1["system_id"], s2["system_id"])
            self.assertEqual(s1["resource_id"], s2["resource_id"])
            self.assertEqual(s1["operation"], s2["operation"])
            self.assertEqual(s1["state"], s2["state"])
            self.assertEqual(s1["evidence_id"], s2["evidence_id"])

if __name__ == "__main__":
    unittest.main()
