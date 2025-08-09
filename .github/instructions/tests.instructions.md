---
applyTo: "tests/**/*.py"
---

## Pytest conventions

- Use clear arrange/act/assert sections
- Prefer fixtures over ad-hoc setup
- Name tests descriptively; one assertion focus per test where possible
- Avoid network and AWS; mock boto3, environment, and filesystem

### Running tests
- `pytest -q`

### Coverage and reliability
- Add one happy-path and one edge case for new behavior
- Prefer deterministic inputs and seeded randomness
