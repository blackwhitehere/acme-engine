from unittest.mock import Mock

from acme_engine.cfn.ecs_cluster import (
    ECSClusterDeployer,
    _build_parameter_overrides,
)


def test_build_parameter_overrides_handles_lists():
    params = {
        "ClusterName": "demo",
        "VpcId": "vpc-123",
        "SubnetIds": ["subnet-a", "subnet-b"],
    }
    toks = _build_parameter_overrides(params)
    assert "ParameterKey=SubnetIds,ParameterValue=subnet-a,subnet-b" in toks
    assert "ParameterKey=VpcId,ParameterValue=vpc-123" in toks


def test_deploy_uses_env_when_missing_params(monkeypatch):
    # Arrange env
    monkeypatch.setenv("ACME_VPC_ID", "vpc-env")
    monkeypatch.setenv("ACME_SUBNET_IDS", "subnet-1, subnet-2")

    # Mock subprocess.run to capture command
    calls = {}

    def fake_run(cmd, check):
        calls["cmd"] = cmd
        return Mock()

    monkeypatch.setattr("subprocess.run", fake_run)

    d = ECSClusterDeployer(stack_name="stack", region="us-east-1")
    d.deploy(parameters={"ClusterName": "demo"}, capabilities=["CAPABILITY_IAM"])  # no VpcId/SubnetIds given

    cmd = calls["cmd"]
    # Basic shape
    assert cmd[:4] == ["aws", "cloudformation", "deploy", "--template-file"]
    # Ensure our environment-derived params appear
    s = " ".join(cmd)
    assert "ParameterKey=VpcId,ParameterValue=vpc-env" in s
    assert "ParameterKey=SubnetIds,ParameterValue=subnet-1,subnet-2" in s


def test_deploy_discovers_when_env_missing(monkeypatch):
    # Ensure env vars are not set
    monkeypatch.delenv("ACME_VPC_ID", raising=False)
    monkeypatch.delenv("ACME_SUBNET_IDS", raising=False)

    # Fake boto3 session and discovery
    session = Mock()
    ec2 = session.client.return_value

    ec2.describe_vpcs.return_value = {"Vpcs": [{"VpcId": "vpc-xyz"}]}
    ec2.describe_subnets.return_value = {
        "Subnets": [
            {"SubnetId": "sub-1", "MapPublicIpOnLaunch": True},
            {"SubnetId": "sub-2", "MapPublicIpOnLaunch": False},
        ]
    }

    calls = {}

    def fake_run(cmd, check):
        calls["cmd"] = cmd
        return Mock()

    monkeypatch.setattr("subprocess.run", fake_run)

    d = ECSClusterDeployer(stack_name="stack", region="us-east-1")
    d.deploy(parameters={"ClusterName": "demo"}, aws_session=session)

    s = " ".join(calls["cmd"]) if calls.get("cmd") else ""
    assert "ParameterKey=VpcId,ParameterValue=vpc-xyz" in s
    # Prefers public subnets; given only sub-1 is public, expect just that one
    assert "ParameterKey=SubnetIds,ParameterValue=sub-1" in s
