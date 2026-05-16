from abc import ABC, abstractmethod
from net_agent_harness.models.artifacts import ConfigRender, ExecutionResult, ArtifactMeta
from net_agent_harness.models.changes import ChangeRequest


class BackendAdapter(ABC):
    @abstractmethod
    async def render(self, change_request: ChangeRequest) -> ConfigRender:
        """Produce a human-readable preview of the proposed change."""

    @abstractmethod
    async def apply(self, config_render: ConfigRender) -> ExecutionResult:
        """Execute the change. Only called after human approval."""

    def _make_meta(self, change_request: ChangeRequest, created_by: str) -> ArtifactMeta:
        from uuid import uuid4
        from datetime import datetime, timezone
        return ArtifactMeta(
            run_id=change_request.meta.run_id,
            artifact_id=str(uuid4()),
            version=1,
            created_at=datetime.now(timezone.utc),
            created_by=created_by,
        )
