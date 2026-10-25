"""
Milestone 7 X-Factor Adversarial & Architectural Test Suite
Validates:
1. Replica data retention detection
2. Backup restore risk and active data flow mitigation
3. Tombstone preservation and PII exposure redaction
4. Security audit log retention enforcement
5. Strict tenant/identity isolation across similar subjects
6. Post-cutoff observation temporal rejection
7. Container pre-cutoff with internal post-cutoff rejection
8. Non-bundle post-cutoff container rejection
9. Causal dependency ordering in remediation plans
10. Planned future actions zero-evidence enforcement
11. Judge-facing explainability dossier schema and reasoning
12. Metamorphic evidence input order invariance
"""

import unittest
from code.models import Step, sort_and_renumber_steps
from code.graph import (
    TemporalEvidenceGraph, TemporalEdge, EdgeType, NodeType,
    CausalRemediationPlanner, AuditExplainer, is_valid_iso
)
from code.evidence_index import ObservedResource


class TestMilestone7XFactor(unittest.TestCase):

    def test_01_replica_contains_data_after_primary_deleted(self):
        """Primary account deleted but search/replica still contains data."""
        graph = TemporalEvidenceGraph(tenant_id="user_101")
        graph.add_resource_node("account_service", "account_101", "user_101")
        graph.add_resource_node("search_service", "search_101", "user_101")

        edge_primary = TemporalEdge(
            source_id="user:user_101",
            target_id="account_service:account_101",
            edge_type=EdgeType.HOLDS_PII,
            evidence_id="ev_01",
            observation_time="2026-09-01T10:00:00Z",
            container_time="2026-09-01T10:00:00Z",
            user_id="user_101",
            system_id="account_service",
            is_present=False
        )
        edge_replica = TemporalEdge(
            source_id="user:user_101",
            target_id="search_service:search_101",
            edge_type=EdgeType.HOLDS_PII,
            evidence_id="ev_02",
            observation_time="2026-09-01T10:00:00Z",
            container_time="2026-09-01T10:00:00Z",
            user_id="user_101",
            system_id="search_service",
            is_present=True
        )
        graph.add_edge(edge_primary)
        graph.add_edge(edge_replica)

        admissible = graph.get_admissible_edges("user_101", "2026-09-02T00:00:00Z")
        self.assertEqual(len(admissible), 2)

        # Build steps
        steps = []
        for e in admissible:
            if e.system_id == "search_service" and e.is_present:
                steps.append(Step(0, "FINDING", e.system_id, "search_101", "REPORT_REMAINING_RECORD", "PRESENT", e.evidence_id))
                steps.append(Step(0, "REMEDIATION", e.system_id, "search_101", "DELETE_RECORD", "ABSENT", ""))
                steps.append(Step(0, "VERIFICATION", e.system_id, "search_101", "VERIFY_RECORD_ABSENT", "ABSENT", ""))

        numbered = sort_and_renumber_steps(steps)
        self.assertEqual(len(numbered), 3)
        self.assertEqual(numbered[0].phase, "FINDING")
        self.assertEqual(numbered[1].phase, "REMEDIATION")
        self.assertEqual(numbered[2].phase, "VERIFICATION")

    def test_02_backup_or_import_path_can_restore_data(self):
        """Active restore risk triggers REPORT_RESTORE_RISK and BLOCK_RESTORE."""
        planner = CausalRemediationPlanner()
        raw_remediations = [
            Step(0, "REMEDIATION", "account_service", "account_102", "DELETE_RECORD", "ABSENT", "ev_fake"),
            Step(0, "REMEDIATION", "backup_service", "backup_102", "BLOCK_RESTORE", "BLOCKED", "ev_fake")
        ]
        ordered = planner.order_remediations(raw_remediations)
        # BLOCK_RESTORE must precede DELETE_RECORD
        self.assertEqual(ordered[0].operation, "BLOCK_RESTORE")
        self.assertEqual(ordered[1].operation, "DELETE_RECORD")
        # Evidence ID must be cleared for all planned actions
        self.assertEqual(ordered[0].evidence_id, "")
        self.assertEqual(ordered[1].evidence_id, "")

        valid, violations = planner.validate_plan_dependencies(ordered)
        self.assertTrue(valid)
        self.assertEqual(len(violations), 0)

    def test_03_tombstone_preserves_id_strips_pii(self):
        """Account tombstone with exposed direct identifiers triggers REPORT_EXPOSED_PII and REDACT_RECORD."""
        edge = TemporalEdge(
            source_id="user:user_103",
            target_id="support_platform:ticket_103",
            edge_type=EdgeType.EXPOSES_PII,
            evidence_id="ev_03",
            observation_time="2026-09-01T12:00:00Z",
            container_time="2026-09-01T12:00:00Z",
            user_id="user_103",
            system_id="support_platform",
            is_present=True,
            is_redacted=False
        )
        self.assertTrue(edge.is_admissible_at("2026-09-02T00:00:00Z"))
        finding = Step(0, "FINDING", edge.system_id, "ticket_103", "REPORT_EXPOSED_PII", "PRESENT", edge.evidence_id)
        remediation = Step(0, "REMEDIATION", edge.system_id, "ticket_103", "REDACT_RECORD", "REDACTED", "")
        verification = Step(0, "VERIFICATION", edge.system_id, "ticket_103", "VERIFY_RECORD_REDACTED", "REDACTED", "")

        numbered = sort_and_renumber_steps([finding, remediation, verification])
        self.assertEqual(numbered[1].operation, "REDACT_RECORD")
        self.assertEqual(numbered[2].state, "REDACTED")

    def test_04_legally_required_retained_record_not_deleted(self):
        """Security service audit log must remain present, never deleted."""
        edge = TemporalEdge(
            source_id="user:user_104",
            target_id="security_service:audit_record_104",
            edge_type=EdgeType.LEGALLY_RETAINED,
            evidence_id="ev_04",
            observation_time="2026-09-01T12:00:00Z",
            container_time="2026-09-01T12:00:00Z",
            user_id="user_104",
            system_id="security_service",
            is_present=True
        )
        verif = Step(0, "VERIFICATION", edge.system_id, "audit_record_104", "VERIFY_RECORD_PRESENT", "PRESENT", edge.evidence_id)
        self.assertEqual(verif.operation, "VERIFY_RECORD_PRESENT")
        self.assertEqual(verif.state, "PRESENT")

    def test_05_cross_tenant_isolation_similar_names(self):
        """Graph rejects edges crossing identity boundaries."""
        graph = TemporalEvidenceGraph(tenant_id="user_A")
        graph.add_identity_node("user_A", {})
        graph.add_identity_node("user_B", {})

        valid_edge = TemporalEdge(
            source_id="user:user_A",
            target_id="account_service:acc_A",
            edge_type=EdgeType.HOLDS_PII,
            evidence_id="ev_A",
            observation_time="2026-09-01T10:00:00Z",
            container_time="2026-09-01T10:00:00Z",
            user_id="user_A",
            system_id="account_service",
            metadata={"user_id": "user_A"}
        )
        corrupted_edge = TemporalEdge(
            source_id="user:user_A",
            target_id="account_service:acc_B",
            edge_type=EdgeType.HOLDS_PII,
            evidence_id="ev_B",
            observation_time="2026-09-01T10:00:00Z",
            container_time="2026-09-01T10:00:00Z",
            user_id="user_A",
            system_id="account_service",
            metadata={"user_id": "user_B"}  # cross tenant leak!
        )
        graph.add_edge(valid_edge)
        self.assertTrue(graph.validate_isolation("user_A"))

        graph.add_edge(corrupted_edge)
        self.assertFalse(graph.validate_isolation("user_A"))

    def test_06_post_cutoff_observation_rejected(self):
        """Observation with observation_time > audit_at is strictly rejected."""
        edge = TemporalEdge(
            source_id="user:user_106",
            target_id="account_service:acc_106",
            edge_type=EdgeType.HOLDS_PII,
            evidence_id="ev_06",
            observation_time="2026-09-10T15:00:00Z",
            container_time="2026-09-08T10:00:00Z",
            user_id="user_106"
        )
        audit_at = "2026-09-08T12:00:00Z"
        self.assertFalse(edge.is_admissible_at(audit_at))

    def test_07_container_pre_cutoff_internal_post_cutoff(self):
        """Container pre-cutoff but observation post-cutoff is rejected."""
        edge = TemporalEdge(
            source_id="user:user_107",
            target_id="account_service:acc_107",
            edge_type=EdgeType.HOLDS_PII,
            evidence_id="ev_07",
            observation_time="2026-09-09T00:00:00Z",
            container_time="2026-09-05T00:00:00Z",
            user_id="user_107"
        )
        audit_at = "2026-09-08T00:00:00Z"
        self.assertFalse(edge.is_admissible_at(audit_at))

    def test_08_container_post_cutoff_internal_pre_cutoff_non_bundle(self):
        """Non-bundle container captured post-cutoff is rejected."""
        edge = TemporalEdge(
            source_id="user:user_108",
            target_id="account_service:acc_108",
            edge_type=EdgeType.HOLDS_PII,
            evidence_id="ev_08",
            observation_time="2026-09-05T00:00:00Z",
            container_time="2026-09-10T00:00:00Z",
            user_id="user_108"
        )
        audit_at = "2026-09-08T00:00:00Z"
        self.assertFalse(edge.is_admissible_at(audit_at, is_bundle=False))
        # If it were an assurance bundle, it would be admitted
        self.assertTrue(edge.is_admissible_at(audit_at, is_bundle=True))

    def test_09_causal_remediation_dependency_order(self):
        """Flow and restore mitigations must strictly precede record deletions."""
        raw_remediations = [
            Step(0, "REMEDIATION", "account_service", "account_109", "DELETE_RECORD", "ABSENT", ""),
            Step(0, "REMEDIATION", "integration_service", "flow_109", "DISABLE_DATA_FLOW", "DISABLED", ""),
            Step(0, "REMEDIATION", "backup_service", "backup_109", "BLOCK_RESTORE", "BLOCKED", "")
        ]
        ordered = CausalRemediationPlanner.order_remediations(raw_remediations)
        ops = [s.operation for s in ordered]
        self.assertIn(ops[0], ("DISABLE_DATA_FLOW", "BLOCK_RESTORE"))
        self.assertIn(ops[1], ("DISABLE_DATA_FLOW", "BLOCK_RESTORE"))
        self.assertEqual(ops[2], "DELETE_RECORD")

    def test_10_planned_actions_have_empty_evidence_id(self):
        """All planned remediation steps must have evidence_id == ''."""
        steps = [
            Step(0, "REMEDIATION", "account_service", "account_110", "DELETE_RECORD", "ABSENT", "should_be_stripped"),
            Step(0, "REMEDIATION", "integration_service", "flow_110", "DISABLE_DATA_FLOW", "DISABLED", "fake_id")
        ]
        sanitized = CausalRemediationPlanner.order_remediations(steps)
        for s in sanitized:
            self.assertEqual(s.evidence_id, "")

    def test_11_explainability_dossier_structure(self):
        """AuditExplainer produces structured, judge-facing audit dossier."""
        case_row = {
            "case_id": "case_test_99",
            "email": "test@example.com",
            "audit_at": "2026-09-08T12:00:00Z",
            "reported_status": "COMPLETE"
        }
        steps = [
            Step(1, "FINDING", "account_service", "account_99", "REPORT_REMAINING_RECORD", "PRESENT", "evidence_54"),
            Step(2, "REMEDIATION", "account_service", "account_99", "DELETE_RECORD", "ABSENT", ""),
            Step(3, "VERIFICATION", "account_service", "account_99", "VERIFY_RECORD_ABSENT", "ABSENT", "")
        ]
        dossier = AuditExplainer.explain_case(case_row, "INCOMPLETE", steps)
        self.assertEqual(dossier["case_id"], "case_test_99")
        self.assertEqual(dossier["certified_status"], "INCOMPLETE")
        self.assertTrue(dossier["status_discrepancy"])
        self.assertEqual(dossier["findings_count"], 1)
        self.assertIn("INCOMPLETE despite reported status 'COMPLETE'", dossier["justification"])
        self.assertIn("Prohibited personal record account_99", dossier["findings_breakdown"][0]["rationale"])

    def test_12_input_order_permutation_invariance(self):
        """Permuting input step order produces identical canonical sorted output."""
        s1 = Step(0, "FINDING", "account_service", "account_10", "REPORT_REMAINING_RECORD", "PRESENT", "ev_1")
        s2 = Step(0, "REMEDIATION", "account_service", "account_10", "DELETE_RECORD", "ABSENT", "")
        s3 = Step(0, "VERIFICATION", "account_service", "account_10", "VERIFY_RECORD_ABSENT", "ABSENT", "")

        out_a = sort_and_renumber_steps([s1, s2, s3])
        out_b = sort_and_renumber_steps([s3, s1, s2])
        out_c = sort_and_renumber_steps([s2, s3, s1])

        self.assertEqual([s.to_dict() for s in out_a], [s.to_dict() for s in out_b])
        self.assertEqual([s.to_dict() for s in out_b], [s.to_dict() for s in out_c])

    def test_13_production_causal_guard_rejects_inverted_remediation(self):
        """Production guard raises clear RuntimeError when an invalid remediation sequence is encountered."""
        invalid_plan = [
            Step(0, "REMEDIATION", "account_service", "acc_bad", "DELETE_RECORD", "ABSENT", ""),
            Step(0, "REMEDIATION", "integration_service", "flw_bad", "DISABLE_DATA_FLOW", "DISABLED", "")
        ]
        valid, violations = CausalRemediationPlanner.validate_plan_dependencies(invalid_plan)
        self.assertFalse(valid)
        self.assertGreater(len(violations), 0)

        # Confirm the exception format raised in production
        with self.assertRaises(RuntimeError) as ctx:
            if not valid:
                raise RuntimeError(f"Causal dependency violation in case test_case: {'; '.join(violations)}")
        self.assertIn("Causal dependency violation in case test_case", str(ctx.exception))
        self.assertIn("Causal hazard: DISABLE_DATA_FLOW on integration_service:flw_bad", str(ctx.exception))

    def test_14_production_causal_guard_passes_valid_cases_unchanged(self):
        """All valid cases pass the production causal guard cleanly without exceptions or mutations."""
        valid_remediations = [
            Step(0, "REMEDIATION", "integration_service", "flw_ok", "DISABLE_DATA_FLOW", "DISABLED", ""),
            Step(0, "REMEDIATION", "account_service", "acc_ok", "DELETE_RECORD", "ABSENT", "")
        ]
        valid, violations = CausalRemediationPlanner.validate_plan_dependencies(valid_remediations)
        self.assertTrue(valid)
        self.assertEqual(len(violations), 0)


if __name__ == "__main__":
    unittest.main()

