"""Tests for target_scope consistency validation.

Covers:
- Device names present + scope=device → passes unchanged
- Device names present + scope=site → corrected to device
- No device names, site present, targets resolved → corrected to site
- No device names, no site → ambiguous
- Scope=device but no resolved targets → ScopeValidationError
- Scope=ambiguous with device names → corrected to device
"""

import pytest

from net_agent_harness.models.changes import ResolvedTarget
from net_agent_harness.models.common import ScopeRef
from net_agent_harness.models.enums import TargetScope
from net_agent_harness.models.resources import DeviceResourceRef, SiteResourceRef
from net_agent_harness.orchestration.scope_validator import (
    ScopeValidationError,
    validate_target_scope,
)


def _target(name: str, site: str = "HQ") -> ResolvedTarget:
    return ResolvedTarget(name=name, site=site, role="switch", platform="mist", vendor="juniper")


class TestValidScopePassthrough:
    def test_device_scope_with_device_names(self) -> None:
        result = validate_target_scope(
            target_scope=TargetScope.device,
            scope_ref=ScopeRef(site="HQ", device_names=["sw1"]),
            resolved_targets=[_target("sw1")],
            target_resources=[DeviceResourceRef(device_name="sw1", site_name="HQ")],
        )
        assert result == TargetScope.device

    def test_site_scope_with_no_device_names(self) -> None:
        result = validate_target_scope(
            target_scope=TargetScope.site,
            scope_ref=ScopeRef(site="HQ", device_names=[]),
            resolved_targets=[_target("sw1"), _target("sw2")],
            target_resources=[SiteResourceRef(site_name="HQ")],
        )
        assert result == TargetScope.site


class TestScopeCorrection:
    def test_site_corrected_to_device_when_names_present(self) -> None:
        """Planner says site, but device_names are present → corrected to device."""
        result = validate_target_scope(
            target_scope=TargetScope.site,
            scope_ref=ScopeRef(site="HQ", device_names=["sw1"]),
            resolved_targets=[_target("sw1")],
            target_resources=[DeviceResourceRef(device_name="sw1", site_name="HQ")],
        )
        assert result == TargetScope.device

    def test_device_corrected_to_site_when_no_names(self) -> None:
        """Planner says device, but no device_names and site is set → corrected to site."""
        result = validate_target_scope(
            target_scope=TargetScope.device,
            scope_ref=ScopeRef(site="HQ", device_names=[]),
            resolved_targets=[_target("sw1"), _target("sw2")],
            target_resources=[SiteResourceRef(site_name="HQ")],
        )
        assert result == TargetScope.site

    def test_ambiguous_corrected_to_device_with_names(self) -> None:
        """Planner says ambiguous, but device_names present → corrected to device."""
        result = validate_target_scope(
            target_scope=TargetScope.ambiguous,
            scope_ref=ScopeRef(site="HQ", device_names=["sw1"]),
            resolved_targets=[_target("sw1")],
            target_resources=[DeviceResourceRef(device_name="sw1", site_name="HQ")],
        )
        assert result == TargetScope.device

    def test_no_site_no_names_becomes_ambiguous(self) -> None:
        """No site, no device names, no targets → ambiguous."""
        result = validate_target_scope(
            target_scope=TargetScope.device,
            scope_ref=ScopeRef(site=None, device_names=[]),
            resolved_targets=[],
            target_resources=[],
        )
        assert result == TargetScope.ambiguous

    def test_device_resource_implies_device_scope(self) -> None:
        """Device resource evidence should imply device scope."""
        result = validate_target_scope(
            target_scope=TargetScope.ambiguous,
            scope_ref=ScopeRef(site=None, device_names=[]),
            resolved_targets=[_target("sw1")],
            target_resources=[DeviceResourceRef(device_name="sw1", site_name="HQ")],
        )
        assert result == TargetScope.device

    def test_site_resource_implies_site_scope(self) -> None:
        """Site resource evidence should imply site scope when targets exist."""
        result = validate_target_scope(
            target_scope=TargetScope.ambiguous,
            scope_ref=ScopeRef(site=None, device_names=[]),
            resolved_targets=[_target("sw1"), _target("sw2")],
            target_resources=[SiteResourceRef(site_name="HQ")],
        )
        assert result == TargetScope.site


class TestScopeErrors:
    def test_device_scope_no_targets_raises(self) -> None:
        """Device names present but no targets resolved → error."""
        with pytest.raises(ScopeValidationError, match="no targets were resolved"):
            validate_target_scope(
                target_scope=TargetScope.device,
                scope_ref=ScopeRef(site="HQ", device_names=["sw1"]),
                resolved_targets=[],
                target_resources=[],
            )

    def test_site_present_no_targets_raises(self) -> None:
        """Site specified but no targets resolved → error."""
        with pytest.raises(ScopeValidationError, match="no targets resolved"):
            validate_target_scope(
                target_scope=TargetScope.site,
                scope_ref=ScopeRef(site="HQ", device_names=[]),
                resolved_targets=[],
                target_resources=[SiteResourceRef(site_name="HQ")],
            )
