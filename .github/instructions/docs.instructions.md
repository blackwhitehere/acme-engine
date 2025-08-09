---
applyTo: "docs/**"
---

## Docs (MkDocs) guidelines

- Keep content concise and practical; prefer short, runnable examples
- Update navigation in `docs/mkdocs.yml` when adding pages
- Use `mkdocstrings` for API docs where helpful
- Ensure README and docs index are consistent; consider using a symlink as noted in README

### Build docs
- `mkdocs build -f docs/mkdocs.yml`
