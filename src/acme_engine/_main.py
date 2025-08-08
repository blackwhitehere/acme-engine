
import argparse
import sys
from acme_engine.cfn.ecs_cluster import ECSClusterDeployer
from acme_engine.cfn.task.task_definition import ECSTaskDefinitionDeployer
from acme_engine.stepfn.compile import compile_step_function
from acme_engine.stepfn.deploy import StepFunctionDeployer
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(
        prog="ae", description="Compute and Orchestration Engine"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ECS Cluster subcommand
    ecs_parser = subparsers.add_parser("ecs-cluster", help="Manage ECS Cluster CloudFormation stack")
    ecs_parser.add_argument("--stack-name", required=True, help="CloudFormation stack name")
    ecs_parser.add_argument("--region", default="us-east-1", help="AWS region")
    ecs_parser.add_argument("--delete", action="store_true", help="Delete the stack instead of deploying")
    ecs_parser.add_argument(
        "--parameters", nargs="*", default=[], metavar="KEY=VALUE",
        help="CloudFormation parameters (e.g. ClusterName=foo VpcId=vpc-xxx SubnetIds=subnet-aaa,subnet-bbb)"
    )
    ecs_parser.add_argument(
        "--capabilities", nargs="*", default=["CAPABILITY_NAMED_IAM"],
        help="CloudFormation capabilities (default: CAPABILITY_NAMED_IAM)"
    )

    # ECS Job Definition subcommand
    job_parser = subparsers.add_parser("ecs-task-def", help="Manage ECS Task Definition CloudFormation stack")
    job_parser.add_argument("--stack-name", required=True, help="CloudFormation stack name for the task definition")
    job_parser.add_argument("--region", default="us-east-1", help="AWS region")
    job_parser.add_argument("--delete", action="store_true", help="Delete the stack instead of deploying")
    job_parser.add_argument(
        "--parameters", nargs="*", default=[], metavar="KEY=VALUE",
        help="CloudFormation parameters (e.g. ClusterName=foo TaskDefinitionName=bar ContainerImage=repo/image:tag ... )"
    )
    job_parser.add_argument(
        "--capabilities", nargs="*", default=["CAPABILITY_NAMED_IAM"],
        help="CloudFormation capabilities (default: CAPABILITY_NAMED_IAM)"
    )

    # Step Function compile subcommand
    compile_parser = subparsers.add_parser("stepfn-compile", help="Compile Step Function definition for Prefect ECS job")
    compile_parser.add_argument("--output", required=True, help="Path to output JSON definition file")
    compile_parser.add_argument("--state-machine-name", required=True, help="Name of the Step Function state machine")
    compile_parser.add_argument("--cluster", required=True, help="ECS Cluster name or ARN")
    compile_parser.add_argument("--task-definition", required=True, help="ECS Task Definition ARN or family:revision")
    compile_parser.add_argument("--subnets", nargs="+", required=True, help="Subnets for ECS task")
    compile_parser.add_argument("--security-groups", nargs="+", required=True, help="Security groups for ECS task")
    compile_parser.add_argument("--container-image", required=True, help="Container image URI")
    compile_parser.add_argument("--flow-path", required=True, help="Path to Prefect flow inside container")
    compile_parser.add_argument("--args", nargs="*", default=[], help="Positional arguments for the flow script")
    compile_parser.add_argument("--kwargs", nargs="*", default=[], help="Keyword arguments for the flow script (key=value)")
    compile_parser.add_argument("--launch-type", default="FARGATE", help="ECS Launch type (default: FARGATE)")
    compile_parser.add_argument("--region", default="us-east-1", help="AWS region")
    compile_parser.add_argument("--execution-role-arn", help="ECS execution role ARN")
    compile_parser.add_argument("--task-role-arn", help="ECS task role ARN")
    compile_parser.add_argument("--log-group", help="CloudWatch log group name")

    # Step Function deploy subcommand
    deploy_parser = subparsers.add_parser("stepfn-deploy", help="Deploy Step Function from definition file")
    deploy_parser.add_argument("--state-machine-name", required=True, help="Name of the Step Function state machine")
    deploy_parser.add_argument("--definition", required=True, help="Path to JSON definition file")
    deploy_parser.add_argument("--role-arn", required=True, help="IAM role ARN for Step Function")
    deploy_parser.add_argument("--region", default="us-east-1", help="AWS region")

    return parser.parse_args()

def parse_parameters(param_list):
    params = {}
    for item in param_list:
        if "=" not in item:
            print(f"Invalid parameter: {item}. Use KEY=VALUE format.", file=sys.stderr)
            sys.exit(1)
        k, v = item.split("=", 1)
        params[k] = v
    return params

def main_logic(args):
    if args.command == "ecs-cluster":
        deployer = ECSClusterDeployer(stack_name=args.stack_name, region=args.region)
        if args.delete:
            deployer.delete()
            print(f"Deleted stack {args.stack_name}")
        else:
            params = parse_parameters(args.parameters)
            deployer.deploy(parameters=params, capabilities=args.capabilities)
            print(f"Deployed/updated stack {args.stack_name}")
    elif args.command == "ecs-task-def":
        deployer = ECSTaskDefinitionDeployer(stack_name=args.stack_name, region=args.region)
        if args.delete:
            deployer.delete()
            print(f"Deleted task definition stack {args.stack_name}")
        else:
            params = parse_parameters(args.parameters)
            deployer.deploy(parameters=params, capabilities=args.capabilities)
            print(f"Deployed/updated task definition stack {args.stack_name}")
    elif args.command == "stepfn-compile":
        # Parse kwargs as key=value pairs
        kwargs = {}
        for item in args.kwargs:
            if "=" not in item:
                print(f"Invalid kwarg: {item}. Use key=value format.", file=sys.stderr)
                sys.exit(1)
            k, v = item.split("=", 1)
            kwargs[k] = v
        compile_step_function(
            output_path=Path(args.output),
            state_machine_name=args.state_machine_name,
            cluster=args.cluster,
            task_definition=args.task_definition,
            subnets=args.subnets,
            security_groups=args.security_groups,
            container_image=args.container_image,
            flow_path=args.flow_path,
            args=args.args,
            kwargs=kwargs,
            launch_type=args.launch_type,
            region=args.region,
            execution_role_arn=args.execution_role_arn,
            task_role_arn=args.task_role_arn,
            log_group=args.log_group,
        )
        print(f"Step Function definition written to {args.output}")
    elif args.command == "stepfn-deploy":
        deployer = StepFunctionDeployer(
            state_machine_name=args.state_machine_name,
            definition_path=Path(args.definition),
            role_arn=args.role_arn,
            region=args.region,
        )
        deployer.deploy()
        print(f"Step Function {args.state_machine_name} deployed/updated.")
    else:
        print("Unknown command", file=sys.stderr)
        sys.exit(1)

def main():
    args = parse_args()
    main_logic(args)

if __name__ == "__main__":
    main()



