from net_agent_harness.adapters.netbox_adapter import NetBoxAdapter
from net_agent_harness.tools.inventory_tools import _normalize_device, _normalize_interface, _normalize_ip, _normalize_resolved_target, _infer_vendor_from_platform
from net_agent_harness.models.enums import DeviceVendor


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


def test_netbox_adapter_get():
    from unittest.mock import patch

    adapter = NetBoxAdapter(
        base_url='https://netbox.example.com',
        token='secret-token',
        timeout_seconds=5,
        verify_tls=True,
    )

    with patch("httpx.Client.get") as mock_get:
        class MockResponse:
            def raise_for_status(self): pass
            def json(self): return {"count": 1, "results": [{"id": 1, "name": "sw1"}]}

        mock_get.return_value = MockResponse()

        res = adapter._get("/api/dcim/devices/")
        assert "results" in res
        assert res["results"][0]["name"] == "sw1"


def test_lookup_inventory_sync_netbox():
    from unittest.mock import patch
    from net_agent_harness.tools.inventory_tools import lookup_inventory_sync

    with patch("net_agent_harness.adapters.netbox_adapter.build_netbox_adapter_from_settings") as mock_builder:
        class MockAdapter:
            def get_devices(self, site=None, name=None):
                return {"count": 1, "results": [{"id": 1, "name": "sw1", "site": {"name": "HQ"}}]}

        mock_builder.return_value = MockAdapter()

        res = lookup_inventory_sync("netbox", site="HQ")
        assert res["source"] == "netbox"
        assert res["count"] == 1
        assert res["results"][0]["name"] == "sw1"


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


def test_infer_vendor_from_platform_known():
    assert _infer_vendor_from_platform("mist") == DeviceVendor.JUNIPER
    assert _infer_vendor_from_platform("MIST") == DeviceVendor.JUNIPER
    assert _infer_vendor_from_platform("ios") == DeviceVendor.CISCO
    assert _infer_vendor_from_platform("ios-xe") == DeviceVendor.CISCO
    assert _infer_vendor_from_platform("nxos") == DeviceVendor.CISCO
    assert _infer_vendor_from_platform("meraki") == DeviceVendor.MERAKI
    assert _infer_vendor_from_platform("eos") == DeviceVendor.ARISTA


def test_infer_vendor_from_platform_unknown():
    assert _infer_vendor_from_platform("unknown-platform") is None
    assert _infer_vendor_from_platform(None) is None
    assert _infer_vendor_from_platform("") is None


def test_normalize_resolved_target_uses_explicit_vendor():
    target = _normalize_resolved_target({
        "name": "sw1",
        "platform": "ios",
        "vendor": "juniper",
    })
    # Explicit vendor takes precedence over platform inference
    assert target.vendor == DeviceVendor.JUNIPER


def test_normalize_resolved_target_infers_vendor_from_platform():
    target = _normalize_resolved_target({
        "name": "sw1",
        "platform": "mist",
    })
    # vendor absent → inferred from platform
    assert target.vendor == DeviceVendor.JUNIPER


def test_normalize_resolved_target_vendor_none_when_platform_unknown():
    target = _normalize_resolved_target({
        "name": "sw1",
        "platform": "custom-os",
    })
    assert target.vendor is None


def test_normalize_resolved_target_vendor_none_when_no_platform():
    target = _normalize_resolved_target({"name": "sw1"})
    assert target.vendor is None
