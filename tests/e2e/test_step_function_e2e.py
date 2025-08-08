import os
import io
import json
import time
import uuid
import zipfile
import shutil
import subprocess
import tempfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
REFRESH_SCRIPT = PROJECT_ROOT / "admin" / "refresh_credentials.sh"
EXPECTED_OUTPUT_SUBSTR = "This is an example flow function."
REGION_ENV_KEYS = ("AWS_REGION", "AWS_DEFAULT_REGION", "AWS_SSO_REGION")


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


def _ensure_env_and_credentials() -> str:
    # Load .env into this process environment (non-destructive)
    env_vars = _parse_env_file(ENV_PATH)
    for k, v in env_vars.items():
        os.environ.setdefault(k, v)

    # Ensure a region is present
    region = next((os.environ.get(k) for k in REGION_ENV_KEYS if os.environ.get(k)), None)
    if not region:
        raise RuntimeError("No AWS region found. Set one of AWS_REGION, AWS_DEFAULT_REGION, or AWS_SSO_REGION in .env")

    # Refresh SSO credentials via provided script
    subprocess.run(["bash", "-lc", f'cd "{PROJECT_ROOT}" && "{REFRESH_SCRIPT}"'], check=True)
    return region


def _zip_lambda_code(flow_src_path: Path) -> bytes:
    # Build a minimal deployment package: handler.py + example/flow.py (+ __init__.py)
    tmpdir = Path(tempfile.mkdtemp())
    try:
        (tmpdir / "example").mkdir(parents=True, exist_ok=True)
        (tmpdir / "example" / "__init__.py").write_text("")  # package marker

        # Copy the current flow file to the zip to guarantee we deploy what's in the repo
        shutil.copy2(flow_src_path, tmpdir / "example" / "flow.py")

        handler_code = """\
from io import StringIO
import sys
def lambda_handler(event, context):
    buf = StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        from example.flow import example_flow
        example_flow()
        out = buf.getvalue()
        return {"output": out}
    except Exception as e:
        return {"error": str(e), "output": buf.getvalue()}
    finally:
        sys.stdout = old
"""
        (tmpdir / "handler.py").write_text(handler_code)

        # Create in-memory zip
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmpdir / "handler.py", arcname="handler.py")
            zf.write(tmpdir / "example" / "__init__.py", arcname="example/__init__.py")
            zf.write(tmpdir / "example" / "flow.py", arcname="example/flow.py")
        mem.seek(0)
        return mem.read()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    region = _ensure_env_and_credentials()

    session = boto3.session.Session(region_name=region)
    iam = session.client("iam")
    lam = session.client("lambda")
    sfn = session.client("stepfunctions")
    sts = session.client("sts")

    account_id = sts.get_caller_identity()["Account"]

    suffix = uuid.uuid4().hex[:8]
    lambda_role_name = f"acme-e2e-lambda-role-{suffix}"
    sfn_role_name = f"acme-e2e-sfn-role-{suffix}"
    lambda_name = f"acme-e2e-example-flow-{suffix}"
    state_machine_name = f"acme-e2e-state-machine-{suffix}"

    lambda_role_arn = None
    sfn_role_arn = None
    state_machine_arn = None

    try:
        # 1) Create Lambda execution role
        lambda_trust = {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}],
        }
        lambda_role_arn = iam.create_role(
            RoleName=lambda_role_name, AssumeRolePolicyDocument=json.dumps(lambda_trust), Description="E2E Lambda role"
        )["Role"]["Arn"]
        iam.attach_role_policy(
            RoleName=lambda_role_name,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
        )
        # Propagate IAM role before creating Lambda
        time.sleep(8)

        # 2) Package and create Lambda
        code_zip = _zip_lambda_code(PROJECT_ROOT / "example" / "flow.py")
        lam.create_function(
            FunctionName=lambda_name,
            Role=lambda_role_arn,
            Runtime="python3.11",
            Handler="handler.lambda_handler",
            Code={"ZipFile": code_zip},
            Timeout=60,
            MemorySize=256,
            Publish=True,
        )
        lambda_arn = f"arn:aws:lambda:{region}:{account_id}:function:{lambda_name}"

        # 3) Create Step Functions role with permission to invoke the Lambda
        sfn_trust = {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Principal": {"Service": "states.amazonaws.com"}, "Action": "sts:AssumeRole"}],
        }
        sfn_role_arn = iam.create_role(
            RoleName=sfn_role_name, AssumeRolePolicyDocument=json.dumps(sfn_trust), Description="E2E SFN role"
        )["Role"]["Arn"]
        invoke_lambda_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": ["lambda:InvokeFunction"], "Resource": [lambda_arn]},
            ],
        }
        iam.put_role_policy(
            RoleName=sfn_role_name, PolicyName="InvokeLambda", PolicyDocument=json.dumps(invoke_lambda_policy)
        )
        time.sleep(5)

        # 4) Create State Machine (STANDARD)
        definition = {
            "StartAt": "InvokeExample",
            "States": {
                "InvokeExample": {
                    "Type": "Task",
                    "Resource": "arn:aws:states:::lambda:invoke",
                    "OutputPath": "$.Payload",
                    "Parameters": {"FunctionName": lambda_arn, "Payload": {}},
                    "End": True,
                }
            },
        }
        state_machine_arn = sfn.create_state_machine(
            name=state_machine_name, definition=json.dumps(definition), roleArn=sfn_role_arn, type="STANDARD"
        )["stateMachineArn"]

        # 5) Start execution and wait for completion
        exec_arn = sfn.start_execution(stateMachineArn=state_machine_arn, name=f"run-{suffix}")["executionArn"]
        deadline = time.time() + 300
        status = "RUNNING"
        output = None
        while time.time() < deadline:
            resp = sfn.describe_execution(executionArn=exec_arn)
            status = resp["status"]
            if status in ("SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"):
                output = resp.get("output")
                break
            time.sleep(2)

        if status != "SUCCEEDED":
            raise RuntimeError(f"State machine execution did not succeed. Status={status} Output={output}")

        payload = json.loads(output) if output else {}
        out_str = payload.get("output", "")
        if EXPECTED_OUTPUT_SUBSTR not in out_str:
            raise AssertionError(f"Expected output to contain '{EXPECTED_OUTPUT_SUBSTR}', got: {out_str!r}")

        print("E2E success: output validated.")
    finally:
        # Cleanup in reverse order
        if state_machine_arn:
            try:
                sfn.delete_state_machine(stateMachineArn=state_machine_arn)
            except ClientError:
                pass
        try:
            lam.delete_function(FunctionName=lambda_name)
        except ClientError:
            pass
        try:
            iam.delete_role_policy(RoleName=sfn_role_name, PolicyName="InvokeLambda")
        except ClientError:
            pass
        try:
            iam.delete_role(RoleName=sfn_role_name)
        except ClientError:
            pass
        try:
            iam.detach_role_policy(
                RoleName=lambda_role_name,
                PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
            )
        except ClientError:
            pass
        try:
            iam.delete_role(RoleName=lambda_role_name)
        except ClientError:
            pass


if __name__ == "__main__":
    main()
