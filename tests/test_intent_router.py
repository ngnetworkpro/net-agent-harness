from net_agent_harness.orchestration.intent_router import route_intent
from net_agent_harness.models.enums import NetworkDomain

def test_route_intent_vlan():
    res1 = route_intent("Add VLAN 200 to trunk port Gi0/1 on sw1 at HQ")
    assert res1.domain == NetworkDomain.VLAN
    assert not res1.ambiguous

    res2 = route_intent("Make sure VLAN 10 is on all access ports at Branch1")
    assert res2.domain == NetworkDomain.VLAN
    assert not res2.ambiguous

def test_route_intent_acl():
    res1 = route_intent("permit ip any any")
    assert res1.domain == NetworkDomain.ACL

    res2 = route_intent("add a firewall rule to block ssh")
    assert res2.domain == NetworkDomain.ACL

def test_route_intent_routing():
    res1 = route_intent("add static route to 10.0.0.0/8 via 192.168.1.1")
    assert res1.domain == NetworkDomain.ROUTING

def test_route_intent_wireless():
    res1 = route_intent("create a new ssid called corp-guest")
    assert res1.domain == NetworkDomain.WIRELESS

def test_route_intent_generic():
    res1 = route_intent("fix the thing on sw1")
    assert res1.domain == NetworkDomain.OTHER
    assert res1.ambiguous
    assert res1.confidence == 0.0
