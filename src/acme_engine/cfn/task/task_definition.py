"""
Module for deploying and managing ECS Job Definitions via CloudFormation.
"""
from pathlib import Path
from typing import Optional

CFN_TEMPLATE_PATH = Path(__file__).parent / "task_definition.yaml"

class ECSTaskDefinitionDeployer:
    """
    Handles deployment of ECS Task Definitions as CloudFormation stacks.
    """
    def __init__(self, stack_name: str, region: str = "us-east-1"):
        self.stack_name = stack_name
        self.region = region

    def deploy(self, parameters: dict, capabilities: Optional[list] = None) -> Optional[str]:
        """
        Deploys or updates the ECS Task Definition CloudFormation stack using boto3.
        Args:
            parameters: Dictionary of parameter key-value pairs for the stack.
            capabilities: List of capabilities (e.g., ["CAPABILITY_NAMED_IAM"]).
        Returns:
            The ECS Task Definition ARN if available, else None.
        """
        import boto3
        cfn = boto3.client("cloudformation", region_name=self.region)
        stack_params = [
            {"ParameterKey": k, "ParameterValue": str(v)} for k, v in parameters.items()
        ]
        if capabilities is None:
            capabilities = ["CAPABILITY_NAMED_IAM"]
        with open(CFN_TEMPLATE_PATH, "r") as f:
            template_body = f.read()
        try:
            cfn.describe_stacks(StackName=self.stack_name)
            # Stack exists, update
            cfn.update_stack(
                StackName=self.stack_name,
                TemplateBody=template_body,
                Parameters=stack_params,
                Capabilities=capabilities
            )
        except cfn.exceptions.ClientError as e:
            if "does not exist" in str(e):
                # Stack does not exist, create
                cfn.create_stack(
                    StackName=self.stack_name,
                    TemplateBody=template_body,
                    Parameters=stack_params,
                    Capabilities=capabilities
                )
            else:
                raise
        waiter = cfn.get_waiter("stack_create_complete")
        try:
            waiter.wait(StackName=self.stack_name)
        except Exception:
            waiter = cfn.get_waiter("stack_update_complete")
            waiter.wait(StackName=self.stack_name)
        # Get task definition ARN from stack outputs if present
        stack = cfn.describe_stacks(StackName=self.stack_name)["Stacks"][0]
        for output in stack.get("Outputs", []):
            if output["OutputKey"].lower().endswith("taskdefinitionarn"):
                return output["OutputValue"]
        return None


    def delete(self) -> None:
        """
        Deletes the ECS Task Definition CloudFormation stack using boto3.
        """
        import boto3
        cfn = boto3.client("cloudformation", region_name=self.region)
        cfn.delete_stack(StackName=self.stack_name)
        waiter = cfn.get_waiter("stack_delete_complete")
        waiter.wait(StackName=self.stack_name)
