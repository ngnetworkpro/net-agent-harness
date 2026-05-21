"""scope_validator.py — Validate target_scope consistency.

Ensures the ``target_scope`` label on a plan artifact matches the evidence
from the scope ref, resolved targets, and target resources.

This is a deterministic correction step: when the planner says ``device``
but the resolution evidence says ``site`` (or vice versa), the validator
corrects the label and logs a warning.  If the scope is irreconcilable
(e.g., scope claims ``device`` but no targets resolved), a
``ScopeValidationError`` is raised.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..models.common import ScopeRef
from ..models.enums import TargetScope

if TYPE_CHECKING:
    from ..models.changes import ResolvedTarget
    from ..models.resources import ResourceRef

logger = logging.getLogger(__name__)


class ScopeValidationError(ValueError):
    """Raised when target_scope is irreconcilably inconsistent."""


def validate_target_scope(
    target_scope: TargetScope,
    scope_ref: ScopeRef,
    resolved_targets: list[ResolvedTarget],
    target_resources: list[ResourceRef],
) -> TargetScope:
    """Validate and optionally correct ``target_scope``.

    Decision matrix
    ---------------
    +-----------------------+-------------+-----------------+-------------------+
    | scope_ref.device_names| scope.site  | resolved_targets| Expected scope    |
    +-----------------------+-------------+-----------------+-------------------+
    | ["sw1"]               | "HQ"        | [sw1]           | device            |
    | []                    | "HQ"        | [sw1, sw2]      | site              |
    | []                    | None        | []              | ambiguous         |
    | ["sw1"]               | "HQ"        | []              | ERROR             |
    +-----------------------+-------------+-----------------+-------------------+

    Parameters
    ----------
    target_scope:
        The scope label produced by the planner.
    scope_ref:
        The planner's ``ScopeRef`` containing site, device_names, etc.
    resolved_targets:
        Devices resolved from inventory by orchestration.
    target_resources:
        Typed resource refs from the merged artifact.

    Returns
    -------
    TargetScope
        The validated (and possibly corrected) scope label.

    Raises
    ------
    ScopeValidationError
        If the scope is irreconcilably inconsistent.
    """
    has_device_names = bool(scope_ref.device_names)
    has_site = scope_ref.site is not None
    has_targets = bool(resolved_targets)

    # Determine expected scope from the evidence
    if has_device_names:
        expected = TargetScope.device
    elif has_site and has_targets:
        expected = TargetScope.site
    elif has_site and not has_targets:
        # Site was named but no devices resolved — this is an error condition.
        # (The caller should have already blocked on empty resolved_targets,
        # but we validate here for safety.)
        raise ScopeValidationError(
            f"Site '{scope_ref.site}' specified but no targets resolved from inventory. "
            f"Cannot determine target scope."
        )
    else:
        expected = TargetScope.ambiguous

    # Validate: device scope with no resolved targets is always an error
    if expected == TargetScope.device and not has_targets:
        raise ScopeValidationError(
            f"Scope specifies device names {scope_ref.device_names} "
            f"but no targets were resolved from inventory."
        )

    # Correct if needed
    if target_scope != expected:
        logger.warning(
            "target_scope corrected from '%s' to '%s' "
            "(device_names=%s, site=%s, resolved_targets=%d)",
            target_scope.value,
            expected.value,
            scope_ref.device_names,
            scope_ref.site,
            len(resolved_targets),
        )
        return expected

    return target_scope
