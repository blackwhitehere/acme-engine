---
applyTo: "src/**/*.py"
---

## Python source requirements

- Target Python 3.12
- Maintain type hints on public APIs
- Follow ruff rules; keep imports sorted via ruff (no isort config here)
- Keep functions small; separate I/O (AWS/boto3) from pure logic to enable testing
- Prefer dependency injection or passing clients explicitly over globals

### Build and validate locally
- Install: `uv sync --dev`
- Lint: `ruff check .`
- Type style: `ruff format --check .` (auto-fix with `ruff format .`)
- Tests: `pytest -q`

### Testing notes
- Mock boto3 and any network calls; avoid real AWS access in unit tests
- Include a happy-path and at least one edge case
- Add minimal docstrings for new public functions/classes
