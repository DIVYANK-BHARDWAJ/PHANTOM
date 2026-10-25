import csv
import json
import os
import sys
from typing import Dict, Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure repository root is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from code.identity import IdentityResolver
from code.evidence_index import EvidenceIndex
from code.auditor import DeletionAuditor

def run_evaluation(dataset_dir: str = "dataset") -> Dict[str, Any]:
    resolver = IdentityResolver(
        os.path.join(dataset_dir, "user_identities.csv"),
        os.path.join(dataset_dir, "user_audit_log.csv")
    )
    index = EvidenceIndex(dataset_dir)
    auditor = DeletionAuditor(index, resolver)

    sample_requests_path = os.path.join(dataset_dir, "sample_deletion_requests.csv")
    sample_output_path = os.path.join(dataset_dir, "sample_output.csv")

    with open(sample_requests_path, "r", encoding="utf-8") as f:
        requests = list(csv.DictReader(f))

    auditor.set_requests(requests)

    with open(sample_output_path, "r", encoding="utf-8") as f:
        ground_truth = {r["case_id"]: r for r in csv.DictReader(f)}

    total_cases = len(requests)
    correct_statuses = 0
    total_expected_steps = 0
    correct_steps = 0
    perfect_cases = 0

    results = []

    print(f"\n=======================================================")
    print(f"RUNNING REGRESSION EVALUATION ACROSS {total_cases} SAMPLE CASES")
    print(f"=======================================================\n")

    for req in requests:
        cid = req["case_id"]
        true_row = ground_truth.get(cid)
        if not true_row:
            continue

        true_status = true_row["deletion_status"]
        true_steps = json.loads(true_row["steps_json"])

        pred_status, pred_step_objs = auditor.audit_case(req)
        pred_steps = [s.to_dict() for s in pred_step_objs]

        status_match = (pred_status == true_status)
        if status_match:
            correct_statuses += 1

        total_expected_steps += len(true_steps)
        total_pred_steps = len(pred_steps)

        # Standard step representation (including evidence_id)
        true_tuples = [(s["phase"], s["system_id"], s["resource_id"], s["operation"], s["state"], s.get("evidence_id", "")) for s in true_steps]
        pred_tuples = [(s["phase"], s["system_id"], s["resource_id"], s["operation"], s["state"], s.get("evidence_id", "")) for s in pred_steps]

        # 5-field tuples (for legacy backward comparison)
        true_5tuples = [t[:5] for t in true_tuples]
        pred_5tuples = [t[:5] for t in pred_tuples]

        # Match without replacement to prevent duplicate predicted steps from inflating matches
        matched_indices = set()
        case_matches = 0
        for pt in pred_5tuples:
            for idx, tt in enumerate(true_5tuples):
                if idx not in matched_indices and pt == tt:
                    matched_indices.add(idx)
                    case_matches += 1
                    break
        correct_steps += case_matches

        # Strict exact match requires status match, identical length, and identical step sequences
        is_exact = (status_match and true_5tuples == pred_5tuples)
        if is_exact:
            perfect_cases += 1

        status_symbol = "✓" if status_match else "✗"
        step_symbol = "✓" if is_exact else "✗"
        print(f"[{status_symbol}] {cid}: Status={pred_status} (expected {true_status}) | Steps: {len(pred_steps)}/{len(true_steps)} (matched {case_matches}) {step_symbol}")
        if not is_exact:
            missing = [t for idx, t in enumerate(true_5tuples) if idx not in matched_indices]
            extra_count = len(pred_steps) - case_matches
            if missing:
                print(f"      Missing: {missing}")
            if extra_count > 0:
                print(f"      Extra unmatched steps: {extra_count}")

    status_acc = (correct_statuses / total_cases) * 100
    step_recall = (correct_steps / total_expected_steps) * 100 if total_expected_steps else 100
    perfect_acc = (perfect_cases / total_cases) * 100

    print(f"\n=======================================================")
    print(f"EVALUATION SUMMARY:")
    print(f"  Case Status Accuracy: {correct_statuses}/{total_cases} ({status_acc:.1f}%)")
    print(f"  Step Match Accuracy:  {correct_steps}/{total_expected_steps} ({step_recall:.1f}%)")
    print(f"  Exact Match Cases:    {perfect_cases}/{total_cases} ({perfect_acc:.1f}%)")
    print(f"=======================================================\n")

    return {
        "status_acc": status_acc,
        "step_acc": step_recall,
        "perfect_acc": perfect_acc
    }

if __name__ == "__main__":
    run_evaluation()
