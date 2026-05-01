from net_agent_harness.orchestration.intent_router import route_intent

def test_route_intent_vlan():
    res1 = route_intent("Add VLAN 200 to trunk port Gi0/1 on sw1 at HQ")
    assert res1.domain == "vlan"
    assert not res1.ambiguous

    res2 = route_intent("Make sure VLAN 10 is on all access ports at Branch1")
    assert res2.domain == "vlan"
    assert not res2.ambiguous

def test_route_intent_acl():
    res1 = route_intent("permit ip any any")
    assert res1.domain == "acl"

    res2 = route_intent("add a firewall rule to block ssh")
    assert res2.domain == "acl"

def test_route_intent_routing():
    res1 = route_intent("add static route to 10.0.0.0/8 via 192.168.1.1")
    assert res1.domain == "routing"

def test_route_intent_wireless():
    res1 = route_intent("create a new ssid called corp-guest")
    assert res1.domain == "wireless"

def test_route_intent_generic():
    res1 = route_intent("fix the thing on sw1")
    assert res1.domain == "generic"
    assert res1.ambiguous
    assert res1.confidence == 0.0
