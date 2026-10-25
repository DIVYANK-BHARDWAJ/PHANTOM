from dataclasses import dataclass, asdict
from typing import List, Dict, Any

# Operation priority order within phases as specified in problem_statement.md
FINDING_OPERATIONS = [
    "REPORT_REMAINING_RECORD",
    "REPORT_EXPOSED_PII",
    "REPORT_ACTIVE_DATA_FLOW",
    "REPORT_RESTORE_RISK"
]

REMEDIATION_OPERATIONS = [
    "DISABLE_DATA_FLOW",
    "BLOCK_RESTORE",
    "DELETE_RECORD",
    "REDACT_RECORD",
    "ANONYMIZE_RECORD"
]

VERIFICATION_OPERATIONS = [
    "VERIFY_RECORD_ABSENT",
    "VERIFY_RECORD_PRESENT",
    "VERIFY_RECORD_REDACTED",
    "VERIFY_RECORD_ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED",
    "VERIFY_RESTORE_BLOCKED"
]

PHASE_ORDER = {
    "FINDING": 1,
    "REMEDIATION": 2,
    "VERIFICATION": 3
}

OPERATION_ORDER = {}
for i, op in enumerate(FINDING_OPERATIONS):
    OPERATION_ORDER[op] = i
for i, op in enumerate(REMEDIATION_OPERATIONS):
    OPERATION_ORDER[op] = i
for i, op in enumerate(VERIFICATION_OPERATIONS):
    OPERATION_ORDER[op] = i

@dataclass
class Step:
    step_no: int
    phase: str
    system_id: str
    resource_id: str
    operation: str
    state: str
    evidence_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_no": self.step_no,
            "phase": self.phase,
            "system_id": self.system_id,
            "resource_id": self.resource_id,
            "operation": self.operation,
            "state": self.state,
            "evidence_id": self.evidence_id
        }

    def sort_key(self):
        # 1. Phase (FINDING, REMEDIATION, VERIFICATION)
        # 2. Operation order within phase
        # 3. system_id ascending
        # 4. resource_id ascending
        return (
            PHASE_ORDER.get(self.phase, 99),
            OPERATION_ORDER.get(self.operation, 99),
            self.system_id,
            self.resource_id
        )

def sort_and_renumber_steps(steps: List[Step]) -> List[Step]:
    """Sorts steps according to official ordering rules and assigns consecutive step numbers starting from 1."""
    sorted_steps = sorted(steps, key=lambda s: s.sort_key())
    numbered = []
    for idx, s in enumerate(sorted_steps, start=1):
        numbered.append(Step(
            step_no=idx,
            phase=s.phase,
            system_id=s.system_id,
            resource_id=s.resource_id,
            operation=s.operation,
            state=s.state,
            evidence_id=s.evidence_id
        ))
    return numbered
