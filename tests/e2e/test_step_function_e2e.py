import os
import json
import time
import uuid
import subprocess
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
REFRESH_SCRIPT = PROJECT_ROOT / "admin" / "refresh_credentials.sh"
EXPECTED_OUTPUT_SUBSTR = "This is an example flow function."
REGION_ENV_KEYS = ("AWS_REGION", "AWS_DEFAULT_REGION", "AWS_SSO_REGION")
ECS_IMAGE_ENV_KEYS = ("E2E_ECS_IMAGE_URI", "ACME_E2E_ECS_IMAGE_URI")


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
    # Load .env into this process environment (non-destructive)
    env_vars = _parse_env_file(ENV_PATH)
    for k, v in env_vars.items():
        os.environ.setdefault(k, v)

    # Ensure a region is present
    region = next((os.environ.get(k) for k in REGION_ENV_KEYS if os.environ.get(k)), None)
    if not region:
        raise RuntimeError("No AWS region found. Set one of AWS_REGION, AWS_DEFAULT_REGION, or AWS_SSO_REGION in .env")

    # Ensure an ECS image URI is present
    image_uri = next((os.environ.get(k) for k in ECS_IMAGE_ENV_KEYS if os.environ.get(k)), None)
    if not image_uri:
        raise RuntimeError(
            "No ECS image URI found. Set E2E_ECS_IMAGE_URI (or ACME_E2E_ECS_IMAGE_URI) in .env to a Python-capable image containing your code."
        )

    # Refresh SSO credentials via provided script
    subprocess.run(["bash", "-lc", f'cd "{PROJECT_ROOT}" && "{REFRESH_SCRIPT}"'], check=True)
    return region, image_uri


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


def _create_iam_role(iam, role_name: str, trust: dict) -> str:
    try:
        arn = iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=json.dumps(trust), Description="E2E role")[
            "Role"
        ]["Arn"]
        return arn
    except ClientError as e:
        raise RuntimeError(f"Failed to create role {role_name}: {e}")


def _create_ecs_execution_role(iam, name: str) -> str:
    trust = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": "ecs-tasks.amazonaws.com"}, "Action": "sts:AssumeRole"}],
    }
    arn = _create_iam_role(iam, name, trust)
    iam.attach_role_policy(RoleName=name, PolicyArn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy")
    return arn


def _create_sfn_role(iam, name: str, pass_role_arns: list[str]) -> str:
    trust = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": "states.amazonaws.com"}, "Action": "sts:AssumeRole"}],
    }
    arn = _create_iam_role(iam, name, trust)
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
                "Action": ["events:PutTargets", "events:PutRule", "events:DescribeRule", "events:DeleteRule", "events:RemoveTargets"],
                "Resource": "*",
            },
            {
                "Effect": "Allow",
                "Action": ["iam:PassRole"],
                "Resource": pass_role_arns,
                "Condition": {"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}},
            },
        ],
    }
    iam.put_role_policy(RoleName=name, PolicyName="AllowEcsRunTaskSync", PolicyDocument=json.dumps(policy))
    return arn


def _create_log_group(logs, name: str, retention_days: int = 1):
    try:
        logs.create_log_group(logGroupName=name)
    except ClientError as e:
        code = getattr(e, "response", {}).get("Error", {}).get("Code")
        if code != "ResourceAlreadyExistsException":
            raise
    try:
        logs.put_retention_policy(logGroupName=name, retentionInDays=retention_days)
    except ClientError:
        pass


def _register_task_definition(ecs, region: str, image_uri: str, exec_role_arn: str, log_group_name: str, stream_prefix: str) -> str:
    container_name = "app"
    td = ecs.register_task_definition(
        family=f"acme-e2e-family-{uuid.uuid4().hex[:8]}",
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
                "command": ["python", "-c", "from example.flow import example_flow; example_flow()"],
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
    return td["taskDefinition"]["taskDefinitionArn"]


def _get_log_stream_name(stream_prefix: str, container_name: str, task_arn: str) -> str:
    # ecs task id is the last token of the task arn after '/'
    task_id = task_arn.split("/")[-1]
    return f"{stream_prefix}/{container_name}/{task_id}"


def _wait_for_log_and_validate(logs, log_group: str, log_stream: str, expected_substring: str, timeout_sec: int = 300):
    deadline = time.time() + timeout_sec
    next_token = None
    seen = ""
    while time.time() < deadline:
        try:
            kwargs = {"logGroupName": log_group, "logStreamName": log_stream, "startFromHead": True}
            if next_token:
                kwargs["nextToken"] = next_token
            resp = logs.get_log_events(**kwargs)
            next_token = resp.get("nextForwardToken")
            messages = [e.get("message", "") for e in resp.get("events", [])]
            if messages:
                seen += "\n".join(messages) + "\n"
                if expected_substring in seen:
                    return True
        except ClientError:
            pass  # stream may not exist yet
        time.sleep(2)
    raise AssertionError(f"Expected output to contain '{expected_substring}', but did not find it in logs.\nCollected logs:\n{seen}")


def main():
    region, image_uri = _ensure_env_and_credentials()

    session = boto3.session.Session(region_name=region)
    iam = session.client("iam")
    ecs = session.client("ecs")
    ec2 = session.client("ec2")
    logs = session.client("logs")
    sfn = session.client("stepfunctions")
    sts = session.client("sts")

    account_id = sts.get_caller_identity()["Account"]

    suffix = uuid.uuid4().hex[:8]
    cluster_name = f"acme-e2e-cluster-{suffix}"
    exec_role_name = f"acme-e2e-ecs-exec-role-{suffix}"
    sfn_role_name = f"acme-e2e-sfn-role-{suffix}"
    state_machine_name = f"acme-e2e-state-machine-{suffix}"
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
        exec_role_arn = _create_ecs_execution_role(iam, exec_role_name)
        # Give IAM a moment to propagate
        time.sleep(8)
        sfn_role_arn = _create_sfn_role(iam, sfn_role_name, [exec_role_arn])
        time.sleep(5)

        # Logs
        _create_log_group(logs, log_group_name, retention_days=1)

        # ECS cluster
        cluster_arn = ecs.create_cluster(clusterName=cluster_name)["cluster"]["clusterArn"]

        # Task definition
        task_definition_arn = _register_task_definition(
            ecs, region=region, image_uri=image_uri, exec_role_arn=exec_role_arn, log_group_name=log_group_name, stream_prefix=stream_prefix
        )

        # Step Functions definition
        definition = {
            "Comment": "Run ECS Fargate task to execute example flow",
            "StartAt": "RunEcsTask",
            "States": {
                "RunEcsTask": {
                    "Type": "Task",
                    "Resource": "arn:aws:states:::ecs:runTask.sync",
                    "Parameters": {
                        "Cluster": cluster_arn,
                        "TaskDefinition": task_definition_arn,
                        "LaunchType": "FARGATE",
                        "NetworkConfiguration": {
                            "AwsvpcConfiguration": {
                                "Subnets": subnet_ids,
                                "SecurityGroups": [sg_id],
                                "AssignPublicIp": assign_public_ip,
                            }
                        },
                        "Overrides": {"ContainerOverrides": [{"Name": container_name}]},
                    },
                    "End": True,
                }
            },
        }

        state_machine_arn = sfn.create_state_machine(
            name=state_machine_name, definition=json.dumps(definition), roleArn=sfn_role_arn, type="STANDARD"
        )["stateMachineArn"]

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

        if status != "SUCCEEDED":
            raise RuntimeError(f"State machine execution did not succeed. Status={status} Output={output}")

        payload = json.loads(output) if output else {}
        # ECS runTask.sync result mirrors ECS API response
        tasks = payload.get("tasks", [])
        if not tasks:
            raise RuntimeError(f"No tasks returned from ECS runTask. Full output={payload}")
        task_arn = tasks[0]["taskArn"]

        # Derive log stream and validate output
        log_stream = _get_log_stream_name(stream_prefix, container_name, task_arn)
        _wait_for_log_and_validate(logs, log_group_name, log_stream, EXPECTED_OUTPUT_SUBSTR, timeout_sec=300)

        print("E2E success: output validated from ECS task logs.")
    finally:
        # Cleanup in reverse order
        if state_machine_arn:
            try:
                sfn.delete_state_machine(stateMachineArn=state_machine_arn)
            except ClientError:
                pass
        if task_definition_arn:
            try:
                ecs.deregister_task_definition(taskDefinition=task_definition_arn)
            except ClientError:
                pass
        try:
            ecs.delete_cluster(cluster=cluster_name)
        except ClientError:
            pass
        try:
            iam.delete_role_policy(RoleName=sfn_role_name, PolicyName="AllowEcsRunTaskSync")
        except ClientError:
            pass
        try:
            iam.delete_role(RoleName=sfn_role_name)
        except ClientError:
            pass
        try:
            iam.detach_role_policy(
                RoleName=exec_role_name,
                PolicyArn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
            )
        except ClientError:
            pass
        try:
            iam.delete_role(RoleName=exec_role_name)
        except ClientError:
            pass
        try:
            logs.delete_log_group(logGroupName=log_group_name)
        except ClientError:
            pass


if __name__ == "__main__":
    main()
