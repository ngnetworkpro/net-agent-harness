"""Site-template and design-policy models.

This module defines:
- ``VlanAssignment``       — a VLAN slot in a site template.
- ``IpBlockRange``         — an IP block reservation in a site template.
- ``SiteTemplate``         — a versioned, reusable site configuration template.
- ``DesignPolicy``         — constraints that proposals must satisfy.
- ``PolicyViolation``      — a single violation found during policy validation.
- ``validate_against_design_policy`` — deterministic policy check function.

Templates are expected to be stored as versioned YAML or JSON alongside
the domain glossaries and loaded at planning time to ground proposals in
standards-compliant defaults.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VlanAssignment(BaseModel):
    """A VLAN slot defined in a site template."""

    model_config = ConfigDict(extra="forbid")

    vlan_id: int = Field(ge=1, le=4094, description="VLAN ID")
    name: str = Field(description="Human-readable VLAN name, e.g. 'Management'")
    role: str | None = Field(
        default=None,
        description="Functional role, e.g. 'management', 'server', 'guest', 'voice'",
    )


class IpBlockRange(BaseModel):
    """An IP address block reserved for a specific purpose in a site template."""

    model_config = ConfigDict(extra="forbid")

    cidr: str = Field(description="CIDR block, e.g. '10.10.0.0/16'")
    purpose: str = Field(
        description="Intended use, e.g. 'management', 'servers', 'guest', 'infrastructure'"
    )
    vlan_id: int | None = Field(
        default=None,
        description="VLAN this block is associated with, if applicable",
    )


class SiteTemplate(BaseModel):
    """A versioned, reusable site configuration template.

    A site template encodes the standard VLAN layout, IP block reservations,
    expected device roles, and naming conventions for a class of sites (e.g.
    a standard branch site or a data-centre pod).  Planners load the relevant
    template as grounding context to ensure proposals conform to organisational
    standards.

    Templates are stored as versioned YAML alongside domain glossaries and
    loaded by ``load_render_context`` or similar loaders.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Template name, e.g. 'standard-branch-v2'")
    description: str | None = Field(
        default=None, description="Human-readable description of this template"
    )
    version: str = Field(default="1.0", description="Semantic version string")
    vlan_assignments: list[VlanAssignment] = Field(
        default_factory=list,
        description="Standard VLAN assignments for sites using this template",
    )
    ip_block_ranges: list[IpBlockRange] = Field(
        default_factory=list,
        description="IP block reservations defined by this template",
    )
    device_roles: list[str] = Field(
        default_factory=list,
        description="Expected device roles at sites using this template, e.g. ['core', 'access', 'firewall']",
    )
    naming_conventions: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Naming convention patterns keyed by resource type, "
            "e.g. {'device': '{site}-{role}{nn}', 'vlan': '{site}-{role}-vlan{id}'}"
        ),
    )


class DesignPolicy(BaseModel):
    """Constraints that a planner proposal must satisfy.

    A design policy complements a ``SiteTemplate`` by expressing hard and
    soft constraints on what the planner is allowed to propose.  Violations
    surface as ``PolicyViolation`` findings — either ``warning`` (non-blocking)
    or ``blocked`` (hard failure that prevents ``apply``).

    Policy files are stored as versioned YAML alongside site templates.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Policy name, e.g. 'branch-design-policy-v1'")
    description: str | None = Field(
        default=None, description="Human-readable description of this policy"
    )
    version: str = Field(default="1.0", description="Semantic version string")
    allowed_vlan_ranges: list[tuple[int, int]] = Field(
        default_factory=list,
        description=(
            "List of (min_vlan_id, max_vlan_id) inclusive ranges that proposals are permitted to use. "
            "An empty list means no VLAN range restriction."
        ),
    )
    required_prefix_lengths: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Minimum required prefix length by purpose, e.g. "
            "{'management': 24, 'servers': 24, 'guest': 25}. "
            "A proposal using a larger (less specific) prefix than required fails validation."
        ),
    )
    topology_requirements: list[str] = Field(
        default_factory=list,
        description=(
            "Human-readable topology constraints that must be satisfied, "
            "e.g. ['All access switches must have a redundant uplink']"
        ),
    )
    max_vlans_per_site: int | None = Field(
        default=None,
        description="Maximum number of VLANs allowed per site; None means unlimited",
    )


class PolicyViolation(BaseModel):
    """A single policy constraint violation found during proposal validation."""

    model_config = ConfigDict(extra="forbid")

    policy_name: str = Field(description="Name of the policy that was violated")
    rule: str = Field(description="Short rule identifier, e.g. 'allowed_vlan_range'")
    details: str = Field(description="Human-readable explanation of why this is a violation")
    severity: str = Field(
        default="warning",
        description="'blocked' for hard failures that prevent apply; 'warning' for advisory findings",
    )


def validate_against_design_policy(
    proposed_vlans: list[int],
    proposed_prefixes: dict[str, int],
    policy: DesignPolicy,
) -> list[PolicyViolation]:
    """Check a proposal against a ``DesignPolicy`` and return any violations.

    This function is deterministic and side-effect-free.  It validates the
    VLAN IDs and prefix lengths proposed by a planner and returns a list of
    ``PolicyViolation`` findings.  An empty list means the proposal is
    policy-compliant.

    Parameters
    ----------
    proposed_vlans:
        List of VLAN IDs proposed by the planner.
    proposed_prefixes:
        Dict mapping purpose → proposed prefix length,
        e.g. ``{'management': 24, 'guest': 26}``.
    policy:
        The ``DesignPolicy`` to validate against.

    Returns
    -------
    list[PolicyViolation]
        All violations found.  Empty when the proposal is compliant.
    """
    violations: list[PolicyViolation] = []

    # VLAN range check
    if policy.allowed_vlan_ranges:
        for vlan_id in proposed_vlans:
            in_range = any(lo <= vlan_id <= hi for lo, hi in policy.allowed_vlan_ranges)
            if not in_range:
                violations.append(
                    PolicyViolation(
                        policy_name=policy.name,
                        rule="allowed_vlan_range",
                        details=(
                            f"VLAN {vlan_id} is outside the allowed ranges "
                            f"{policy.allowed_vlan_ranges}."
                        ),
                        severity="blocked",
                    )
                )

    # Max VLAN count check
    if policy.max_vlans_per_site is not None:
        if len(proposed_vlans) > policy.max_vlans_per_site:
            violations.append(
                PolicyViolation(
                    policy_name=policy.name,
                    rule="max_vlans_per_site",
                    details=(
                        f"Proposal includes {len(proposed_vlans)} VLANs but "
                        f"the policy allows at most {policy.max_vlans_per_site}."
                    ),
                    severity="blocked",
                )
            )

    # Prefix length check — larger prefix_length value = more specific = stricter minimum
    for purpose, required_length in policy.required_prefix_lengths.items():
        proposed_length = proposed_prefixes.get(purpose)
        if proposed_length is None:
            continue
        if proposed_length < required_length:
            violations.append(
                PolicyViolation(
                    policy_name=policy.name,
                    rule="required_prefix_length",
                    details=(
                        f"Purpose '{purpose}': proposed /{proposed_length} is less specific than "
                        f"the required minimum /{required_length}."
                    ),
                    severity="blocked",
                )
            )

    return violations
