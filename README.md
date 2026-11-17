# tmpl-project

The starter for every new repo in the `nghiep-pham-ecosys` org (spec §5.5). It is a
[Copier](https://copier.readthedocs.io/) template: answer a few questions and get a repo that already has the
workspace conventions (project card, agent notes, licences, CI with gitleaks and `pr-title`, pinned tools).

Version: **v0.1** (local draft, ecosys#7). The repo base only; the K1 extras (ruff, coverage ratchet, commit-msg
hook, release notes, issue and PR forms per repo) come in later versions.

## Use it

```sh
# Copier pinned to an exact version; uvx comes with uv (pinned in the ecosys .mise.toml)
uvx --from copier==9.19.1 copier copy gh:nghiep-pham-ecosys/tmpl-project projects/<new-repo>
cd projects/<new-repo>
git init -b main
mise install
just ci
```

Until the GitHub repo exists, use the local path of this repo instead of `gh:nghiep-pham-ecosys/tmpl-project`.
Copier writes the source path into `.copier-answers.yml`, so render a public repo from the GitHub URL, not from a
local path.

Non-interactive, for example in a script:

```sh
uvx --from copier==9.19.1 copier copy --defaults -d project_name=example-lab -d visibility=private <template> <dest>
```

Later, to pull a newer template version into a generated repo: `uvx --from copier==9.19.1 copier update`.

## Questions

| Answer | Default | What it does |
|---|---|---|
| `project_name` | `example-lab` | Repo name. Lower case, digits and hyphens, starts with a letter. Used in every file and in the repo URL in `project.yaml`. |
| `description` | an example sentence | One sentence at the top of `README.md` and `CLAUDE.md`. |
| `area` | `lab` | Workspace area (`lab`, `learn`, `content`, `ecosys`, `jobs`). Goes into `project.yaml` and `CLAUDE.md`. |
| `visibility` | `public` | `public`: public-safe rules in `CLAUDE.md` and `CONTRIBUTING.md`. `private`: adds `.githooks/pre-push` (gitleaks, fails closed) and a `just hooks` recipe, because private repos on the Free plan have no rulesets. |
| `status` | `active` | `project.yaml` status: `active`, `paused` or `done`. Only `active` counts against the area WIP limit. |
| `content_licence` | yes | yes: adds `LICENSE-content` (CC BY 4.0 for text and media) next to the MIT `LICENSE`. no: MIT only. `README`, `NOTICE` and `CONTRIBUTING` follow the choice. |
| `python` | yes | yes: adds `tests/test_smoke.py` (stdlib `unittest`), a `just test` recipe and a CI `test` job that `ci-result` waits for. |
| `copyright_holder` | `Nghiep Pham` | Name in `LICENSE`, `LICENSE-content` and `NOTICE`. |
| `copyright_year` | `2026` | First year in the licence files. |

`org` (`nghiep-pham-ecosys`) is fixed and not asked.

## What a generated repo gets

| File | Why |
|---|---|
| `README.md` | what it is, quick start, layout, licence |
| `CLAUDE.md` | a stub that points to the root rules (`../../CLAUDE.md`) and imports nothing (spec §9.7) |
| `project.yaml` | name, area, status, stack, highlights, links, visibility (spec §5.5) |
| `justfile` | `ci` = what CI runs: `test` (python), `actionlint`, `gitleaks` (working tree and history); `hooks` (private) |
| `.mise.toml` | just 1.59.0, gitleaks 8.30.1, actionlint 1.7.12, the same pins as the ecosys root |
| `.github/workflows/ci.yml` | `test` (python), `gitleaks`, `actionlint`, aggregate `ci-result`; actions pinned by full SHA; tools from release tarballs checked by sha256 |
| `.github/workflows/pr-title.yml` | the `pr-title` check, same as ecosys |
| `.githooks/pre-push` | private only: gitleaks on the pushed commits; no gitleaks, no push |
| `.gitleaks-worktree.toml` | working-tree scan only (`gitleaks dir`): default rules plus skips for gitignored tool folders (`.venv`, `node_modules`, caches) and local env files. The history scan (`gitleaks git` in `just ci`, CI and pre-push) uses the default rules with no allowlist, so a force-committed secret under those paths still fails. |
| `.gitignore` | secrets, Python and Node caches, `.tmp-session/` |
| `LICENSE`, `LICENSE-content`, `NOTICE` | MIT code, CC BY 4.0 text and media (optional), attributions |
| `CONTRIBUTING.md` | flow, commit and PR title format, `Refs` line, rules |
| `.copier-answers.yml` | the answers, for `copier update` |

Issue and PR templates come from the org `.github` repo, so the template does not copy them.

## Develop the template

```sh
mise install
just ci      # renders the template for several answer sets into a temp dir and checks the output
```

The template uses `[[ ]]` and `[% %]` as Jinja delimiters (`_envops` in `copier.yml`), because workflows and
justfiles use `{{ }}`. Only files ending in `.jinja` are rendered; the rest are copied as they are. A file or folder
whose name renders to an empty string is skipped, which is how the optional files work.

## Licence

MIT, see [LICENSE](LICENSE).
