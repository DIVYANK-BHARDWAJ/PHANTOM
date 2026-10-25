# Known Limitations & Benchmark Audit Notes

## 1. Schema Differences
* **Status Enum Contract**: PHANTOM's native competition format emits three statuses (`COMPLETE`, `INCOMPLETE`, `NOT_APPLICABLE`). The synthetic benchmark defines six statuses (`completed`, `in_progress`, `blocked`, `failed`, `partially_completed`, `not_found`). The adapter translates lifecycle states into this six-status ontology without modifying PHANTOM's core algorithms.
* **Step Representation**: The benchmark expects step sequences as action strings (e.g., `request_received`, `primary_record_deleted`), whereas competition steps are structured JSON objects with 7 keys (`step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state`, `evidence_id`).

## 2. Synthetic Label Limitations
* **Synthetic Ground Truth**: As disclosed in the benchmark documentation, expected labels are rule-generated synthetic ground truth rather than human-adjudicated production audits. Edge cases where requests were closed before secondary replication completed reflect generator heuristics.
* **Non-Measurable Metrics**: Explanations or free-text rationales were not evaluated because the benchmark does not supply ground-truth explanation strings.

## 3. Data Integrity & Leakage Prevention
* **Ground-Truth Isolation**: The `expected` field and `ground_truth.csv` were completely excluded from the inference payload. All predictions were generated solely from `evidence`, `created_at`, `evaluation_cutoff`, and `context`.
