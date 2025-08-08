# One time setup

In order not to replicate documentation in `docs/docs/index.md` file and `README.md` in root of the project setup a symlink from `README.md` file to the `index.md` file.
To do this, from `docs/docs` dir run:

    ln -sf ../../README.md index.md

# Usage
run `mkdocs serve` from this dir to run docs in browser
run `mkdocs build` to build docs for deployment under `site`