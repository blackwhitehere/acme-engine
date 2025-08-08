"""
Example usage of AcmeFlowDeployer, mimicking the Prefect deployment API.
"""
from acme_engine.sdk.flow_deployer import AcmeFlowDeployer

# Example flow function (replace with actual flow logic)
def example_flow():
    pass

if __name__ == "__main__":
    deployer = AcmeFlowDeployer()
    deployer.deploy(
        flow_function=example_flow,
        name="acme-engine--main--example-flow--dev",
        description="Example deployment using Acme Engine SDK",
        work_pool_name="default-pool",
        cron=None,
        parameters={"param1": 42},
        job_variables={
            "env": {"ENV_VAR": "value"},
            # Provide your Step Functions role ARN here
            "stepfn_role_arn": "arn:aws:iam::<account-id>:role/StepFunctionRole",
        },
        image="repo/image:tag",
        tags=["EXAMPLE"],
        version="main-abcdef",
        paused=False,
        concurrency_limit=1,
        triggers=None,
        build=False,
        push=False,
    )
