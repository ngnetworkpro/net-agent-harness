from net_agent_harness.orchestration.intent_router import route_intent

def test_route_intent_vlan():
    assert route_intent("Add VLAN 200 to trunk port Gi0/1 on sw1 at HQ") == "vlan"
    assert route_intent("Make sure VLAN 10 is on all access ports at Branch1") == "vlan"

def test_route_intent_acl():
    assert route_intent("permit ip any any") == "acl"
    assert route_intent("add a firewall rule to block ssh") == "acl"

def test_route_intent_routing():
    assert route_intent("add static route to 10.0.0.0/8 via 192.168.1.1") == "routing"

def test_route_intent_wireless():
    assert route_intent("create a new ssid called corp-guest") == "wireless"

def test_route_intent_generic():
    assert route_intent("fix the thing on sw1") == "generic"
