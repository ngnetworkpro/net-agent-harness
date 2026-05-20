from net_agent_harness.tools.ipam_tools import answer_ipam_question, find_assignment, find_prefix


def test_find_prefix_returns_result_for_seeded_prefix() -> None:
    result = find_prefix("10.10.21.0/24")
    assert result["found"] is True
    assert result["prefix"]["vlan_id"] == 21


def test_find_assignment_returns_result_for_seeded_ip() -> None:
    result = find_assignment("10.0.0.10")
    assert result["found"] is True
    assert result["assignment"]["device_name"] == "sw1"


def test_answer_ipam_question_handles_unknown_input() -> None:
    result = answer_ipam_question("Is anything assigned here?")
    assert "could not detect" in result["answer"].lower()
