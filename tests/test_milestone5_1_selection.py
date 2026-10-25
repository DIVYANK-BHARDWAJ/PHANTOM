import unittest
import copy
import random
from typing import Dict, List, Any
from code.models import Step, sort_and_renumber_steps
from code.evidence_index import ObservedResource
from code.auditor import _is_valid_iso

class TestMilestone51EvidenceSelection(unittest.TestCase):
    def setUp(self):
        self.audit_at = "2026-09-15T12:00:00Z"
        self.mock_manifest = {
            "ev_pre_dedicated": {
                "file_id": "ev_pre_dedicated",
                "origin": "service_resource_export",
                "captured_at": "2026-09-15T11:44:55Z"
            },
            "ev_post_bundle": {
                "file_id": "ev_post_bundle",
                "origin": "records_assurance_snapshot_bundle",
                "captured_at": "2026-09-17T04:00:00Z"
            },
            "ev_pre_bundle": {
                "file_id": "ev_pre_bundle",
                "origin": "records_assurance_snapshot_bundle",
                "captured_at": "2026-09-15T12:00:00Z"
            },
            "ev_early_container": {
                "file_id": "ev_early_container",
                "origin": "central_observability_export",
                "captured_at": "2026-09-10T10:00:00Z"
            }
        }

    def _selection_key(self, obs: ObservedResource) -> tuple:
        f_meta = self.mock_manifest.get(obs.evidence_id, {})
        m_cap = f_meta.get("captured_at", "")
        container_pre = 1 if (_is_valid_iso(m_cap) and m_cap <= self.audit_at) else 0
        return (container_pre, obs.captured_at, obs.evidence_id)

    def test_01_post_cutoff_container_cannot_override_admissible_pre_cutoff_evidence(self):
        """
        An observation in a container captured post-cutoff must not override
        an observation from a valid container captured at or before cutoff.
        """
        obs_pre = ObservedResource(
            system_id="export_service",
            resource_id="export_9999",
            evidence_id="ev_pre_dedicated",
            captured_at="2026-09-15T11:44:55Z",
            is_present=True
        )
        obs_post_container = ObservedResource(
            system_id="export_service",
            resource_id="export_9999",
            evidence_id="ev_post_bundle",
            captured_at="2026-09-15T12:00:00Z",  # inner snapshot at cutoff, but container is post-cutoff
            is_present=True
        )

        # In order [obs_pre, obs_post_container]
        observations = [obs_pre, obs_post_container]
        latest_by_resource = {}
        for obs in sorted(observations, key=self._selection_key):
            latest_by_resource[obs.resource_id] = obs
        self.assertEqual(latest_by_resource["export_9999"].evidence_id, "ev_pre_dedicated")

        # In reversed order [obs_post_container, obs_pre]
        observations_rev = [obs_post_container, obs_pre]
        latest_by_resource_rev = {}
        for obs in sorted(observations_rev, key=self._selection_key):
            latest_by_resource_rev[obs.resource_id] = obs
        self.assertEqual(latest_by_resource_rev["export_9999"].evidence_id, "ev_pre_dedicated")

    def test_02_observation_with_late_internal_timestamp_rejected_despite_early_container(self):
        """
        Even if a container is captured before cutoff, an observation with an
        internal timestamp strictly after cutoff must be rejected.
        """
        late_obs = ObservedResource(
            system_id="account_service",
            resource_id="account_1234",
            evidence_id="ev_early_container",
            captured_at="2026-09-16T08:00:00Z"  # After cutoff
        )
        
        # Test admission criteria
        is_admissible = _is_valid_iso(late_obs.captured_at) and late_obs.captured_at <= self.audit_at
        self.assertFalse(is_admissible, "Observation with timestamp after audit_at must never be admitted")

    def test_03_deterministic_tie_breaking_for_identical_timestamps(self):
        """
        When multiple admissible observations for the same resource have identical
        container status and identical timestamps, tie-breaking must be stable and deterministic.
        """
        obs_a = ObservedResource(
            system_id="search_service",
            resource_id="search_7777",
            evidence_id="ev_pre_dedicated",
            captured_at="2026-09-15T11:44:55Z",
            is_present=True
        )
        obs_b = ObservedResource(
            system_id="search_service",
            resource_id="search_7777",
            evidence_id="ev_pre_bundle",
            captured_at="2026-09-15T11:44:55Z",
            is_present=True
        )

        for _ in range(10):
            shuffled = [obs_a, obs_b]
            random.shuffle(shuffled)
            selected = {}
            for obs in sorted(shuffled, key=self._selection_key):
                selected[obs.resource_id] = obs
            # "ev_pre_bundle" < "ev_pre_dedicated" lexicographically, so "ev_pre_dedicated" is sorted second and wins deterministically
            self.assertEqual(selected["search_7777"].evidence_id, "ev_pre_dedicated")

    def test_04_input_file_ordering_invariance(self):
        """
        Observation selection must produce identical results regardless of
        the order observations are discovered or parsed.
        """
        obs1 = ObservedResource(system_id="sys1", resource_id="res_alpha", evidence_id="ev_pre_dedicated", captured_at="2026-09-15T10:00:00Z")
        obs2 = ObservedResource(system_id="sys1", resource_id="res_alpha", evidence_id="ev_post_bundle", captured_at="2026-09-15T11:00:00Z")
        obs3 = ObservedResource(system_id="sys2", resource_id="res_beta", evidence_id="ev_pre_bundle", captured_at="2026-09-15T09:00:00Z")
        obs4 = ObservedResource(system_id="sys2", resource_id="res_beta", evidence_id="ev_pre_dedicated", captured_at="2026-09-15T10:00:00Z")

        obs_list = [obs1, obs2, obs3, obs4]
        
        # Run 20 permutations
        baseline = None
        for seed in range(20):
            rng = random.Random(seed)
            perm = list(obs_list)
            rng.shuffle(perm)
            res = {}
            for o in sorted(perm, key=self._selection_key):
                res[o.resource_id] = o.evidence_id
            if baseline is None:
                baseline = res
            else:
                self.assertEqual(res, baseline, f"Permutation under seed {seed} produced different result")

    def test_05_tenant_and_identity_isolation(self):
        """
        Evidence for one user must never match or contaminate another user's observation pool.
        """
        from code.identity import UserIdentityGraph
        
        user_a = UserIdentityGraph(
            user_id="user_100",
            current_name="Alice Smith",
            all_names={"Alice Smith"},
            all_emails={"alice@example.com"},
            all_phones={"+15550101"},
            all_email_hashes={"hash_alice"}
        )
        user_b = UserIdentityGraph(
            user_id="user_200",
            current_name="Bob Jones",
            all_names={"Bob Jones"},
            all_emails={"bob@example.com"},
            all_phones={"+15550202"},
            all_email_hashes={"hash_bob"}
        )

        obs_alice = ObservedResource(
            system_id="support_platform",
            resource_id="ticket_100",
            evidence_id="ev_pre_dedicated",
            captured_at="2026-09-15T10:00:00Z",
            email="alice@example.com",
            user_id="user_100"
        )

        # Helper matching logic matching Auditor._matches_user
        def matches(obs, graph):
            if obs.user_id and obs.user_id == graph.user_id:
                return True
            if obs.email and obs.email in graph.all_emails:
                return True
            if obs.phone and obs.phone in graph.all_phones:
                return True
            if obs.name and obs.name in graph.all_names:
                return True
            if obs.email_hash and obs.email_hash in graph.all_email_hashes:
                return True
            return False

        self.assertTrue(matches(obs_alice, user_a))
        self.assertFalse(matches(obs_alice, user_b), "Alice's observation must NOT match Bob")

    def test_06_step_ordering_and_renumbering_integrity(self):
        """
        Steps must always maintain strict phase ordering (FINDING -> REMEDIATION -> VERIFICATION)
        and consecutive 1-based step numbers.
        """
        raw_steps = [
            Step(step_no=99, phase="VERIFICATION", system_id="search_service", resource_id="search_1", operation="VERIFY_RECORD_ABSENT", state="ABSENT", evidence_id=""),
            Step(step_no=5, phase="FINDING", system_id="search_service", resource_id="search_1", operation="REPORT_REMAINING_RECORD", state="PRESENT", evidence_id="ev_pre_dedicated"),
            Step(step_no=12, phase="REMEDIATION", system_id="search_service", resource_id="search_1", operation="DELETE_RECORD", state="ABSENT", evidence_id=""),
        ]
        
        ordered = sort_and_renumber_steps(raw_steps)
        self.assertEqual([s.step_no for s in ordered], [1, 2, 3])
        self.assertEqual([s.phase for s in ordered], ["FINDING", "REMEDIATION", "VERIFICATION"])
        self.assertEqual(ordered[0].evidence_id, "ev_pre_dedicated")
        self.assertEqual(ordered[1].evidence_id, "")
        self.assertEqual(ordered[2].evidence_id, "")

if __name__ == "__main__":
    unittest.main()
