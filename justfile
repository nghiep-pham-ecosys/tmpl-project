# Commands for the tmpl-project template repo. Run `just` to list them.
# Tool versions are pinned in .mise.toml; outside an activated shell use `mise exec -- just ci`.
set shell := ["bash", "-cu"]

# List the recipes
default:
    @just --list --unsorted

# Static checks, render every answer set, copier update v0.1.0 -> v0.1.1 (needs uvx)
test:
    python3 -m unittest discover -v -s tests -p 'test_*.py'

# Lint this repo's workflows (template/.github is checked in the rendered repos by `just test`)
actionlint:
    actionlint
    @echo "actionlint: ok"

# Secret scan: the working tree, then the git history
gitleaks:
    gitleaks dir --redact --no-banner -v .
    gitleaks git --redact --no-banner -v .

# Everything a CI run would do
ci: test actionlint gitleaks
