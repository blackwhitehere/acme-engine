import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import boto3
from acme_engine.cfn.task.task_definition import ECSTaskDefinitionDeployer
from acme_engine.stepfn.compile import compile_step_function
from acme_engine.stepfn.deploy import StepFunctionDeployer

class AcmeFlowDeployer:
    """
    SDK for deploying flows using Acme Engine, mimicking the Prefect flow_function.deploy API.
    """
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def deploy(
        self,
        flow_function: Callable,
        name: str,
        description: Optional[str] = None,
        work_pool_name: str = "default-pool",
        cron: Optional[str] = None,
        paused: bool = False, # todo: need to use it
        parameters: Optional[Dict[str, Any]] = None,
        job_variables: Optional[Dict[str, Any]] = None,
        image: Optional[str] = None,
        tags: Optional[List[str]] = None,
        version: Optional[str] = None,
        concurrency_limit: int = 1,
        triggers: Optional[List[Any]] = None,
        **kwargs
    ) -> None:
        """
        Deploy a flow using Acme Engine. This API mimics Prefect's flow_function.deploy.
        Args:
            flow_function: The flow function object to deploy
            name: Name of the deployment
            description: Description of the deployment
            work_pool_name: Name of the work pool (maps to ECS cluster)
            cron: Cron schedule
            parameters: Parameters for the flow
            job_variables: Override settings (e.g., roles, networking, cpu/memory, log group)
            image: Container image URI
            tags: List of tags
            version: Version string
            paused: Whether the deployment is paused
            concurrency_limit: Concurrency limit
            triggers: List of trigger objects
            kwargs: Additional arguments
        """

        if job_variables is None:
            job_variables = {}

        self.logger.info(f"Deploying flow '{name}' with Acme Engine SDK")
        ecs_cluster = work_pool_name

        # Attempt to source default ARNs and log group from an ECS cluster stack
        # if user did not provide them via job_variables.
        cfn = boto3.client("cloudformation")
        if (
            not job_variables.get("execution_role_arn")
            or not job_variables.get("task_role_arn")
            or not job_variables.get("log_group_name")
        ):
            try:
                stack = cfn.describe_stacks(StackName=ecs_cluster)["Stacks"][0]
                outputs = {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}
                job_variables.setdefault("execution_role_arn", outputs.get("ExecutionRoleArn", ""))
                job_variables.setdefault("task_role_arn", outputs.get("TaskRoleArn", ""))
                job_variables.setdefault("log_group_name", outputs.get("LogGroupName", f"/ecs/{ecs_cluster}"))
            except Exception:
                # Fall back to defaults; caller must ensure values are valid in their env
                job_variables.setdefault("log_group_name", f"/ecs/{ecs_cluster}")

        # Register new ECS Task Definition for this deployment (new image/args)
        task_def_stack_name = f"{name}-taskdef"
        task_def_params = {
            "ClusterName": ecs_cluster,
            "TaskDefinitionName": name,
            "ContainerImage": image or "",
            "ExecutionRoleArn": job_variables.get("execution_role_arn", ""),
            "TaskRoleArn": job_variables.get("task_role_arn", ""),
            "Cpu": int(job_variables.get("cpu", 1024)),
            "Memory": int(job_variables.get("memory", 2048)),
            "LogGroupName": job_variables.get("log_group_name", f"/ecs/{ecs_cluster}"),
        }
        task_definition_arn = ECSTaskDefinitionDeployer(stack_name=task_def_stack_name).deploy(task_def_params)

        # Compile Step Function definition for this flow
        stepfn_def_path = Path(f"{name}_stepfn.json")

        # Derive import path for the provided callable (module:function)
        module_name = flow_function.__module__
        qualname = getattr(flow_function, "__name__", None) or getattr(flow_function, "__qualname__", "flow")
        target_path = f"{module_name}:{qualname}"

        compile_step_function(
            output_path=stepfn_def_path,
            state_machine_name=name,
            cluster=ecs_cluster,
            task_definition=task_definition_arn or name,  # fallback to name if ARN unknown
            subnets=job_variables.get("subnets", []),
            security_groups=job_variables.get("security_groups", []),
            flow_path=target_path,
            args=(parameters or {}).get("args", []),
            kwargs=(parameters or {}).get("kwargs", {}),
        )

        # Deploy or update the Step Function
        stepfn_role_arn = job_variables.get("stepfn_role_arn") if job_variables else ""
        if not stepfn_role_arn:
            # Explicit value required to avoid deploying with wrong permissions
            raise ValueError("stepfn_role_arn must be provided via job_variables['stepfn_role_arn']")
        stepfn_deployer = StepFunctionDeployer(
            state_machine_name=name,
            definition_path=stepfn_def_path,
            role_arn=stepfn_role_arn,
        )
        stepfn_deployer.deploy()

        self.logger.info(f"[Acme Engine] Deployed flow '{name}' (image: {image}, version: {version})")
