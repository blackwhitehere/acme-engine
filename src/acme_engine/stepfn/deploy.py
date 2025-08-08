"""
Step Function deployment helper using boto3.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import boto3


class StepFunctionDeployer:
    """
    Deploys a Step Function state machine from a definition file.
    Creates if absent, updates if exists (matched by name).
    """

    def __init__(self, state_machine_name: str, definition_path: Path, role_arn: str, region: str = "us-east-1"):
        self.state_machine_name = state_machine_name
        self.definition_path = definition_path
        self.role_arn = role_arn
        self.region = region
        self.client = boto3.client("stepfunctions", region_name=region)

    def _find_state_machine_arn(self) -> Optional[str]:
        paginator = self.client.get_paginator("list_state_machines")
        for page in paginator.paginate():
            for sm in page.get("stateMachines", []):
                if sm.get("name") == self.state_machine_name:
                    return sm.get("stateMachineArn")
        return None

    def deploy(self) -> str:
        """
        Deploy or update the state machine and return its ARN.
        """
        definition = Path(self.definition_path).read_text()
        # Ensure it's valid JSON
        json.loads(definition)

        existing_arn = self._find_state_machine_arn()
        if not existing_arn:
            resp = self.client.create_state_machine(
                name=self.state_machine_name,
                definition=definition,
                roleArn=self.role_arn,
                type="STANDARD",
            )
            return resp["stateMachineArn"]
        else:
            self.client.update_state_machine(
                stateMachineArn=existing_arn,
                definition=definition,
                roleArn=self.role_arn,
            )
            return existing_arn
