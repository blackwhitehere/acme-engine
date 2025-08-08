# ECS Task Definition CloudFormation Management

This directory contains the CloudFormation template and deployment helper for ECS Task Definitions.

## Files

- `task_definition.yaml`: CloudFormation template for ECS Task Definition.
- `job_definition.py`: Python module to deploy/delete the task definition stack using AWS CLI.

## Usage

### Deploy the Task Definition

```
python -m acme_engine.cfn.task.task_definition \
  --stack-name my-ecs-task-def \
  --region us-east-1 \
  --parameters ClusterName=my-ecs-batch-cluster TaskDefinitionName=my-task ContainerImage=repo/image:tag \
    ExecutionRoleArn=arn:aws:iam::... TaskRoleArn=arn:aws:iam::... LogGroupName=/ecs/my-ecs-batch-cluster
```

Or use the `ECSTaskDefinitionDeployer` class in your own scripts.

### Delete the Task Definition

```
python -m acme_engine.cfn.task.task_definition --stack-name my-ecs-task-def --region us-east-1 --delete
```

## Parameters

- `ClusterName`: Name of the ECS Cluster
- `TaskDefinitionName`: Name for the ECS Task Definition
- `ContainerImage`: Container image URI
- `ExecutionRoleArn`: ARN of the ECS execution role
- `TaskRoleArn`: ARN of the ECS task role
- `Cpu`: vCPU units for the task (default: 1024)
- `Memory`: Memory (MiB) for the task (default: 2048)
- `LogGroupName`: Name of the CloudWatch Log Group

## Notes
- You must have AWS CLI configured and permissions to deploy CloudFormation stacks.
- The template does not check if the cluster exists; you must provide the correct cluster name.
