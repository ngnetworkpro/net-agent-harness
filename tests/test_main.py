import pytest
import typer

from net_agent_harness.main import show_run


def test_show_run_rejects_invalid_run_id():
    with pytest.raises(typer.BadParameter, match="Invalid run_id"):
        show_run("../../etc")
