import pytest
from net_agent_harness.orchestration.domain_loader import load_domain_context, load_render_context, DomainLoadError
from net_agent_harness.models.enums import NetworkDomain

def test_load_vlan_domain_context():
    ctx = load_domain_context(NetworkDomain.VLAN)
    
    assert ctx.domain == "vlan"
    assert "VLAN provisioning" in ctx.description
    
    # Check core terms are merged
    term_names = [t.name for t in ctx.terms]
    assert "intent" in term_names
    assert "no_op" in term_names
    
    # Check domain terms are merged
    assert "vlan_id" in term_names
    assert "trunk" in term_names
    
    # Check intents
    intent_names = [i.name for i in ctx.intents]
    assert "provision_vlan_trunk" in intent_names
    
    # Check examples
    assert len(ctx.examples) > 0
    assert "Add VLAN 200 to trunk port Gi0/1 on sw1 at HQ" in [e.user for e in ctx.examples]

def test_load_generic_domain_context():
    with pytest.raises(DomainLoadError):
        load_domain_context(NetworkDomain.OTHER)


def test_load_domain_context_returns_isolated_copy():
    first = load_domain_context(NetworkDomain.VLAN)
    original_len = len(first.terms)
    first.terms.append(first.terms[0])

    second = load_domain_context(NetworkDomain.VLAN)
    assert len(second.terms) == original_len


# ---------------------------------------------------------------------------
# load_render_context tests
# ---------------------------------------------------------------------------

class TestLoadRenderContext:
    def test_vlan_returns_expected_keys(self):
        data = load_render_context("vlan")
        assert "preamble" in data
        assert "summary_format_rules" in data
        assert "snippet_examples" in data

    def test_vlan_preamble_non_empty(self):
        data = load_render_context("vlan")
        assert data["preamble"].strip()

    def test_vlan_summary_format_rules_non_empty(self):
        data = load_render_context("vlan")
        assert data["summary_format_rules"].strip()

    def test_vlan_snippet_examples_is_list(self):
        data = load_render_context("vlan")
        assert isinstance(data["snippet_examples"], list)

    def test_vlan_snippet_examples_non_empty(self):
        data = load_render_context("vlan")
        assert len(data["snippet_examples"]) > 0

    def test_unknown_domain_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="unknown_domain"):
            load_render_context("unknown_domain")

    def test_return_type_is_dict(self):
        data = load_render_context("vlan")
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Assembled system prompt tests
# ---------------------------------------------------------------------------

class TestAssembledVlanSystemPrompt:
    """Verify that the refactored render_system_prompt assembles correctly."""

    @pytest.fixture
    def vlan_prompt(self):
        from net_agent_harness.agents.config_render_agent import render_system_prompt
        from net_agent_harness.models.artifacts import (
            RenderRequest,
            VlanRenderPayload,
            VlanRenderOp,
            RenderTarget,
            OperationType,
        )
        from net_agent_harness.models.enums import NetworkDomain

        payload = VlanRenderPayload(
            vlan_ops=[
                VlanRenderOp(
                    target=RenderTarget(name="sw1"),
                    vlan_id=10,
                    operation=OperationType.ENSURE_PRESENT,
                )
            ]
        )
        req = RenderRequest(
            domain=NetworkDomain.VLAN,
            intent_type="set_access_vlan",
            payload=payload,
        )

        class DummyCtx:
            deps = req

        return render_system_prompt(DummyCtx())

    def test_prompt_contains_vlan_preamble(self, vlan_prompt):
        assert "VLAN" in vlan_prompt

    def test_prompt_contains_vlan_specific_intro(self, vlan_prompt):
        assert "specialized in VLAN operations" in vlan_prompt

    def test_prompt_does_not_contain_routing_text(self, vlan_prompt):
        assert "specialized in routing operations" not in vlan_prompt

    def test_prompt_contains_render_payload_section(self, vlan_prompt):
        assert "## Render Payload" in vlan_prompt

    def test_prompt_contains_vlan_ops_from_describe_ops(self, vlan_prompt):
        assert "VLAN Operations:" in vlan_prompt
        assert "VLAN 10" in vlan_prompt

    def test_prompt_contains_summary_format_rules(self, vlan_prompt):
        # summary_format_rules from YAML should mention VLAN creation format
        assert "Rendered VLAN" in vlan_prompt

    def test_prompt_contains_output_format_section(self, vlan_prompt):
        assert "## Output Format" in vlan_prompt

    def test_prompt_contains_input_contract_section(self, vlan_prompt):
        assert "## Input Contract" in vlan_prompt
        assert "domain: vlan" in vlan_prompt
        assert "intent_type: set_access_vlan" in vlan_prompt

    def test_prompt_contains_allowed_vlans_mode_rule(self, vlan_prompt):
        assert "allowed_vlans_mode" in vlan_prompt
