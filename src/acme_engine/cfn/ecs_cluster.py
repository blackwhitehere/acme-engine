"""
Module for deploying and managing the ECS Cluster CloudFormation stack.
"""
from pathlib import Path
import subprocess
from typing import Optional

CFN_TEMPLATE_PATH = Path(__file__).parent / "ecs_cluster.yaml"

class ECSClusterDeployer:
    """
    Handles deployment of the ECS Cluster CloudFormation stack.
    """
    def __init__(self, stack_name: str, region: str = "us-east-1"):
        self.stack_name = stack_name
        self.region = region

    def deploy(self, parameters: dict, capabilities: Optional[list] = None):
        """
        Deploys or updates the ECS Cluster CloudFormation stack.
        Args:
            parameters: Dictionary of parameter key-value pairs for the stack.
            capabilities: List of capabilities (e.g., ["CAPABILITY_NAMED_IAM"]).
        """
        param_args = []
        for k, v in parameters.items():
            param_args.append(f"ParameterKey={k},ParameterValue={v}")
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
