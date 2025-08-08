import json
from pathlib import Path

from acme_engine.stepfn.compile import compile_step_function


def test_compile_generates_valid_definition(tmp_path: Path):
    out = tmp_path / "def.json"
    compile_step_function(
        output_path=out,
        state_machine_name="test-sm",
        cluster="my-cluster",
        task_definition="my-task:1",
        flow_path="pkg.mod:func",
        subnets=["subnet-1"],
        security_groups=["sg-1"],
        args=["a", 1],
        kwargs={"k": "v"},
    )
    data = json.loads(out.read_text())
    assert data["StartAt"] == "RunPrefectFlow"
    params = data["States"]["RunPrefectFlow"]["Parameters"]
    assert params["Cluster"] == "my-cluster"
    cmd = params["Overrides"]["ContainerOverrides"][0]["Command"]
    # Ensure runner is used and args/kwargs are present as JSON
    assert cmd[:4] == ["python", "-m", "acme_engine.runtime.run_flow", "--target"]
    assert "--args" in cmd and "--kwargs" in cmd
