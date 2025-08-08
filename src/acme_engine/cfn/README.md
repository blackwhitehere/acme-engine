# ECS Cluster CloudFormation Stack

This directory contains the CloudFormation template and deployment helper for the ECS Cluster optimized for batch jobs using FARGATE.

## Files

- `ecs_cluster.yaml`: CloudFormation template for ECS Cluster, IAM roles, and CloudWatch log group.
- `ecs_cluster.py`: Python module to deploy/delete the stack using AWS CLI.

## Usage

### Deploy the Stack

```
python -m acme_engine.cfn.ecs_cluster \
  --stack-name my-ecs-batch-cluster \
  --region us-east-1 \
  --parameters ClusterName=my-ecs-batch-cluster VpcId=vpc-xxxx SubnetIds=subnet-aaa,subnet-bbb
```

Or use the `ECSClusterDeployer` class in your own scripts.

### Delete the Stack

```
python -m acme_engine.cfn.ecs_cluster --stack-name my-ecs-batch-cluster --region us-east-1 --delete
```

## Parameters

- `ClusterName`: Name of the ECS Cluster
- `VpcId`: VPC Id for ECS Cluster
- `SubnetIds`: Comma-separated list of Subnet Ids
- `ExecutionRoleName`: Name for ECS execution role (default: acme-ecs-execution-role)
- `TaskRoleName`: Name for ECS task role (default: acme-ecs-task-role)
- `DefaultCpu`: Default vCPU units for jobs (default: 1024)
- `DefaultMemory`: Default memory (MiB) for jobs (default: 2048)

## Notes
- You must have AWS CLI configured and permissions to deploy CloudFormation stacks.
- The template uses named IAM roles and creates a CloudWatch log group for ECS jobs.
