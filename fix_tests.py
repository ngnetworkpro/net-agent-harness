import re
from pathlib import Path

files_to_fix = [
    "tests/test_models.py",
    "tests/test_artifact_store.py",
    "tests/test_config_tools.py",
    "tests/test_coordinator.py",
]

for file_path in files_to_fix:
    content = Path(file_path).read_text(encoding="utf-8")
    if "RollbackPlan" not in content:
        content = content.replace(
            "from net_agent_harness.models.changes import ChangeRequest, RequestedChange",
            "from net_agent_harness.models.changes import ChangeRequest, RequestedChange, RollbackPlan"
        )
    
    # Replace risk=ChangeRisk.LOW, with target_scope, rollback_plan, and risk
    if "target_scope" not in content:
        content = content.replace(
            "risk=ChangeRisk.LOW,",
            """target_scope="device",
        rollback_plan=RollbackPlan(
            summary="Revert",
            trigger_conditions=["Error"],
            rollback_steps=["Undo"]
        ),
        risk=ChangeRisk.LOW,"""
        )
    Path(file_path).write_text(content, encoding="utf-8")

print("Files fixed.")
