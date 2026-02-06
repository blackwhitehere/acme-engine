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
    env = params["Overrides"]["ContainerOverrides"][0]["Environment"]
    # Ensure environment variables include target and args/kwargs as JSON
    env_map = {e["Name"]: e["Value"] for e in env}
    assert env_map["AE_TARGET"] == "pkg.mod:func"
    assert json.loads(env_map["AE_ARGS_JSON"]) == ["a", 1]
    assert json.loads(env_map["AE_KWARGS_JSON"]) == {"k": "v"}
