"""
Step Function definition generator for running flows as ECS jobs.

Generates a definition that starts a container task and passes parameters
via container environment variables. The image's own entrypoint is expected
to read these parameters and execute the target callable.
"""
import json
from pathlib import Path
from typing import Optional, Sequence, Mapping

def compile_step_function(
    output_path: Path,
    state_machine_name: str,
    cluster: str,
    task_definition: str,
    flow_path: str,
    subnets: Optional[Sequence[str]] = None,
    security_groups: Optional[Sequence[str]] = None,
    args: Optional[Sequence[object]] = None,
    kwargs: Optional[Mapping[str, object]] = None,
    launch_type: str = "FARGATE",
    # The following parameters are placeholders for future use or parity with CLI options.
    # They are accepted to keep the function signature stable when invoked via the CLI,
    # but are not currently used in the generated state machine definition.
    container_image: Optional[str] = None,
    region: Optional[str] = None,
    execution_role_arn: Optional[str] = None,
    task_role_arn: Optional[str] = None,
    log_group: Optional[str] = None,
) -> None:
    """
    Generates a Step Function definition for running a flow in ECS.
    Writes the definition to ``output_path`` as JSON.

    Args:
        output_path (Path): Path to write the Step Function definition JSON file.
    state_machine_name (str): Name of the Step Function state machine and ECS container override.
        cluster (str): ECS cluster name or ARN to run the task in.
        task_definition (str): ECS task definition ARN or family:revision to use.
        subnets (list, optional): List of subnet IDs for the ECS task networking. If None, uses default subnets.
        security_groups (list, optional): List of security group IDs for the ECS task networking. If None, uses default security groups.
    flow_path (str): Import path to the target callable inside the container (e.g. "pkg.mod:func").
    args (list, optional): Positional arguments to pass to the callable (JSON-serialized into env var).
    kwargs (dict, optional): Keyword arguments to pass to the callable (JSON-serialized into env var).
        launch_type (str, optional): ECS launch type (default: "FARGATE").
    """
    args = list(args or [])
    kwargs = dict(kwargs or {})
    subnets = list(subnets or get_default_subnets())
    security_groups = list(security_groups or get_default_security_groups())
    # Step Function definition
    definition = {
        "Comment": f"Run flow {flow_path} in ECS",
        "StartAt": "RunPrefectFlow",
        "States": {
            "RunPrefectFlow": {
                "Type": "Task",
                "Resource": "arn:aws:states:::ecs:runTask.sync",
                "Parameters": {
                    "LaunchType": launch_type,
                    "Cluster": cluster,
                    "TaskDefinition": task_definition,
                    "NetworkConfiguration": {
                        "AwsvpcConfiguration": {
                            "Subnets": subnets,
                            "SecurityGroups": security_groups,
                            "AssignPublicIp": "ENABLED"
                        }
                    },
                    "Overrides": {
                        "ContainerOverrides": [
                            {
                                "Name": state_machine_name,
                                # Pass inputs to the container via environment variables.
                                # The container entrypoint is responsible for consuming these.
                                "Environment": [
                                    {"Name": "AE_TARGET", "Value": flow_path},
                                    {"Name": "AE_ARGS_JSON", "Value": json.dumps(args)},
                                    {
                                        "Name": "AE_KWARGS_JSON",
                                        "Value": json.dumps({k: v for k, v in kwargs.items()}),
                                    },
                                ],
                            }
                        ]
                    },
                },
                "End": True
            }
        }
    }
    with open(output_path, "w") as f:
        json.dump(definition, f, indent=2)

def get_default_subnets() -> list:
    # TODO: Replace with logic to fetch or define default subnets
    return ["subnet-xxxxxxxx"]

def get_default_security_groups() -> list:
    # TODO: Replace with logic to fetch or define default security groups
    return ["sg-xxxxxxxx"]
