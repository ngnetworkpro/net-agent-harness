from net_agent_harness.adapters.netbox_adapter import NetBoxAdapter
from net_agent_harness.tools.inventory_tools import _normalize_device, _normalize_interface, _normalize_ip


def test_netbox_adapter_init():
    adapter = NetBoxAdapter(
        base_url='https://netbox.example.com',
        token='secret-token',
        timeout_seconds=5,
        verify_tls=True,
    )
    assert adapter.base_url == 'https://netbox.example.com'
    assert adapter.timeout_seconds == 5
    assert adapter.verify_tls is True


def test_normalize_device():
    item = {
        'id': 10,
        'name': 'sw1',
        'site': {'name': 'HQ'},
        'status': {'value': 'active'},
        'role': {'name': 'access-switch'},
        'platform': {'name': 'iosxe'},
        'primary_ip4': {'address': '10.0.0.10/24'},
    }
    out = _normalize_device(item)
    assert out['name'] == 'sw1'
    assert out['primary_ip'] == '10.0.0.10/24'


def test_normalize_interface_and_ip():
    iface = {
        'id': 20,
        'name': 'Gig1/0/1',
        'type': {'label': '1000BASE-T'},
        'enabled': True,
        'mtu': 1500,
        'description': 'User port',
        'mode': {'value': 'access'},
        'untagged_vlan': {'vid': 220},
        'tagged_vlans': [{'vid': 221}, {'vid': 222}],
    }
    ip = {
        'id': 30,
        'address': '10.0.0.10/24',
        'family': {'value': 4},
        'status': {'value': 'active'},
        'dns_name': 'sw1.example.com',
        'assigned_object': {'name': 'Vlan220'},
    }
    iface_out = _normalize_interface(iface)
    ip_out = _normalize_ip(ip)
    assert iface_out['untagged_vlan'] == 220
    assert iface_out['tagged_vlans'] == [221, 222]
    assert ip_out['interface'] == 'Vlan220'
