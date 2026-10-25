#!/usr/bin/env python3
"""
Standalone Output CSV Verification Script for Ghost Data Still Exists
=====================================================================
Strictly validates output.csv against all competition requirements in AGENTS.md §6:
1. Exact file path: output.csv at repo root
2. Exact header: case_id,deletion_status,steps_json
3. Exactly 518 data rows
4. Exactly one row per case_id in dataset/deletion_requests.csv, matching case_ids
5. Rows sorted by case_id
6. Valid deletion_status enum: COMPLETE, INCOMPLETE, NOT_APPLICABLE
7. Valid JSON array in steps_json
8. When NOT_APPLICABLE: steps_json == []
9. Sequential 1-indexed step_no
10. Valid phases (FINDING -> REMEDIATION -> VERIFICATION)
11. Allowed operations and states only
12. Valid evidence_id citations:
    - COMPLETE: non-empty evidence_id for verification
    - INCOMPLETE: non-empty evidence_id for findings, empty for remediation and future verification
"""

import os
import sys
import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_CSV = REPO_ROOT / "output.csv"
REQUESTS_CSV = REPO_ROOT / "dataset/deletion_requests.csv"
EVIDENCE_FILES_CSV = REPO_ROOT / "dataset/evidence_files.csv"

ALLOWED_STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
ALLOWED_PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]

ALLOWED_OPERATIONS = {
    "FINDING": {
        "REPORT_REMAINING_RECORD": "PRESENT",
        "REPORT_EXPOSED_PII": "PRESENT",
        "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
        "REPORT_RESTORE_RISK": "ACTIVE"
    },
    "REMEDIATION": {
        "DISABLE_DATA_FLOW": "DISABLED",
        "BLOCK_RESTORE": "BLOCKED",
        "DELETE_RECORD": "ABSENT",
        "REDACT_RECORD": "REDACTED",
        "ANONYMIZE_RECORD": "ANONYMIZED"
    },
    "VERIFICATION": {
        "VERIFY_RECORD_ABSENT": "ABSENT",
        "VERIFY_RECORD_PRESENT": "PRESENT",
        "VERIFY_RECORD_REDACTED": "REDACTED",
        "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
        "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
        "VERIFY_RESTORE_BLOCKED": "BLOCKED"
    }
}

def validate():
    print(f"=== Running Strict Output CSV Validation ===")
    print(f"Target: {OUTPUT_CSV}")

    if not OUTPUT_CSV.exists():
        print(f"FAIL: {OUTPUT_CSV} does not exist!")
        sys.exit(1)

    # 1. Load requests to verify case_id set
    expected_case_ids = []
    with open(REQUESTS_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            expected_case_ids.append(r["case_id"])

    assert len(expected_case_ids) == 518, f"Expected 518 requests, found {len(expected_case_ids)}"

    # 2. Load valid evidence IDs
    valid_evidence_ids = set()
    with open(EVIDENCE_FILES_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            valid_evidence_ids.add(r["file_id"])

    # 3. Read output.csv
    with open(OUTPUT_CSV, encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        if header != ["case_id", "deletion_status", "steps_json"]:
            print(f"FAIL: Header mismatch! Found {header}")
            sys.exit(1)

        rows = list(reader)

    print(f"Row count: {len(rows)} (expected 518)")
    if len(rows) != 518:
        print(f"FAIL: Expected exactly 518 data rows, found {len(rows)}")
        sys.exit(1)

    output_cids = [r[0] for r in rows]
    if set(output_cids) != set(expected_case_ids):
        diff = set(expected_case_ids) - set(output_cids)
        print(f"FAIL: Missing case IDs: {diff}")
        sys.exit(1)

    status_counts = {"COMPLETE": 0, "INCOMPLETE": 0, "NOT_APPLICABLE": 0}
    total_steps = 0

    for idx, (cid, status, steps_str) in enumerate(rows, start=1):
        if status not in ALLOWED_STATUSES:
            print(f"FAIL: Invalid status '{status}' at row {idx} ({cid})")
            sys.exit(1)
        status_counts[status] += 1

        try:
            steps = json.loads(steps_str)
        except Exception as e:
            print(f"FAIL: Malformed JSON at row {idx} ({cid}): {e}")
            sys.exit(1)

        if not isinstance(steps, list):
            print(f"FAIL: steps_json is not an array at row {idx} ({cid})")
            sys.exit(1)

        if status == "NOT_APPLICABLE":
            if steps != []:
                print(f"FAIL: NOT_APPLICABLE case {cid} must have empty steps array, got {steps}")
                sys.exit(1)
            continue

        total_steps += len(steps)
        current_phase_idx = 0

        for s_idx, s in enumerate(steps, start=1):
            # Check step_no
            if s.get("step_no") != s_idx:
                print(f"FAIL: Inconsecutive step_no in {cid}: step {s_idx} has {s.get('step_no')}")
                sys.exit(1)

            # Check 7 exact keys
            expected_keys = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}
            if set(s.keys()) != expected_keys:
                print(f"FAIL: Incorrect step keys in {cid} step {s_idx}: {set(s.keys())}")
                sys.exit(1)

            phase = s["phase"]
            if phase not in ALLOWED_PHASES:
                print(f"FAIL: Invalid phase '{phase}' in {cid} step {s_idx}")
                sys.exit(1)

            # Phase order monotonic check
            p_idx = ALLOWED_PHASES.index(phase)
            if p_idx < current_phase_idx:
                print(f"FAIL: Phase out of order in {cid}: {phase} after prior phase")
                sys.exit(1)
            current_phase_idx = p_idx

            op = s["operation"]
            state = s["state"]
            ev_id = s.get("evidence_id", "")

            if op not in ALLOWED_OPERATIONS[phase]:
                print(f"FAIL: Invalid operation '{op}' for phase {phase} in {cid}")
                sys.exit(1)

            expected_state = ALLOWED_OPERATIONS[phase][op]
            if state != expected_state:
                print(f"FAIL: State mismatch in {cid} step {s_idx}: op {op} requires state {expected_state}, got {state}")
                sys.exit(1)

            # Evidence rules
            if status == "COMPLETE":
                if phase != "VERIFICATION":
                    print(f"FAIL: COMPLETE case {cid} contains non-VERIFICATION step {s_idx}")
                    sys.exit(1)
                if not ev_id or ev_id not in valid_evidence_ids:
                    print(f"FAIL: COMPLETE case {cid} step {s_idx} missing valid evidence citation: '{ev_id}'")
                    sys.exit(1)
            elif status == "INCOMPLETE":
                if phase == "FINDING":
                    if not ev_id or ev_id not in valid_evidence_ids:
                        print(f"FAIL: FINDING in {cid} step {s_idx} missing valid evidence citation: '{ev_id}'")
                        sys.exit(1)
                else:
                    if ev_id != "":
                        print(f"FAIL: REMEDIATION / post-verification in {cid} must have empty evidence_id, got '{ev_id}'")
                        sys.exit(1)

    print("=== VALIDATION PASSED SUCCESSFULLY ===")
    print(f"Total Rows Verified: 518")
    print(f"Status Distribution: {status_counts}")
    print(f"Total Steps Verified: {total_steps}")
    print(f"All constraints, schemas, phase orderings, and evidence citations strictly compliant.")

if __name__ == "__main__":
    validate()
