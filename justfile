# Commands for the tmpl-project template repo. Run `just` to list them.
# Tool versions are pinned in .mise.toml; outside an activated shell use `mise exec -- just ci`.
set shell := ["bash", "-cu"]

# List the recipes
default:
    @just --list --unsorted

# Render the template for several answer sets and check the output (needs uvx)
test:
    python3 -m unittest discover -v -s tests -p 'test_*.py'

# Secret scan: the working tree, then the git history
gitleaks:
    gitleaks dir --redact --no-banner -v .
    gitleaks git --redact --no-banner -v .

# Everything a CI run would do
ci: test gitleaks
