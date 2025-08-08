# Acme Engine

Compute and orchestration engine for running containerized batch jobs on AWS ECS/Fargate, orchestrated by Step Functions, with a clean, modular Python SDK for deployments.

## What problem does it solve?

Running reproducible, versioned batch jobs in the cloud is hard to do in a maintainable, cost‑efficient way. Acme Engine provides:

- A minimal, serverless baseline on ECS/Fargate (no always‑on compute)
- Simple, repeatable infrastructure via CloudFormation templates
- Step Functions flows compiled from Python to orchestrate jobs
- A small Python SDK to deploy/update jobs with new images/configs
- Clear separation of concerns so each part can evolve independently

## Key features

- ECS cluster and roles created via CloudFormation
- Parameterized ECS task definitions (image, roles, logs)
- Step Functions definition compiler and deploy helper
- Python SDK for one‑liner deployments that mirror Prefect’s ergonomics
- Opinionated defaults with escape hatches for customization


## Dev environment

The project comes with a python development environment.
To generate it, after checking out the repo run:

    chmod +x create_env.sh

Then to generate the environment (or update it to latest version based on state of `uv.lock`), run:

    ./create_env.sh

This will generate a new python virtual env under `.venv` directory. You can activate it via:

    source .venv/bin/activate

If you are using VSCode, set to use this env via `Python: Select Interpreter` command.

## Documentation

The project ships with a MkDocs site under `docs/`.

- Local preview: run a live-reloading docs server
    - Make sure the dev environment is active and install docs deps (once):
        - mkdocs, mkdocs-material, mkdocstrings[python]
    - Start the server from the repo root:
        - `mkdocs serve -f docs/mkdocs.yml`
    - Open http://127.0.0.1:8000

- Published docs: https://blackwhitehere.github.io/acme-engine

To avoid duplicating content between this README and the docs index, create a symlink (from `docs/docs`):

        ln -sf ../../README.md index.md

## Quickstart

Here are a few common tasks you can accomplish with Acme Engine. See the docs for full guides.

- Provision an ECS cluster with the provided CloudFormation template
- Register or update a task definition with your container image
- Compile a Step Function definition for your flow
- Deploy the Step Function and point it at the latest image

Typical flow in code (high level):

1) Generate a Step Functions JSON definition from Python
2) Deploy the definition (create/update) via the helper
3) Update ECS task definition to a new image when ready

See:
- `src/acme_engine/cfn/` for CloudFormation templates and helpers
- `src/acme_engine/stepfn/` for compile/deploy helpers
- `src/acme_engine/sdk/` for the higher-level deployer API

## Project template

This project has been setup with `acme-project-create`, a python code template library.

# Required setup post checkout

* Run `pre-commit install` to install the pre-commit hooks.

# Required setup post template use

* Enable GitHub Pages to be published via [GitHub Actions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site#publishing-with-a-custom-github-actions-workflow) by going to `Settings-->Pages-->Source`
* Create `release-pypi` environment for [GitHub Actions](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment#creating-an-environment) to enable uploads of the library to PyPi. Set protections on what tags can deploy to this environment (Point 10). Set it to tags following pattern `v*`.
* Setup auth to PyPI for the GitHub Action implemented in `.github/workflows/release.yml` via [Trusted Publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/) `uv publish` [doc](https://docs.astral.sh/uv/guides/publish/#publishing-your-package)
* Once you create the python environment for the first time add the `uv.lock` file that will be created in project directory to the source control and update it each time environment is rebuilt
* To avoid duplication between `docs/docs/index.md` and the root `README.md`, create a symlink as shown in the Documentation section above

## Design

### Overview

This project provides infrastructure and tooling for running batch jobs on AWS ECS using FARGATE, orchestrated by AWS Step Functions, with a focus on maintainability, cost efficiency, and ease of deployment.

### Main Features


#### 1. CloudFormation Stack for ECS Cluster

The implementation for this feature is provided in `src/acme_engine/cfn/ecs_cluster.yaml` (CloudFormation template) and `src/acme_engine/cfn/ecs_cluster.py` (deployment helper).

- **Purpose:** Automates creation of an ECS cluster optimized for batch jobs.
- **Launch Type:** Uses FARGATE for serverless, cost-effective compute.
- **Resource Defaults:** Each job is provisioned with 1 vCPU and 2GB memory (configurable).
- **IAM Roles:** Automatically creates and assigns necessary execution and task roles with least-privilege permissions.
- **Best Practices:** Follows AWS recommendations for ECS setup, including minimal always-on resources to reduce costs.
- **How to use:** See `src/acme_engine/cfn/README.md` for deployment instructions and parameter details.


#### 2. ECS Task Definition Management

The implementation for this feature is provided in `src/acme_engine/cfn/task/task_definition.yaml` (CloudFormation template) and `src/acme_engine/cfn/task/task_definition.py` (deployment helper).

- **Job Definition:** CloudFormation templates manage ECS job definitions (task definitions) for a specified cluster.
- **Image URI:** Supports parameterization for container image URIs.
- **Defaults:** Provides sensible defaults for Execution Role ARN, Task Role ARN, and CloudWatch Logs configuration.
- **Extensibility:** Templates are designed for easy modification and extension.
- **How to use:** See `src/acme_engine/cfn/task/README.md` for deployment instructions and parameter details. The CLI expects you to pass the cluster identifier; it does not check if the cluster exists.


#### 3. Step Function Creation Script

The implementation for this feature is provided in `src/acme_engine/stepfn/compile.py` (definition generator) and `src/acme_engine/stepfn/deploy.py` (deployment helper).

- **Purpose:** Automates creation of AWS Step Functions to orchestrate Prefect-based workflows running as ECS jobs.
- **Integration:** Accepts a container image URI and a path to the Prefect flow inside the container, and generates a Step Function that launches the container and executes the flow.
- **Configurability:** Allows customization of job parameters, flow arguments, and workflow logic. The CLI works in two steps: first, it compiles the Step Function definition to a file; then, it deploys the definition from that file.
- **How to use:** See `src/acme_engine/stepfn/README.md` for usage and parameter details.


#### 4. Python SDK for Deployment

The implementation for this feature is provided in `src/acme_engine/sdk/flow_deployer.py` (SDK) and `src/acme_engine/sdk/example_usage.py` (usage example).

- **Deployment Workflow:** Provides a Python SDK (`AcmeFlowDeployer`) to deploy new versions of flows, mimicking the Prefect `flow_function.deploy` API.
- **Prefect Compatibility:** Allows existing deployment scripts to use Acme Engine as a drop-in replacement for Prefect's deployment API.
- **Step Function Deployment:** Follows a two-step process—first generates a config file with the step function definition, then deploys it.
- **Image Updates:** Updates ECS task definitions and Step Functions to use new container image URIs.
- **Versioning:** Ensures smooth rollout of new job versions with minimal manual intervention.
- **Centralized Logic:** SDK centralizes deployment logic to avoid duplication and simplify maintenance.
- **How to use:** See `src/acme_engine/sdk/README.md` for usage and API details.

### Design Principles

- **Separation of Concerns:** Infrastructure, job definitions, orchestration, and deployment logic are modular and isolated.
- **DRY Principle:** Centralized configuration and templates to avoid duplication.
- **Single Responsibility:** Each component (CloudFormation, job definition, orchestration, SDK) has a focused responsibility.
- **Reversibility:** Design choices (e.g., resource sizes, roles, image URIs) are parameterized for easy change.
- **Orthogonality:** Components can be modified or replaced independently.