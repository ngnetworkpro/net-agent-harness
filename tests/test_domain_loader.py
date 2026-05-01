from net_agent_harness.orchestration.domain_loader import load_domain_context

def test_load_vlan_domain_context():
    ctx = load_domain_context("vlan")
    
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
    ctx = load_domain_context("generic")
    
    assert ctx.domain == "generic"
    assert "No specific context available." in ctx.description
    
    # Core terms should still be present
    term_names = [t.name for t in ctx.terms]
    assert "intent" in term_names
    assert "no_op" in term_names
    
    # Domain-specific stuff should be empty
    assert len(ctx.intents) == 0
    assert len(ctx.examples) == 0
