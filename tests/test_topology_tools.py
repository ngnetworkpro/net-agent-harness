from net_agent_harness.tools.topology_tools import answer_topology_question


def test_answer_topology_question_for_known_device() -> None:
    result = answer_topology_question("What is connected to sw1?")
    assert "sw1" in result["answer"].lower()
    assert result["data"]["links"]
    assert result["data"]["links"][0]["target_device"] == "fw1"
