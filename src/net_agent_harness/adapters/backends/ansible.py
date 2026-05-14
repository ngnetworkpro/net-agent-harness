from net_agent_harness.adapters.backends.base import BackendAdapter
from net_agent_harness.models.artifacts import ConfigRender, ExecutionResult
from net_agent_harness.models.changes import ChangeRequest


class AnsibleBackendAdapter(BackendAdapter):
    async def render(self, change_request: ChangeRequest) -> ConfigRender:
        raise NotImplementedError(
            "AnsibleBackendAdapter is not yet implemented. "
            "Set NET_AGENT_EXECUTION_BACKEND=terraform to use the Terraform backend."
        )

    async def apply(self, config_render: ConfigRender) -> ExecutionResult:
        raise NotImplementedError(
            "AnsibleBackendAdapter is not yet implemented. "
            "Set NET_AGENT_EXECUTION_BACKEND=terraform to use the Terraform backend."
        )
