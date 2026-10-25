import os
import sys
import csv
import json
import argparse
from typing import List, Dict, Any

# Ensure repo root is on sys.path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

try:
    from code.identity import IdentityResolver
    from code.evidence_index import EvidenceIndex
    from code.auditor import DeletionAuditor
    from code.models import Step
except (ImportError, ModuleNotFoundError):
    from identity import IdentityResolver
    from evidence_index import EvidenceIndex
    from auditor import DeletionAuditor
    from models import Step

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Ghost Data Still Exists — AI-powered deletion-audit CLI")
    parser.add_argument("--dataset", type=str, default="dataset", help="Path to dataset directory")
    parser.add_argument("--requests", type=str, default=None, help="Path to deletion requests CSV (defaults to dataset/deletion_requests.csv)")
    parser.add_argument("--output", type=str, default="output.csv", help="Path to output CSV destination")
    parser.add_argument("--explain", type=str, default=None, help="Case ID to generate detailed audit explanation for")
    args = parser.parse_args()

    dataset_dir = args.dataset
    requests_path = args.requests or os.path.join(dataset_dir, "deletion_requests.csv")
    output_path = args.output

    # 1. Initialize identity resolver
    identities_csv = os.path.join(dataset_dir, "user_identities.csv")
    audit_log_csv = os.path.join(dataset_dir, "user_audit_log.csv")
    resolver = IdentityResolver(identities_csv, audit_log_csv)

    # 2. Initialize evidence index
    index = EvidenceIndex(dataset_dir)

    # 3. Initialize auditor
    auditor = DeletionAuditor(index, resolver)

    # 4. Read deletion requests
    requests = []
    with open(requests_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            requests.append(row)

    auditor.set_requests(requests)

    # If --explain is requested, output dossier for that case and exit
    if args.explain:
        target_case = next((r for r in requests if r["case_id"] == args.explain), None)
        if not target_case:
            print(f"Error: Case {args.explain} not found in {requests_path}")
            sys.exit(1)
        dossier = auditor.explain_case(target_case)
        print(json.dumps(dossier, indent=2))
        return

    print(f"=== Initializing Deletion Audit Agent ===")
    print(f"Dataset root:   {dataset_dir}")
    print(f"Input requests: {requests_path}")
    print(f"Output file:    {output_path}")
    print(f"Processing {len(requests)} cases...")
    output_rows = []


    for i, req in enumerate(requests):
        case_id = req["case_id"]
        status, steps = auditor.audit_case(req)

        # Serialize steps to dicts with exact 7 keys
        steps_dicts = [s.to_dict() for s in steps]
        steps_json = json.dumps(steps_dicts, separators=(',', ':'))

        output_rows.append({
            "case_id": case_id,
            "deletion_status": status,
            "steps_json": steps_json
        })

        if (i + 1) % 50 == 0 or (i + 1) == len(requests):
            print(f"  Processed {i + 1}/{len(requests)} cases...")

    # Sort output rows by natural case number (case_01..case_550)
    def _case_sort_key(cid: str):
        parts = cid.split("_")
        if len(parts) == 2 and parts[1].isdigit():
            return int(parts[1])
        return cid

    output_rows.sort(key=lambda r: _case_sort_key(r["case_id"]))

    # Write output CSV
    print(f"Writing {len(output_rows)} rows to {output_path}...")
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"], quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in output_rows:
            writer.writerow(r)

    print(f"=== Completed Audit Run Successfully ===")
    print(f"Saved: {output_path} with {len(output_rows)} cases.")

if __name__ == "__main__":
    main()
