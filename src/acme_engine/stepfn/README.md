# Step Function Creation and Deployment

This directory contains scripts to generate and deploy AWS Step Function state machines for running Prefect flows as ECS jobs.

## Files

- `compile.py`: Generates a Step Function definition JSON for a Prefect flow in ECS.
- `deploy.py`: Deploys the Step Function using the generated definition.

## Usage

### 1. Compile Step Function Definition

```
python -m acme_engine.stepfn.compile \
  --output stepfn.json \
  --state-machine-name my-flow-stepfn \
  --cluster my-ecs-batch-cluster \
  --task-definition my-job-def:1 \
  --subnets subnet-aaa subnet-bbb \
  --security-groups sg-xxx \
  --container-image repo/image:tag \
  --flow-path /flows/my_flow.py \
  --args arg1 arg2 \
  --kwargs key1=val1 key2=val2
```

### 2. Deploy Step Function

```
python -m acme_engine.stepfn.deploy \
  --state-machine-name my-flow-stepfn \
  --definition stepfn.json \
  --role-arn arn:aws:iam::...:role/StepFunctionRole \
  --region us-east-1
```

## Notes
- The compile step only generates the definition file; deployment is a separate step.
- The Step Function launches the specified container image and passes the flow path and arguments to the container.
- You must provide the correct ARNs and networking parameters.
