# Acme Engine Python SDK for Flow Deployment

This module provides an Acme Engine SDK for deploying flows, mimicking the Prefect `flow_function.deploy` API. Use this SDK to deploy flows in a way that is compatible with existing Prefect-based deployment scripts, but without requiring Prefect for deployment.

## Usage Example

```
from acme_engine.sdk.flow_deployer import AcmeFlowDeployer

def my_flow():
    ...

deployer = AcmeFlowDeployer()
deployer.deploy(
    flow_function=my_flow,
    name="my-deployment",
    description="My flow deployment",
    work_pool_name="default-pool",
    work_queue_name="default-queue",
    cron=None,
    parameters={"param1": 42},
    job_variables={"env": {"ENV_VAR": "value"}},
    image="repo/image:tag",
    tags=["EXAMPLE"],
    version="main-abcdef",
    paused=False,
    concurrency_limit=1,
    triggers=None,
    build=False,
    push=False,
)
```

## API

- `AcmeFlowDeployer.deploy(...)`: Accepts the same arguments as Prefect's `flow_function.deploy`, but uses Acme Engine as the backend.

## Notes
- This SDK is designed to be a drop-in replacement for Prefect's deployment API in automation scripts.
- The actual deployment logic should be implemented in the `deploy` method to interact with Acme Engine's backend.
