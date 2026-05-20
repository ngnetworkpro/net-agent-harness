"""Tests for SiteTemplate, DesignPolicy, and policy validation (Issue #64)."""
import pytest
from pydantic import ValidationError

from net_agent_harness.models.site_template import (
    DesignPolicy,
    IpBlockRange,
    PolicyViolation,
    SiteTemplate,
    VlanAssignment,
    validate_against_design_policy,
)


class TestVlanAssignment:
    def test_basic_creation(self):
        va = VlanAssignment(vlan_id=10, name="Management")
        assert va.vlan_id == 10
        assert va.name == "Management"
        assert va.role is None

    def test_with_role(self):
        va = VlanAssignment(vlan_id=20, name="Servers", role="server")
        assert va.role == "server"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            VlanAssignment(vlan_id=10, name="x", extra_field="nope")  # type: ignore[call-arg]


class TestIpBlockRange:
    def test_basic_creation(self):
        block = IpBlockRange(cidr="10.10.0.0/16", purpose="management")
        assert block.cidr == "10.10.0.0/16"
        assert block.purpose == "management"
        assert block.vlan_id is None

    def test_with_vlan(self):
        block = IpBlockRange(cidr="10.10.1.0/24", purpose="servers", vlan_id=100)
        assert block.vlan_id == 100


class TestSiteTemplate:
    def test_minimal_template(self):
        tmpl = SiteTemplate(name="standard-branch-v1")
        assert tmpl.name == "standard-branch-v1"
        assert tmpl.version == "1.0"
        assert tmpl.vlan_assignments == []
        assert tmpl.ip_block_ranges == []
        assert tmpl.device_roles == []
        assert tmpl.naming_conventions == {}

    def test_full_template(self):
        tmpl = SiteTemplate(
            name="branch-v2",
            description="Standard branch site template",
            version="2.0",
            vlan_assignments=[
                VlanAssignment(vlan_id=10, name="Management", role="management"),
                VlanAssignment(vlan_id=20, name="Servers", role="server"),
            ],
            ip_block_ranges=[
                IpBlockRange(cidr="10.0.0.0/8", purpose="infrastructure"),
            ],
            device_roles=["core", "access", "firewall"],
            naming_conventions={"device": "{site}-{role}{nn}"},
        )
        assert len(tmpl.vlan_assignments) == 2
        assert len(tmpl.ip_block_ranges) == 1
        assert "core" in tmpl.device_roles
        assert tmpl.naming_conventions["device"] == "{site}-{role}{nn}"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            SiteTemplate(name="x", unexpected="nope")  # type: ignore[call-arg]


class TestDesignPolicy:
    def test_minimal_policy(self):
        policy = DesignPolicy(name="branch-policy-v1")
        assert policy.name == "branch-policy-v1"
        assert policy.version == "1.0"
        assert policy.allowed_vlan_ranges == []
        assert policy.required_prefix_lengths == {}
        assert policy.topology_requirements == []
        assert policy.max_vlans_per_site is None

    def test_full_policy(self):
        policy = DesignPolicy(
            name="strict-branch",
            allowed_vlan_ranges=[(10, 99), (200, 299)],
            required_prefix_lengths={"management": 24, "servers": 24, "guest": 25},
            topology_requirements=["All access switches must have a redundant uplink"],
            max_vlans_per_site=50,
        )
        assert len(policy.allowed_vlan_ranges) == 2
        assert policy.required_prefix_lengths["management"] == 24
        assert policy.max_vlans_per_site == 50

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            DesignPolicy(name="x", unexpected="nope")  # type: ignore[call-arg]


class TestPolicyViolation:
    def test_default_severity_is_warning(self):
        v = PolicyViolation(
            policy_name="p1", rule="allowed_vlan_range", details="VLAN 999 not allowed"
        )
        assert v.severity == "warning"

    def test_blocked_severity(self):
        v = PolicyViolation(
            policy_name="p1",
            rule="allowed_vlan_range",
            details="VLAN 999 not allowed",
            severity="blocked",
        )
        assert v.severity == "blocked"


class TestValidateAgainstDesignPolicy:
    def _policy(self) -> DesignPolicy:
        return DesignPolicy(
            name="test-policy",
            allowed_vlan_ranges=[(10, 99), (200, 299)],
            required_prefix_lengths={"management": 24, "servers": 24},
            max_vlans_per_site=5,
        )

    def test_compliant_proposal_returns_no_violations(self):
        policy = self._policy()
        violations = validate_against_design_policy(
            proposed_vlans=[10, 20, 30],
            proposed_prefixes={"management": 24, "servers": 24},
            policy=policy,
        )
        assert violations == []

    def test_vlan_outside_range_is_blocked(self):
        policy = self._policy()
        violations = validate_against_design_policy(
            proposed_vlans=[999],
            proposed_prefixes={},
            policy=policy,
        )
        assert len(violations) == 1
        assert violations[0].rule == "allowed_vlan_range"
        assert violations[0].severity == "blocked"

    def test_multiple_out_of_range_vlans_produce_multiple_violations(self):
        policy = self._policy()
        violations = validate_against_design_policy(
            proposed_vlans=[100, 150, 999],
            proposed_prefixes={},
            policy=policy,
        )
        vlan_violations = [v for v in violations if v.rule == "allowed_vlan_range"]
        assert len(vlan_violations) == 3

    def test_too_many_vlans_is_blocked(self):
        policy = self._policy()
        violations = validate_against_design_policy(
            proposed_vlans=[10, 20, 30, 40, 50, 60],  # 6 > max_vlans_per_site=5
            proposed_prefixes={},
            policy=policy,
        )
        max_violations = [v for v in violations if v.rule == "max_vlans_per_site"]
        assert len(max_violations) == 1
        assert max_violations[0].severity == "blocked"

    def test_prefix_too_short_is_blocked(self):
        policy = self._policy()
        violations = validate_against_design_policy(
            proposed_vlans=[],
            proposed_prefixes={"management": 22},  # /22 is less specific than /24
            policy=policy,
        )
        prefix_violations = [v for v in violations if v.rule == "required_prefix_length"]
        assert len(prefix_violations) == 1
        assert prefix_violations[0].severity == "blocked"

    def test_prefix_more_specific_than_required_is_allowed(self):
        policy = self._policy()
        violations = validate_against_design_policy(
            proposed_vlans=[],
            proposed_prefixes={"management": 26},  # /26 is more specific than /24 — allowed
            policy=policy,
        )
        assert violations == []

    def test_no_vlan_range_restriction_allows_any_vlan(self):
        policy = DesignPolicy(name="open-policy")  # no allowed_vlan_ranges
        violations = validate_against_design_policy(
            proposed_vlans=[1, 100, 4000],
            proposed_prefixes={},
            policy=policy,
        )
        assert violations == []

    def test_unknown_purpose_in_prefixes_is_skipped(self):
        policy = self._policy()
        violations = validate_against_design_policy(
            proposed_vlans=[],
            proposed_prefixes={"guest": 26},  # "guest" not in policy.required_prefix_lengths
            policy=policy,
        )
        assert violations == []
