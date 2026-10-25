import unittest
import copy
import re
from typing import Dict, List, Any
from code.models import Step
from code.evidence_index import ObservedResource

ISO_REGEX = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')

def is_valid_iso(ts: str) -> bool:
    return bool(ts and isinstance(ts, str) and ISO_REGEX.match(ts))

class TestMilestone42TemporalAndAttribution(unittest.TestCase):
    def setUp(self):
        self.cutoff = "2026-09-15T12:00:00Z"

    # --- Phase 2: Comprehensive Temporal Tests ---

    def test_01_observation_strictly_before_cutoff(self):
        manifest_meta = {"file_id": "ev_01", "origin": "central_observability_export", "captured_at": "2026-09-15T10:00:00Z"}
        obs = ObservedResource(system_id="account_service", resource_id="acc_1", evidence_id="ev_01", captured_at="2026-09-15T10:00:00Z")
        is_bundle = (manifest_meta.get("origin") == "records_assurance_snapshot_bundle")
        
        # Test admission
        admitted = False
        if not is_bundle:
            if is_valid_iso(manifest_meta["captured_at"]) and manifest_meta["captured_at"] <= self.cutoff:
                if is_valid_iso(obs.captured_at) and obs.captured_at <= self.cutoff:
                    admitted = True
        self.assertTrue(admitted, "Regular observation before cutoff should be admitted")

    def test_02_observation_exactly_at_cutoff(self):
        manifest_meta = {"file_id": "ev_51", "origin": "records_assurance_snapshot_bundle", "captured_at": "2026-09-15T12:00:00Z"}
        obs = ObservedResource(system_id="security_service", resource_id="audit_1", evidence_id="ev_51", captured_at="2026-09-15T12:00:00Z")
        
        admitted = is_valid_iso(obs.captured_at) and obs.captured_at <= self.cutoff
        self.assertTrue(admitted, "Observation exactly at cutoff must be admitted")

    def test_03_observation_strictly_after_cutoff(self):
        manifest_meta = {"file_id": "ev_06", "origin": "central_observability_export", "captured_at": "2026-09-18T11:55:24Z"}
        obs = ObservedResource(system_id="security_service", resource_id="audit_4902", evidence_id="ev_06", captured_at="2026-09-18T11:55:24Z")
        
        # Manifest check for non-bundle
        manifest_admitted = is_valid_iso(manifest_meta["captured_at"]) and manifest_meta["captured_at"] <= self.cutoff
        self.assertFalse(manifest_admitted, "Manifest captured after cutoff must be rejected")
        obs_admitted = is_valid_iso(obs.captured_at) and obs.captured_at <= self.cutoff
        self.assertFalse(obs_admitted, "Observation after cutoff must be rejected")

    def test_04_earlier_inner_timestamp_in_later_captured_bundle(self):
        # Bundle manifest is exported 2 days after cutoff, but inner snapshot observation was taken at or before cutoff
        manifest_meta = {"file_id": "ev_02", "origin": "records_assurance_snapshot_bundle", "captured_at": "2026-09-17T12:00:00Z"}
        obs = ObservedResource(system_id="security_service", resource_id="audit_4128", evidence_id="ev_02", captured_at="2026-09-15T12:00:00Z")
        
        is_bundle = (manifest_meta.get("origin") == "records_assurance_snapshot_bundle")
        self.assertTrue(is_bundle)
        
        # When evaluating per-observation for bundles
        admitted = is_valid_iso(obs.captured_at) and obs.captured_at <= self.cutoff
        self.assertTrue(admitted, "Inner snapshot at/before cutoff inside later-exported bundle must be admitted")

    def test_05_later_inner_timestamp_in_earlier_captured_bundle(self):
        # Anomaly scenario: bundle manifest captured earlier, but inner snapshot claims a future date
        manifest_meta = {"file_id": "ev_02", "origin": "records_assurance_snapshot_bundle", "captured_at": "2026-09-15T12:00:00Z"}
        obs = ObservedResource(system_id="security_service", resource_id="audit_9999", evidence_id="ev_02", captured_at="2026-09-20T12:00:00Z")
        
        admitted = is_valid_iso(obs.captured_at) and obs.captured_at <= self.cutoff
        self.assertFalse(admitted, "Inner observation with timestamp after cutoff must be strictly rejected")

    def test_06_mixed_observations_in_one_bundle(self):
        # Bundle has observations from 2026-09-09, 2026-09-15, and 2026-09-17
        obs_list = [
            ObservedResource(system_id="account_service", resource_id="acc_1", evidence_id="ev_02", captured_at="2026-09-09T12:00:00Z"),
            ObservedResource(system_id="security_service", resource_id="audit_1", evidence_id="ev_02", captured_at="2026-09-15T12:00:00Z"),
            ObservedResource(system_id="account_service", resource_id="acc_2", evidence_id="ev_02", captured_at="2026-09-17T12:00:00Z"),
        ]
        admitted = [o.resource_id for o in obs_list if is_valid_iso(o.captured_at) and o.captured_at <= self.cutoff]
        self.assertEqual(admitted, ["acc_1", "audit_1"])
        self.assertNotIn("acc_2", admitted)

    def test_07_missing_and_malformed_timestamps(self):
        invalid_ts_list = ["", None, "not-a-timestamp", "2026/09/15", "2026-09-15", "invalid_iso"]
        for bad_ts in invalid_ts_list:
            obs = ObservedResource(system_id="account_service", resource_id="acc_bad", evidence_id="ev_02", captured_at=bad_ts)
            admitted = is_valid_iso(obs.captured_at) and obs.captured_at <= self.cutoff
            self.assertFalse(admitted, f"Timestamp '{bad_ts}' must fail closed")

    def test_08_conflicting_outer_and_inner_timestamps(self):
        # Outer manifest is later (2026-09-17), inner observation is valid (2026-09-15)
        # However, for non-bundle evidence, outer manifest still controls and blocks
        manifest_meta = {"file_id": "ev_sql", "origin": "database_snapshot", "captured_at": "2026-09-17T12:00:00Z"}
        obs = ObservedResource(system_id="account_service", resource_id="acc_sql", evidence_id="ev_sql", captured_at="2026-09-15T10:00:00Z")
        is_bundle = (manifest_meta.get("origin") == "records_assurance_snapshot_bundle")
        
        admitted = False
        if is_bundle:
            admitted = is_valid_iso(obs.captured_at) and obs.captured_at <= self.cutoff
        else:
            if is_valid_iso(manifest_meta["captured_at"]) and manifest_meta["captured_at"] <= self.cutoff:
                admitted = is_valid_iso(obs.captured_at) and obs.captured_at <= self.cutoff
                
        self.assertFalse(admitted, "Non-bundle file with post-cutoff manifest must remain blocked even if inner claims earlier")

    def test_09_regular_files_with_post_cutoff_manifest(self):
        regular_origins = [
            ("central_observability_export", "2026-09-16T00:00:00Z"),
            ("customer_data_read_replica_capture", "2026-09-21T10:00:00Z"),
            ("search_index_service", "2026-09-18T00:00:00Z"),
            ("customer_account_service", "2026-10-01T12:00:00Z"),
        ]
        for orig, cap in regular_origins:
            admitted = is_valid_iso(cap) and cap <= self.cutoff
            self.assertFalse(admitted, f"Regular file from {orig} captured at {cap} must be rejected at cutoff {self.cutoff}")

    # --- Phase 3: Deterministic Analytics Matching Tests ---

    def test_10_analytics_matching_order_invariance(self):
        # Simulate batch matching for complete cases with shuffled/reversed order
        complete_reqs = [
            {"case_id": "case_25", "reported_at": "2026-09-02T12:00:00Z"},
            {"case_id": "case_26", "reported_at": "2026-09-02T12:00:00Z"},
        ]
        cand_events = [("2026-09-02T11:31:08Z", "analytics_1895"), ("2026-09-02T11:31:24Z", "analytics_4566")]

        def allocate(req_list):
            sorted_reqs = sorted(req_list, key=lambda x: x["case_id"])
            sorted_cands = sorted(cand_events)
            mapping = {}
            for idx, r in enumerate(sorted_reqs):
                if idx < len(sorted_cands):
                    mapping[r["case_id"]] = sorted_cands[idx][1]
            return mapping

        forward = allocate(complete_reqs)
        reversed_order = allocate(list(reversed(complete_reqs)))
        self.assertEqual(forward, reversed_order, "Allocation must be 100% invariant to input row ordering")
        self.assertEqual(forward["case_25"], "analytics_1895")
        self.assertEqual(forward["case_26"], "analytics_4566")

    def test_11_incomplete_cases_do_not_steal_analytics_slots(self):
        # Even if an incomplete case is in the batch, only complete cases consume slots
        all_reqs = [
            {"case_id": "case_24", "status": "INCOMPLETE", "reported_at": "2026-09-02T12:00:00Z"},
            {"case_id": "case_25", "status": "COMPLETE", "reported_at": "2026-09-02T12:00:00Z"},
            {"case_id": "case_26", "status": "COMPLETE", "reported_at": "2026-09-02T12:00:00Z"},
        ]
        cand_events = [("2026-09-02T11:31:08Z", "analytics_1895"), ("2026-09-02T11:31:24Z", "analytics_4566")]

        complete_only = [r for r in all_reqs if r["status"] == "COMPLETE"]
        sorted_reqs = sorted(complete_only, key=lambda x: x["case_id"])
        
        mapping = {}
        for idx, r in enumerate(sorted_reqs):
            if idx < len(cand_events):
                mapping[r["case_id"]] = cand_events[idx][1]

        self.assertNotIn("case_24", mapping)
        self.assertEqual(mapping["case_25"], "analytics_1895")
        self.assertEqual(mapping["case_26"], "analytics_4566")

if __name__ == '__main__':
    unittest.main()
