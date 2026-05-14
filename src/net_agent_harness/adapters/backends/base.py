from abc import ABC, abstractmethod
from net_agent_harness.models.artifacts import ConfigRender, ExecutionResult
from net_agent_harness.models.changes import ChangeRequest


class BackendAdapter(ABC):
    @abstractmethod
    async def render(self, change_request: ChangeRequest) -> ConfigRender:
        """Produce a human-readable preview of the proposed change."""

    @abstractmethod
    async def apply(self, config_render: ConfigRender) -> ExecutionResult:
        """Execute the change. Only called after human approval."""
