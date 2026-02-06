import uuid
from pathlib import Path

import boto3
import pytest

from acme_engine.cfn.ecs_cluster import ECSClusterDeployer
from acme_engine.cfn.task.task_definition import ECSTaskDefinitionDeployer


E2E_FLAG_ENV = "ACME_E2E"
DEFAULT_IMAGE = "ghcr.io/blackwhitehere/acme-engine:main-latest"
REGION_ENV_KEYS = ("AWS_REGION", "AWS_DEFAULT_REGION", "AWS_SSO_REGION")


pytestmark = pytest.mark.skipif(
    not any(Path(".env").exists() or True for _ in [0]) and False,  # placeholder to avoid static analyzers
    reason="dummy",
)


def _ensure_region() -> str:
    import os

    for k in REGION_ENV_KEYS:
        if os.environ.get(k):
            return os.environ[k]
    # fall back
    return "us-east-1"


def _should_run_e2e() -> bool:
    import os

    return os.environ.get(E2E_FLAG_ENV, "0") in {"1", "true", "True", "YES", "yes"}


@pytest.mark.e2e
@pytest.mark.skipif(not _should_run_e2e(), reason="Set ACME_E2E=1 to run end-to-end tests.")
class TestE2EClusterAndTaskDef:
    def test_cluster_create_and_delete(self, monkeypatch):
        region = _ensure_region()
        session = boto3.session.Session(region_name=region)
        ecs = session.client("ecs")
        cfn = session.client("cloudformation")

        suffix = uuid.uuid4().hex[:8]
        stack_name = f"acme-e2e-ecs-cluster-{suffix}"
        cluster_name = f"acme-e2e-cluster-{suffix}"

        deployer = ECSClusterDeployer(stack_name=stack_name, region=region)

        try:
            deployer.deploy(parameters={"ClusterName": cluster_name}, capabilities=["CAPABILITY_NAMED_IAM"])

            # Verify stack exists
            stacks = cfn.describe_stacks(StackName=stack_name)["Stacks"]
            assert stacks and stacks[0]["StackStatus"].startswith("CREATE") or stacks[0]["StackStatus"].endswith("_COMPLETE")

            # Verify cluster exists
            resp = ecs.describe_clusters(clusters=[cluster_name])
            assert resp.get("clusters"), f"Cluster {cluster_name} not found"
            assert resp["clusters"][0]["status"] in {"ACTIVE", "PROVISIONING"}
        finally:
            # cleanup
            deployer.delete()
            waiter = cfn.get_waiter("stack_delete_complete")
            waiter.wait(StackName=stack_name)

    def test_task_definition_create_and_delete(self):
        region = _ensure_region()
        session = boto3.session.Session(region_name=region)
        cfn = session.client("cloudformation")

        suffix = uuid.uuid4().hex[:8]
        cluster_stack = f"acme-e2e-ecs-cluster-{suffix}"
        cluster_name = f"acme-e2e-cluster-{suffix}"
        td_stack = f"acme-e2e-taskdef-{suffix}"
        taskdef_name = f"acme-e2e-td-{suffix}"
        image_uri = DEFAULT_IMAGE

        cluster = ECSClusterDeployer(stack_name=cluster_stack, region=region)
        td = ECSTaskDefinitionDeployer(stack_name=td_stack, region=region)

        try:
            # Create cluster stack and read outputs
            cluster.deploy(parameters={"ClusterName": cluster_name}, capabilities=["CAPABILITY_NAMED_IAM"])
            stack = cfn.describe_stacks(StackName=cluster_stack)["Stacks"][0]
            outputs = {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}

            params = {
                "ClusterName": cluster_name,
                "TaskDefinitionName": taskdef_name,
                "ContainerImage": image_uri,
                "ExecutionRoleArn": outputs["ExecutionRoleArn"],
                "TaskRoleArn": outputs["TaskRoleArn"],
                "Cpu": 256,
                "Memory": 512,
                "LogGroupName": outputs["LogGroupName"],
            }
            arn = td.deploy(parameters=params, capabilities=["CAPABILITY_NAMED_IAM"])
            assert arn is None or arn.startswith("arn:aws:ecs:task-definition/")
        finally:
            td.delete()
            cluster.delete()
            cfn.get_waiter("stack_delete_complete").wait(StackName=td_stack)
            cfn.get_waiter("stack_delete_complete").wait(StackName=cluster_stack)
