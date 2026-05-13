from net_agent_harness.adapters.backends.base import BackendAdapter
from net_agent_harness.adapters.backends.terraform import TerraformBackendAdapter
from net_agent_harness.adapters.backends.direct_api import DirectAPIBackendAdapter
from net_agent_harness.adapters.backends.ansible import AnsibleBackendAdapter
from net_agent_harness.config import Settings, settings
from net_agent_harness.models.artifacts import ConfigRender


def get_backend_adapter(s: Settings | None = None) -> BackendAdapter:
    s = s or settings
    match s.execution_backend:
        case "terraform":
            return TerraformBackendAdapter()
        case "direct_api":
            return DirectAPIBackendAdapter()
        case "ansible":
            return AnsibleBackendAdapter()
        case _:
            raise ValueError(f"Unknown execution backend: {s.execution_backend!r}")


def request_approval(config_render: ConfigRender) -> bool:
    """Present the proposed change to the operator and wait for approval."""
    print("\n" + "=" * 60)
    print("PENDING APPROVAL")
    print("=" * 60)
    print(f"Summary: {config_render.summary}")

    if config_render.warnings:
        print("\nWarnings:")
        for w in config_render.warnings:
            print(f"  ! {w}")

    if config_render.snippets:
        print("\nProposed changes:")
        for snippet in config_render.snippets:
            print(f"\n  [{snippet.device_name}]")
            if snippet.path_hint:
                print(f"  File: {snippet.path_hint}")
            if snippet.rendered_text:
                for line in snippet.rendered_text.splitlines():
                    print(f"  {line}")

    print("\n" + "=" * 60)
    try:
        response = input("Apply these changes? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nApproval cancelled.")
        return False

    return response == "y"
