import json
import time
import uuid
from pathlib import Path

import boto3
import pytest

from acme_engine.stepfn.compile import compile_step_function
from acme_engine.stepfn.deploy import StepFunctionDeployer

E2E_FLAG_ENV = "ACME_E2E"
REGION_ENV_KEYS = ("AWS_REGION", "AWS_DEFAULT_REGION", "AWS_SSO_REGION")
EXPECTED_OUTPUT_SUBSTR = "This is an example flow function."


def _parse_env_file(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def _ensure_env_and_credentials() -> tuple[str, str]:
    import os

    # Load .env into this process environment (non-destructive)
    env_vars = _parse_env_file(Path(__file__).resolve().parents[2] / ".env")
    for k, v in env_vars.items():
        os.environ.setdefault(k, v)

    # Ensure a region is present
    region = next((os.environ.get(k) for k in REGION_ENV_KEYS if os.environ.get(k)), None)
    if not region:
        raise RuntimeError(
            "No AWS region found. Set one of AWS_REGION, AWS_DEFAULT_REGION, or AWS_SSO_REGION in .env"
        )

    return region, os.environ.get("E2E_ECS_IMAGE_URI") or os.environ.get("ACME_E2E_ECS_IMAGE_URI") or "ghcr.io/blackwhitehere/acme-engine:main-latest"


def _discover_network(ec2):
    # Use default VPC
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}]).get("Vpcs", [])
    if not vpcs:
        raise RuntimeError("No default VPC found for ECS networking")
    vpc_id = vpcs[0]["VpcId"]

    # Subnets in default VPC
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]).get("Subnets", [])
    if not subnets:
        raise RuntimeError("No subnets found in default VPC")

    public_subnets = [s for s in subnets if s.get("MapPublicIpOnLaunch")]
    chosen = public_subnets or subnets
    subnet_ids = [s["SubnetId"] for s in chosen[:3]]  # up to 3 AZs

    # Default security group
    sgs = ec2.describe_security_groups(
        Filters=[{"Name": "group-name", "Values": ["default"]}, {"Name": "vpc-id", "Values": [vpc_id]}]
    ).get("SecurityGroups", [])
    if not sgs:
        raise RuntimeError("Default security group not found in default VPC")
    sg_id = sgs[0]["GroupId"]

    assign_public_ip = "ENABLED" if public_subnets else "DISABLED"
    return subnet_ids, sg_id, assign_public_ip


@pytest.mark.e2e
@pytest.mark.skipif(__import__("os").environ.get(E2E_FLAG_ENV, "0") not in {"1", "true", "True", "YES", "yes"}, reason="Set ACME_E2E=1 to run end-to-end tests.")
class TestE2EStepFunction:
    def test_compile_deploy_and_run(self, tmp_path: Path):
        region, image_uri = _ensure_env_and_credentials()
        session = boto3.session.Session(region_name=region)
        iam = session.client("iam")
        ecs = session.client("ecs")
        ec2 = session.client("ec2")
        logs = session.client("logs")
        sfn = session.client("stepfunctions")

        suffix = uuid.uuid4().hex[:8]
        cluster_name = f"acme-e2e-cluster-{suffix}"
        exec_role_name = f"acme-e2e-ecs-exec-role-{suffix}"
        sfn_role_name = f"acme-e2e-sfn-role-{suffix}"
    # state_machine_name intentionally omitted; we generate a unique name in the deployer
        log_group_name = f"/acme/e2e/{suffix}"
        stream_prefix = "acme-e2e"
        container_name = "app"

        exec_role_arn = None
        sfn_role_arn = None
        task_definition_arn = None
        state_machine_arn = None

        try:
            # Networking
            subnet_ids, sg_id, assign_public_ip = _discover_network(ec2)

            # IAM roles
            trust_exec = {
                "Version": "2012-10-17",
                "Statement": [
                    {"Effect": "Allow", "Principal": {"Service": "ecs-tasks.amazonaws.com"}, "Action": "sts:AssumeRole"}
                ],
            }
            exec_role_arn = iam.create_role(
                RoleName=exec_role_name, AssumeRolePolicyDocument=json.dumps(trust_exec), Description="E2E exec role"
            )["Role"]["Arn"]
            iam.attach_role_policy(
                RoleName=exec_role_name,
                PolicyArn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
            )
            time.sleep(8)
            trust_sfn = {
                "Version": "2012-10-17",
                "Statement": [
                    {"Effect": "Allow", "Principal": {"Service": "states.amazonaws.com"}, "Action": "sts:AssumeRole"}
                ],
            }
            sfn_role_arn = iam.create_role(
                RoleName=sfn_role_name, AssumeRolePolicyDocument=json.dumps(trust_sfn), Description="E2E sfn role"
            )["Role"]["Arn"]
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["ecs:RunTask", "ecs:StopTask", "ecs:DescribeTasks"],
                        "Resource": "*",
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "events:PutTargets",
                            "events:PutRule",
                            "events:DescribeRule",
                            "events:DeleteRule",
                            "events:RemoveTargets",
                        ],
                        "Resource": "*",
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["iam:PassRole"],
                        "Resource": "*",
                        "Condition": {"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}},
                    },
                ],
            }
            iam.put_role_policy(RoleName=sfn_role_name, PolicyName="AllowEcsRunTaskSync", PolicyDocument=json.dumps(policy))

            # Logs
            try:
                logs.create_log_group(logGroupName=log_group_name)
            except logs.exceptions.ResourceAlreadyExistsException:
                pass
            try:
                logs.put_retention_policy(logGroupName=log_group_name, retentionInDays=1)
            except Exception:
                pass

            # ECS cluster
            cluster_arn = ecs.create_cluster(clusterName=cluster_name)["cluster"]["clusterArn"]

            # Task definition
            td = ecs.register_task_definition(
                family=f"acme-e2e-family-{suffix}",
                networkMode="awsvpc",
                requiresCompatibilities=["FARGATE"],
                cpu="256",
                memory="512",
                executionRoleArn=exec_role_arn,
                containerDefinitions=[
                    {
                        "name": container_name,
                        "image": image_uri,
                        "essential": True,
                        "command": [
                            "python",
                            "-c",
                            "from example.flow import example_flow; example_flow()",
                        ],
                        "logConfiguration": {
                            "logDriver": "awslogs",
                            "options": {
                                "awslogs-group": log_group_name,
                                "awslogs-region": region,
                                "awslogs-stream-prefix": stream_prefix,
                            },
                        },
                    }
                ],
            )
            task_definition_arn = td["taskDefinition"]["taskDefinitionArn"]

            # Step Functions definition
            definition_path = Path(__file__).parent / f"def-{suffix}.json"
            compile_step_function(
                output_path=definition_path,
                state_machine_name=container_name,
                cluster=cluster_arn,
                task_definition=task_definition_arn,
                flow_path="example.flow:example_flow",
                subnets=subnet_ids,
                security_groups=[sg_id],
                launch_type="FARGATE",
            )

            sfd = StepFunctionDeployer(
                state_machine_name=f"acme-e2e-sm-{suffix}",
                definition_path=definition_path,
                role_arn=sfn_role_arn,
                region=region,
            )
            state_machine_arn = sfd.deploy()

            # Execute and wait
            exec_arn = sfn.start_execution(stateMachineArn=state_machine_arn, name=f"run-{suffix}")["executionArn"]
            deadline = time.time() + 600
            status = "RUNNING"
            output = None
            while time.time() < deadline:
                resp = sfn.describe_execution(executionArn=exec_arn)
                status = resp["status"]
                if status in ("SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"):
                    output = resp.get("output")
                    break
                time.sleep(3)

            assert status == "SUCCEEDED", f"State machine execution failed: {status}, output={output}"

            payload = json.loads(output) if output else {}
            tasks = payload.get("tasks", [])
            assert tasks, f"No tasks in output: {payload}"
            task_arn = tasks[0]["taskArn"]

            logs_client = logs
            log_stream = f"{stream_prefix}/{container_name}/{task_arn.split('/')[-1]}"

            # Poll logs for expected output
            deadline = time.time() + 300
            seen = ""
            next_token = None
            while time.time() < deadline:
                try:
                    kwargs = {"logGroupName": log_group_name, "logStreamName": log_stream, "startFromHead": True}
                    if next_token:
                        kwargs["nextToken"] = next_token
                    resp = logs_client.get_log_events(**kwargs)
                    next_token = resp.get("nextForwardToken")
                    messages = [e.get("message", "") for e in resp.get("events", [])]
                    if messages:
                        seen += "\n".join(messages) + "\n"
                        if EXPECTED_OUTPUT_SUBSTR in seen:
                            break
                except logs_client.exceptions.ResourceNotFoundException:
                    pass
                time.sleep(2)

            assert EXPECTED_OUTPUT_SUBSTR in seen
        finally:
            if state_machine_arn:
                try:
                    sfn.delete_state_machine(stateMachineArn=state_machine_arn)
                except Exception:
                    pass
            if task_definition_arn:
                try:
                    ecs.deregister_task_definition(taskDefinition=task_definition_arn)
                except Exception:
                    pass
            try:
                ecs.delete_cluster(cluster=cluster_name)
            except Exception:
                pass
            try:
                iam.delete_role_policy(RoleName=sfn_role_name, PolicyName="AllowEcsRunTaskSync")
            except Exception:
                pass
            try:
                iam.delete_role(RoleName=sfn_role_name)
            except Exception:
                pass
            try:
                iam.detach_role_policy(
                    RoleName=exec_role_name,
                    PolicyArn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
                )
            except Exception:
                pass
            try:
                iam.delete_role(RoleName=exec_role_name)
            except Exception:
                pass
            try:
                logs.delete_log_group(logGroupName=log_group_name)
            except Exception:
                pass
