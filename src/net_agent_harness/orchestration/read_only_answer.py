from datetime import datetime, timezone
from uuid import uuid4

from ..models.artifacts import ReadOnlyAnswer
from ..models.common import ArtifactMeta
from ..models.enums import Capability
from ..tools.ipam_tools import answer_ipam_question
from ..tools.topology_tools import answer_topology_question


def build_read_only_answer(
    question: str,
    capability: Capability,
    inventory_source: str,
    operator: str = "local-user",
) -> ReadOnlyAnswer:
    if capability is Capability.TOPOLOGY:
        result = answer_topology_question(question, inventory_source=inventory_source)
    elif capability is Capability.IPAM:
        result = answer_ipam_question(question, inventory_source=inventory_source)
    else:
        raise ValueError(f"Unsupported read-only capability: {capability.value}")

    run_id = f"run-{uuid4().hex[:8]}"
    return ReadOnlyAnswer(
        meta=ArtifactMeta(
            run_id=run_id,
            artifact_id=f"answer-{run_id}",
            version=1,
            created_at=datetime.now(timezone.utc),
            created_by=operator,
        ),
        capability=capability,
        question=question,
        answer=result["answer"],
        data=result.get("data", {}),
    )
