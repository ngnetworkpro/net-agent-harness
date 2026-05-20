from net_agent_harness.models.enums import Capability
from net_agent_harness.orchestration.read_only_answer import build_read_only_answer


def test_build_read_only_answer_for_topology() -> None:
    answer = build_read_only_answer(
        question="What is connected to sw1?",
        capability=Capability.TOPOLOGY,
        inventory_source="mock",
    )
    assert answer.capability is Capability.TOPOLOGY
    assert "sw1" in answer.answer.lower()
    assert answer.evidence == ["inventory:mock"]
    assert answer.missing_data == []
    assert answer.confidence == 1.0


def test_build_read_only_answer_for_ipam() -> None:
    answer = build_read_only_answer(
        question="Is 10.10.21.0/24 assigned?",
        capability=Capability.IPAM,
        inventory_source="mock",
    )
    assert answer.capability is Capability.IPAM
    assert "10.10.21.0/24" in answer.answer
    assert answer.evidence == ["ipam:mock"]
    assert answer.missing_data == []
    assert answer.confidence == 1.0
