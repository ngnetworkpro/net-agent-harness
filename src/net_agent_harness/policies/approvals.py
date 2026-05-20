from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

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


class PolicyDenied(PermissionError):
    """Raised when a mutating operation is attempted without required approval."""


class WriteCapability(str, Enum):
    INVENTORY = "inventory_write"
    IPAM = "ipam_write"
    TOPOLOGY = "topology_write"


class WriteApprovalContext(BaseModel):
    """Policy artifact required before any source-of-truth write can proceed."""

    model_config = ConfigDict(extra="forbid")

    approved_artifact_id: str | None = Field(
        default=None,
        description="Approved artifact authorizing the write, such as a validation or execution artifact.",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Evidence references reviewed alongside the approving artifact.",
    )
    capability_grants: list[WriteCapability] = Field(
        default_factory=list,
        description="Explicit write capabilities granted by policy for this artifact.",
    )


_WRITE_ENABLEMENT_BY_CAPABILITY: dict[WriteCapability, str] = {
    WriteCapability.INVENTORY: "enable_inventory_writes",
    WriteCapability.IPAM: "enable_ipam_writes",
    WriteCapability.TOPOLOGY: "enable_topology_writes",
}


def is_write_capability_enabled(
    capability: WriteCapability,
    s: Settings | None = None,
) -> bool:
    active_settings = s or settings
    return bool(getattr(active_settings, _WRITE_ENABLEMENT_BY_CAPABILITY[capability]))


def assert_write_allowed(
    capability: WriteCapability,
    approval: WriteApprovalContext,
    s: Settings | None = None,
) -> None:
    """Require explicit configuration, approval artifact, evidence, and grant."""

    if not is_write_capability_enabled(capability, s=s):
        raise PolicyDenied(
            f"Write capability '{capability.value}' is disabled by configuration."
        )

    if not approval.approved_artifact_id:
        raise PolicyDenied(
            f"Write capability '{capability.value}' requires an approved artifact."
        )

    if capability not in approval.capability_grants:
        raise PolicyDenied(
            f"Write capability '{capability.value}' requires an explicit capability grant."
        )

    if not approval.evidence:
        raise PolicyDenied(
            f"Write capability '{capability.value}' requires reviewed evidence references."
        )


def deny_unimplemented_write(
    capability: WriteCapability,
    approval: WriteApprovalContext,
    s: Settings | None = None,
) -> None:
    """Enforce the write gate, then keep the write path stubbed."""

    assert_write_allowed(capability, approval, s=s)
    raise NotImplementedError(
        f"Write capability '{capability.value}' is approval-gated but not implemented."
    )


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
