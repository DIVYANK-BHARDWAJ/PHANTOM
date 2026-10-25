# Milestone 7 X-Factor Engineering Sprint Report — PHANTOM

**Project:** HackerRank Orchestrate (October 2026) — *Ghost Data Still Exists*  
**Date:** 2026-10-25  
**Harness / Coding Agent:** Antigravity  
**Model:** Gemini 3.8 Flash (Medium)  
**Status:** COMPLETE — GO RECOMMENDATION  

---

## 1. X-Factor Feature Matrix

An architectural audit of PHANTOM evaluated the system against the six target capabilities:

| Capability | Initial State | Post-Sprint State | Architectural Implementation & Evidence |
|---|---|---|---|
| **A. Temporal Evidence Graph** | **PARTIAL** (Flat observation dictionary `latest_by_resource`) | **EXISTING & FORMALIZED** | Implemented `TemporalEvidenceGraph` with typed nodes (`IDENTITY`, `RESOURCE`, `FLOW_RISK`, `EVIDENCE`) and typed directional edges (`HOLDS_PII`, `REPLICATES_TO`, `RESTORE_RISK`, `ACTIVE_DATA_FLOW`, `EXPOSES_PII`, `LEGALLY_RETAINED`, `ACCOUNT_TOMBSTONE`, `SUPPORTED_BY`). Tracks observation vs container capture timestamps with strict cutoff checking. |
| **B. Causal Remediation Planner** | **PARTIAL** (Static operation enumeration ordering) | **EXISTING & TESTED** | Implemented `CausalRemediationPlanner` with explicit dependency level enforcement (Level 1: `DISABLE_DATA_FLOW`, `BLOCK_RESTORE` $\to$ Level 2: `DELETE_RECORD`, `REDACT_RECORD`, `ANONYMIZE_RECORD`). Enforces topological plan validation and zero evidence citations (`evidence_id=""`) on future actions. |
| **C. Evidence-Backed Citations** | **EXISTING** (100% admissible) | **EXISTING & GROUNDED** | Every material finding and completed verification cites an admissible participant-visible evidence ID (`file_id`, `activity_id`, `audit_id`) captured at or before `audit_at`. Zero fabricated IDs across 518 cases. |
| **D. Bounded Investigator** | **PARTIAL** (Single-pass index lookup) | **PARTIAL** | Upfront indexing across 94 multi-modal files with deterministic lookup and temporal bounds. Multi-turn interactive retrieval was evaluated but deemed high-risk for determinism and latency within the 5-hour sprint budget. |
| **E. Deterministic Core + Selective LLM** | **EXISTING** (Deterministic Python core) | **EXISTING & VERIFIED** | Deterministic Python remains 100% authoritative for identity facts, temporal eligibility, deletion policy, step ordering, schema validation, and final output. Zero fabricated LLM calls or unvetted external cloud dependencies. |
| **F. Judge-Facing Explainability** | **MISSING** (Raw status & step tuples only) | **EXISTING & OPERATIONAL** | Implemented `AuditExplainer` and CLI flag `--explain <case_id>`. Generates structured audit dossiers detailing intent authorization, resolved identity aliases, temporal evidence filtering, causal breakdown of findings, remediation rationale, and required evidence to reach COMPLETE status. |

---

## 2. Top Gaps Discovered

1. **Absence of an Explicit Entity-Relationship Representation (Gap A):**
   - Observations across SQL replicas, support attachments, and activity logs were previously merged into a flat dictionary `latest_by_resource: Dict[str, ObservedResource]`. While effective for matching, it did not explicitly represent the causal and temporal relationships between user identities, downstream replicas, and restoration risks.
2. **Implicit vs Explicit Remediation Dependency Ordering (Gap B):**
   - Remediation ordering previously relied solely on static array sorting in `models.py`. If a complex case required disabling an active data flow before deleting downstream replicas, the system lacked a topological validator to guarantee no destructive action preceded propagation cutoff.
3. **Black-Box Audit Output for Evaluators and Judges (Gap F):**
   - The engine produced exact CSV rows with serialized JSON steps, but provided no human-readable or judge-facing explanation of *why* an audit failed, *why* certain evidence was excluded, or *what* remediation actions were causally required.

---

## 3. Files Changed and Implementation Details

### 1. `code/graph.py` (New Module)
- **`TemporalEvidenceGraph`**:
  - Maintains typed `GraphNode` and `TemporalEdge` structures.
  - Implements `is_admissible_at(audit_at, is_bundle)` which strictly evaluates whether both inner observation timestamps and outer container capture timestamps satisfy the historical cutoff.
  - Implements `validate_isolation(user_id)` to guarantee zero cross-tenant contamination.
- **`CausalRemediationPlanner`**:
  - Classifies operations into dependency hierarchies:
    - Level 1: `DISABLE_DATA_FLOW`, `BLOCK_RESTORE`
    - Level 2: `DELETE_RECORD`, `REDACT_RECORD`, `ANONYMIZE_RECORD`
  - Strips evidence citations from all planned remediation and future verification steps (`evidence_id=""`).
  - Provides `validate_plan_dependencies(steps)` to formally detect any causal ordering violations.
- **`AuditExplainer`**:
  - Generates comprehensive structured dossiers explaining status decisions, policy violations, and remediation requirements.

### 2. `code/auditor.py`
- Integrated `TemporalEvidenceGraph` and `CausalRemediationPlanner` into `audit_case()`.
- Added `explain_case(case_row)` method providing on-demand audit explanations for any case.
- Preserved 100% backward compatibility with all baseline matching and batch correlation logic.

### 3. `code/main.py`
- Added `--explain <case_id>` argument to the CLI:
  ```bash
  python code/main.py --requests dataset/sample_deletion_requests.csv --explain case_05
  ```
- Emits structured JSON explaining the audit verdict, evidence provenance, and policy justification.

### 4. `tests/test_milestone7_xfactor.py` (New Test Suite)
- Added 12 rigorous adversarial and architectural unit tests.

---

## 4. Tests Added and Results

A dedicated test suite `tests/test_milestone7_xfactor.py` was created containing 12 unit tests:

1. `test_01_replica_contains_data_after_primary_deleted`: Validates replica detection when primary account is gone.
2. `test_02_backup_or_import_path_can_restore_data`: Validates backup restore risk detection and priority ordering.
3. `test_03_tombstone_preserves_id_strips_pii`: Validates PII redaction while maintaining tombstone user ID.
4. `test_04_legally_required_retained_record_not_deleted`: Validates preservation of security service audit records.
5. `test_05_cross_tenant_isolation_similar_names`: Validates graph isolation when users have overlapping names.
6. `test_06_post_cutoff_observation_rejected`: Validates rejection of observations with `captured_at > audit_at`.
7. `test_07_container_pre_cutoff_internal_post_cutoff`: Validates rejection when observation postdates cutoff.
8. `test_08_container_post_cutoff_internal_pre_cutoff_non_bundle`: Validates container cutoff enforcement for non-bundles.
9. `test_09_causal_remediation_dependency_order`: Validates that flow/restore cutoffs precede record deletions.
10. `test_10_planned_actions_have_empty_evidence_id`: Validates that planned future actions have `evidence_id == ""`.
11. `test_11_explainability_dossier_structure`: Validates schema and fields of judge-facing explainability dossiers.
12. `test_12_input_order_permutation_invariance`: Validates output determinism under arbitrary step permutations.

**Test Run Results:**
```text
Ran 75 tests in 0.293s
OK (All 75 tests passing)
```

---

## 5. Before and After Benchmark Metrics

Evaluated on the 32 public ground-truth cases (`dataset/sample_deletion_requests.csv`):

| Metric | Baseline (M6) | Post-Sprint (M7) | Delta |
|---|---|---|---|
| **Status Accuracy** | 32 / 32 (100.0%) | 32 / 32 (100.0%) | 0.0% (Maintained) |
| **Strict 5-Field Step Matches** | 188 / 193 (97.41%) | 188 / 193 (97.41%) | 0.0% (Maintained) |
| **5-Field Precision** | 98.95% (188/190) | 98.95% (188/190) | 0.0% (Maintained) |
| **5-Field Recall** | 97.41% (188/193) | 97.41% (188/193) | 0.0% (Maintained) |
| **5-Field F1 Score** | 98.17% | 98.17% | 0.0% (Maintained) |
| **Strict 6-Field Step Matches** | 187 / 193 (96.89%) | 187 / 193 (96.89%) | 0.0% (Maintained) |
| **6-Field Precision** | 98.42% (187/190) | 98.42% (187/190) | 0.0% (Maintained) |
| **6-Field Recall** | 96.89% (187/193) | 96.89% (187/193) | 0.0% (Maintained) |
| **6-Field F1 Score** | 97.65% | 97.65% | 0.0% (Maintained) |
| **Exact 5-Field Cases** | 27 / 32 (84.38%) | 27 / 32 (84.38%) | 0.0% (Maintained) |
| **Exact 7-Field Cases** | 26 / 32 (81.25%) | 26 / 32 (81.25%) | 0.0% (Maintained) |
| **Total Passing Tests** | 63 / 63 (100.0%) | 75 / 75 (100.0%) | **+12 passing tests** |

Zero regressions were introduced. All architectural enhancements integrate cleanly with 100% fidelity.

---

## 6. Full-Dataset Validation Results (518 Cases)

All 518 evaluation requests in `dataset/deletion_requests.csv` were audited and validated across the 14 contract rules:

- **Row Count:** Exactly 518 rows (100% matched to `deletion_requests.csv`).
- **Status Distribution:**
  - `COMPLETE`: 212 cases (40.93%)
  - `INCOMPLETE`: 296 cases (57.14%)
  - `NOT_APPLICABLE`: 10 cases (1.93%)
- **Total Steps Audited:** 2,722 steps across all 518 cases.
- **Fabricated Evidence IDs:** Exactly 0.
- **Temporal Leaks:** Exactly 0 (zero citations of evidence captured after `audit_at`).
- **Ordering and Schema:** 100% compliant with canonical phase (`FINDING` $\to$ `REMEDIATION` $\to$ `VERIFICATION`) and 7-field schema.
- **Output Checksum:**
  - `output.csv` SHA-256: `EA0EFBC579314C8A9917DC5A3E24F664E1A4DD3B8594819902BB46AC421371A1`
  - Re-generated output matched the baseline byte-for-byte, confirming **100% determinism**.

---

## 7. Regressions and Resolution

- **Regression Count:** 0.
- All 63 previously passing tests passed without modification.
- All 12 new tests in `tests/test_milestone7_xfactor.py` passed on first execution.
- Deterministic output generation across all 518 cases was preserved with identical cryptographic checksums.

---

## 8. Remaining X-Factor Capabilities (Future Work)

1. **Persistent Graph Database Integration (e.g., Neo4j / NetworkX):**
   - The current `TemporalEvidenceGraph` is implemented as an in-memory typed Python graph. While fast (~0.29s for the full suite), an external graph database could support complex graph query languages (Cypher) for enterprise deployments.
2. **Selective Local LLM Intent Disambiguation:**
   - Multilingual intent classification is currently handled deterministically via compiled regex heuristics. If a local LLM (e.g., Ollama / Llama 3) were integrated in future work, it could handle colloquial language variations without compromising test reproducibility.

---

## 9. Verified Artifact Paths and Checksums

| Artifact | Relative Path | Verified SHA-256 Checksum |
|---|---|---|
| **Root Predictions** | `output.csv` | `EA0EFBC579314C8A9917DC5A3E24F664E1A4DD3B8594819902BB46AC421371A1` |
| **Official Reference** | `dataset/output.csv` | `6A08A7C64BD6C8D81C1D73740D2F44BD7728BCE9DCD06B4C0A74F5CD8D203970` (Preserved intact) |
| **Submission Archive** | `code.zip` | Rebuilt and verified with 31 clean files (0 dataset, 0 cache, 0 secrets) |
| **Audit Log** | `log.txt` | Continuously appended per AGENTS.md §5.2 |



---

## 10. Release Recommendation

**VERDICT: GO**

PHANTOM has successfully graduated from a deterministic heuristic matcher to a robust, evidence-grounded AI deletion-audit engine featuring:
- An explicit **Temporal Evidence Graph** modeling entity relationships and strict cutoff boundaries.
- A **Causal Remediation Planner** enforcing topological dependency ordering and zero-evidence planning constraints.
- An operational **Audit Explainer** providing transparent, judge-facing audit dossiers.
- 75/75 passing tests and 100% deterministic, contract-compliant evaluation outputs.
