from pydantic_ai import Agent, RunContext
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.output import NativeOutput
from pydantic_ai.providers.ollama import OllamaProvider

from ..config import settings
from ..models.changes import PlannedChange
from ..orchestration.run_context import RunContextData
from ..tools.inventory_tools import lookup_inventory, resolve_device_target, resolve_site_targets
from ..tools.vlan_state import compute_vlan_diff

model = OllamaModel(
    settings.ollama_model,
    provider=OllamaProvider(base_url="http://localhost:11434/v1"),
)

change_planner = Agent(
    model,
    deps_type=RunContextData,
    output_type=NativeOutput(PlannedChange),
    retries=2,
)

@change_planner.system_prompt
def planner_system_prompt(ctx: RunContext[RunContextData]) -> str:
    """Generate the system prompt dynamically using the resolved domain context."""
    
    # Static preamble (rules of engagement)
    preamble = [
        "You are a network change planner.",
        "Return only valid structured output matching the schema.",
        "Do not use placeholder values such as 'string' or 'unknown'.",
        "If a field is not known and the schema allows it, use null or an empty list.",
        "Write requested_change.summary as a short human-readable sentence.",
        "Write requested_change.intent in plain English and preserve important details from the user's request, including VLAN IDs, device names, and site names.",
        "Do not convert intent into a slug, identifier, or code-like label.",
        "Extract explicit scope details from the request, including site names, device names, and device roles when present.",
        "Always call an inventory tool when a site or device name is known.",
        "Populate resolved_targets only with devices returned from inventory tools.",
        "Do not invent targets.",
        "If inventory returns no matching targets, set clarifications_needed to explain why.",
        "Classify target_scope as device, site, or ambiguous based on what can be resolved.",
        "If the user says 'sw1 at HQ', call get_device_target('HQ', 'sw1') and use the result.",
        "If the user says 'site HQ', call get_site_targets('HQ') and use the result.",
        "If the request cannot be safely targeted, target_scope should be ambiguous and clarifications_needed should explain what is missing.",
        "Use the inventory tool when the site is known.",
        "Do not invent devices outside tool results.",
        "Always return a rollback_plan object.",
        "Keep assumptions and rollback steps concise and operationally realistic.",
        # No-op evaluation rules
        "For any VLAN provisioning request, always call evaluate_vlan_intent after resolving the target device. Populate plan_decision from its result.",
        "If plan_decision.decision is no_op, set risk to low and leave resolved_targets empty — no config changes are needed and none should be rendered.",
        "If plan_decision.decision is blocked, set clarifications_needed to explain the blocker and do not proceed to rendering."
    ]
    
    parts = [" ".join(preamble)]
    
    # Inject domain context if available
    if ctx.deps.domain_context:
        parts.append(ctx.deps.domain_context.render_prompt_block())
        
    return "\n\n".join(parts)


@change_planner.output_validator
async def _enforce_plan_decision(
    ctx: RunContext[RunContextData], output: PlannedChange
) -> PlannedChange:
    """Deterministically enforce the consequences of plan_decision.

    The LLM may produce a correct ``plan_decision`` but neglect to apply its
    implications to the rest of the output (e.g. leaving ``resolved_targets``
    populated on a no_op, or leaving ``clarifications_needed`` empty on a
    blocked decision).  This validator corrects both cases in code so the
    downstream pipeline always sees a consistent artifact.
    """
    from ..models.changes import PlanDecisionType

    if output.plan_decision is None:
        return output

    decision = output.plan_decision.decision
    reason = output.plan_decision.reason

    if decision == PlanDecisionType.NO_OP:
        # Nothing needs rendering — clear targets so ensure_renderable
        # (and any other consumers) cannot accidentally proceed.
        output.resolved_targets = []
        output.clarifications_needed = [
            f"[no_op] {reason}"
        ]

    elif decision == PlanDecisionType.BLOCKED:
        # Ensure the reason surfaces as a clarification so the CLI surfaces
        # it clearly, regardless of what the LLM put in clarifications_needed.
        blocker_note = f"[blocked] {reason}"
        if blocker_note not in output.clarifications_needed:
            output.clarifications_needed = [blocker_note] + [
                c for c in output.clarifications_needed
                if not c.startswith("[blocked]")
            ]

    return output




@change_planner.tool
async def get_inventory(ctx: RunContext[RunContextData], site: str):
    return lookup_inventory(ctx, site=site)

@change_planner.tool
async def get_site_targets(ctx: RunContext[RunContextData], site: str):
    return resolve_site_targets(ctx, site=site)


@change_planner.tool
async def get_device_target(ctx: RunContext[RunContextData], site: str | None, device_name: str):
    return resolve_device_target(ctx, site=site, device_name=device_name)


@change_planner.tool
async def evaluate_vlan_intent(
    ctx: RunContext[RunContextData],
    site: str,
    device_name: str,
    vlan_id: int,
    target_interfaces: list[str],
    mode: str = "trunk",
    vlan_name: str | None = None,
) -> dict:
    """Evaluate whether a VLAN provisioning intent is already satisfied on a device.

    Call this after resolving the target device from inventory.  The result is a
    PlanDecision dict — decision (apply | no_op | blocked), reason, and diff — that
    should be placed verbatim into plan_decision on the PlannedChange output.

    Parameters
    ----------
    site:
        Site name used to look up the device's full inventory snapshot.
    device_name:
        Exact device name as returned by the inventory tool.
    vlan_id:
        VLAN ID the request wants to provision.
    target_interfaces:
        Interface names the VLAN should be present on.
    mode:
        ``"trunk"`` (default) or ``"access"``.
    vlan_name:
        Optional human-readable VLAN label; used only in reason strings.
    """
    from ..adapters.mock_inventory_adapter import get_inventory_for_site

    snapshot = get_inventory_for_site(run_id=ctx.deps.run_id, site=site)
    device = next((d for d in snapshot.devices if d.name == device_name), None)

    if device is None:
        return {
            "decision": "blocked",
            "reason": (
                f"Device '{device_name}' was not found in the inventory snapshot "
                f"for site '{site}'. Verify the device name and site."
            ),
            "diff": {"vlans_to_create": [], "ports_to_update": []},
        }

    return compute_vlan_diff(
        intent={
            "vlan_id": vlan_id,
            "target_interfaces": target_interfaces,
            "mode": mode,
            "vlan_name": vlan_name,
        },
        current_state=device,
    )