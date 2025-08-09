This repository is a Python 3.12 project named "acme_engine" that provides a compute/orchestration engine for batch jobs on AWS ECS/Fargate with Step Functions, plus a small SDK. Use these instructions when proposing or implementing changes (including by Copilot coding agent).

## Development flow

- Environment: Python 3.12 with uv managing dependencies (pyproject + uv.lock)
- Install deps (preferred): `uv sync --dev` (or run `./create_env.sh` locally)
- Lint/format: `ruff check .` and `ruff format --check .` (fix with `ruff format .`)
- Tests: `pytest -q`
- Docs (MkDocs): `mkdocs build -f docs/mkdocs.yml`

Copilot acceptance criteria for PRs:
- Code compiles and type-checks; ruff passes; tests pass; docs build succeeds
- Public APIs keep or improve type hints and docstrings
- Changes are scoped, reversible, and easy to review (single responsibility)

## Repository structure (high level)
- `src/acme_engine/`: library and CLI (`ae`) sources
- `tests/`: unit/integration tests
- `docs/`: MkDocs site (material theme, mkdocstrings)
- `example/`: sample flows/usages
- `admin/`: scripts for local ops

## Code standards
- Prefer small, composable functions and modules; separate concerns clearly
- Adhere to DRY: centralize shared logic/config where feasible
- Name things precisely and consistently; optimize for readability
- Keep decisions reversible; pass dependencies via parameters where sensible
- Maintain Python typing in signatures and ensure docs reflect behavior
- Keep docs concise and practical; avoid comments that restate obvious code

## Testing guidelines
- Use pytest; write focused tests with clear arrange/act/assert
- Mock cloud/service calls (e.g., boto3) by default; avoid network or AWS usage in unit tests
- Add at least a happy-path test and one edge case for new behavior

## Docs guidelines
- Update or add user-facing docs for any new feature or CLI change
- Keep `docs/mkdocs.yml` and navigation consistent; short examples > long prose

## CI and tooling (for Copilot)
- Prefer uv for dependency sync; use Python 3.12
- Run ruff and pytest in CI; build docs to catch regressions

Tip: If you need to add tools or packages for Copilot’s ephemeral env, use `.github/workflows/copilot-setup-steps.yml` with a single `copilot-setup-steps` job.