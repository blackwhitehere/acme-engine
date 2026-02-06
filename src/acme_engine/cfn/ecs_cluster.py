"""
Module for deploying and managing the ECS Cluster CloudFormation stack.

It can resolve existing VPC and Subnets from the configured AWS account,
using environment variables (from .env, if loaded) when provided, or falling
back to AWS discovery via EC2 APIs.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Mapping, Optional

try:  # optional at runtime; in tests we mock the session creation
    import boto3  # type: ignore
except Exception:  # pragma: no cover - only hit in exotic envs
    boto3 = None  # type: ignore[assignment]

CFN_TEMPLATE_PATH = Path(__file__).parent / "ecs_cluster.yaml"

def _env_get_subnet_ids() -> list[str] | None:
    """Read subnet IDs from environment if provided, else None.

    Supports either ACME_SUBNET_IDS or SUBNET_IDS as a comma-separated list.
    """
    raw = os.environ.get("ACME_SUBNET_IDS") or os.environ.get("SUBNET_IDS")
    if not raw:
        return None
    # Allow whitespace, ensure non-empty tokens
    items = [s.strip() for s in raw.split(",")]
    return [s for s in items if s]


def _env_get_vpc_id() -> str | None:
    """Read VPC ID from environment if provided, else None.

    Supports either ACME_VPC_ID or VPC_ID.
    """
    return os.environ.get("ACME_VPC_ID") or os.environ.get("VPC_ID")


def _discover_default_vpc_and_subnets(session, prefer_public: bool = True) -> tuple[str, list[str]]:
    """Discover default VPC and subnets using the provided boto3 session.

    - Picks the default VPC (isDefault=true)
    - Chooses subnets in that VPC; prefers those with MapPublicIpOnLaunch if any

    Returns:
        (vpc_id, subnet_ids)
    """
    ec2 = session.client("ec2")
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}]).get("Vpcs", [])
    if not vpcs:
        raise RuntimeError("No default VPC found for ECS cluster configuration")
    vpc_id = vpcs[0]["VpcId"]

    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]).get("Subnets", [])
    if not subnets:
        raise RuntimeError("No subnets found in the discovered VPC")
    public = [s for s in subnets if s.get("MapPublicIpOnLaunch")]
    chosen = public if (prefer_public and public) else subnets
    subnet_ids = [s["SubnetId"] for s in chosen]
    return vpc_id, subnet_ids


def _build_parameter_overrides(parameters: Mapping[str, object]) -> list[str]:
    """Build aws CLI --parameter-overrides tokens from a dict.

    Lists are joined with commas (as expected by CloudFormation for List<...> parameters).
    """
    tokens: list[str] = []
    for k, v in parameters.items():
        if isinstance(v, (list, tuple)):
            value = ",".join(str(x) for x in v)
        else:
            value = str(v)
        tokens.append(f"ParameterKey={k},ParameterValue={value}")
    return tokens


class ECSClusterDeployer:
    """
    Handles deployment of the ECS Cluster CloudFormation stack.
    """
    def __init__(self, stack_name: str, region: str = "us-east-1") -> None:
        self.stack_name: str = stack_name
        self.region: str = region

    def deploy(
        self,
        parameters: dict,
        capabilities: Optional[list[str]] = None,
        *,
        aws_session=None,
    ) -> None:
        """
        Deploys or updates the ECS Cluster CloudFormation stack.
        Args:
            parameters: Dictionary of parameter key-value pairs for the stack.
            capabilities: List of capabilities (e.g., ["CAPABILITY_NAMED_IAM"]).
            aws_session: Optional boto3 session to use (for testability / DI).
        """
        # Ensure VpcId and SubnetIds are present; resolve from env or AWS if missing
        resolved_params: dict[str, object] = dict(parameters)
        if "VpcId" not in resolved_params or not resolved_params["VpcId"]:
            vpc_id_env = _env_get_vpc_id()
            if vpc_id_env:
                resolved_params["VpcId"] = vpc_id_env
            else:
                if aws_session is None:
                    if boto3 is None:
                        raise RuntimeError("boto3 is required to discover VPC when VpcId is not provided")
                    aws_session = boto3.session.Session(region_name=self.region)
                vpc_id, subnets = _discover_default_vpc_and_subnets(aws_session)
                resolved_params.setdefault("SubnetIds", subnets)
                resolved_params["VpcId"] = vpc_id
        # Subnets might still be missing; fill from env or discovery
        if "SubnetIds" not in resolved_params or not resolved_params["SubnetIds"]:
            subnets_env = _env_get_subnet_ids()
            if subnets_env:
                resolved_params["SubnetIds"] = subnets_env
            else:
                if aws_session is None:
                    if boto3 is None:
                        raise RuntimeError("boto3 is required to discover SubnetIds when not provided")
                    aws_session = boto3.session.Session(region_name=self.region)
                _, subnets = _discover_default_vpc_and_subnets(aws_session)
                resolved_params["SubnetIds"] = subnets

        param_args = _build_parameter_overrides(resolved_params)
        cmd = [
            "aws", "cloudformation", "deploy",
            "--template-file", str(CFN_TEMPLATE_PATH),
            "--stack-name", self.stack_name,
            "--region", self.region,
            "--parameter-overrides", *param_args
        ]
        if capabilities:
            cmd += ["--capabilities"] + capabilities
        subprocess.run(cmd, check=True)

    def delete(self):
        """
        Deletes the ECS Cluster CloudFormation stack.
        """
        cmd = [
            "aws", "cloudformation", "delete-stack",
            "--stack-name", self.stack_name,
            "--region", self.region
        ]
        subprocess.run(cmd, check=True)
