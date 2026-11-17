# tmpl-project

The starter for every new repo in the `nghiep-pham-ecosys` org (spec §5.5). It is a
[Copier](https://copier.readthedocs.io/) template: answer a few questions and get a repo that already has the
workspace conventions (project card, agent notes, licences, CI with gitleaks and `pr-title`, pinned tools).

Version: **v0.1** (ecosys#7). The repo base only (ADR 0005 §1). Planned for later versions: ruff, a coverage
ratchet, a commit-msg hook, release notes, and issue and PR forms per repo.

All commands below run Copier through `uvx` at one exact version, `copier==9.19.1`. `uvx` comes with uv, which the
ecosys root `.mise.toml` pins.

## Create a repo from it

Creating a repo needs Nghiep's yes (ADR 0003). Then, from the workspace root:

```sh
# 1. Render the latest release tag (add --vcs-ref vX.Y.Z to pick one) into the folder repos.yaml will name
uvx --from copier==9.19.1 copier copy gh:nghiep-pham-ecosys/tmpl-project projects/<new-repo>
cd projects/<new-repo>

# 2. First commit
git init -b main
git add -A
git commit -m "chore: generate from tmpl-project v0.1.0"

# 3. Tools and checks (mise asks once to trust the new .mise.toml)
mise trust
mise install
just ci
just hooks   # private repos only, before the first push: gitleaks runs on every push

# 4. The GitHub repo, then push: --public or --private, the same as the visibility answer
gh repo create nghiep-pham-ecosys/<new-repo> --public --source . --push
```

Then add the repo to `repos.yaml` (or to the private overlay, for a repo whose name stays out of public files), and
open the first PR so `ci-result` and `pr-title` run once before any ruleset requires them.

Render from the GitHub URL, not a local path: Copier writes the source into `.copier-answers.yml`, and `copier update`
reads it from there. Without `--vcs-ref`, Copier uses the newest tag, so only tagged versions reach new repos.

Non-interactive, for example in a script:

```sh
uvx --from copier==9.19.1 copier copy --defaults -d project_name=example-lab -d visibility=private gh:nghiep-pham-ecosys/tmpl-project <dest>
```

## Update a generated repo

```sh
cd projects/<repo>          # clean working tree on a new branch
uvx --from copier==9.19.1 copier update --defaults
git diff                     # the template changes, merged three-way with local edits
just ci
```

`--defaults` keeps the stored answers. Copier merges each template change with the repo's own edits and moves
`_commit` in `.copier-answers.yml` to the new tag. A conflict shows up as inline `<<<<<<<` markers; `git grep -n '^<<<<<<< '`
finds them before you commit. Commit as `chore: update from tmpl-project vX.Y.Z`. `tests/test_update.py` checks this path on every change.

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
| `copyright_year` | the current year | First year in the licence files. The default is the year of the first render (`strftime` from the Ansible filters Copier always loads, so no `--trust`). `copier update` keeps the stored answer. |

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
just ci      # what CI runs: test, actionlint, gitleaks
```

`just test` runs three test files (stdlib `unittest`, Copier through `uvx`):

| File | Checks |
|---|---|
| `tests/test_repo.py` | actions GitHub-owned and pinned by SHA; tool versions the same in `.mise.toml`, `template/.mise.toml`, `scripts/install-tools` and the generated CI; one Copier version everywhere |
| `tests/test_install_tools.py` | runs `scripts/install-tools` offline with a fake `curl` and synthetic archives; accepts both checksum line formats (`<sha>  <file>` and uv's `<sha> *<file>`), rejects a pin that is missing or listed for another file |
| `tests/test_render.py` | renders three answer sets (public and private); files per answer, project card, workflows, gitleaks on planted secrets, the pre-push hook, and `just ci` inside each generated repo |
| `tests/test_update.py` | tags v0.1.0 in a scratch copy, renders and commits repos with a local edit, changes the template, tags v0.1.1, runs `copier update`; the change arrives, the local edit stays, no conflicts |

Run it with temp output in the workspace scratch folder: `TMPDIR=<workspace>/.tmp-session/<session>/kit mise exec -- just ci`.

CI (`.github/workflows/ci.yml`) has the jobs `test`, `render (public)`, `render (private)`, `gitleaks`, `actionlint`
and the aggregate `ci-result`; `pr-title` is a separate workflow. The `render` jobs do what a new repo does: render
with default answers, commit, run `just ci`. CI uses only GitHub-owned actions pinned by SHA; uv, just, gitleaks and
actionlint come from their release archives through `scripts/install-tools`, which checks each one against a pinned
sha256 and the release checksum file.

The template uses `[[ ]]` and `[% %]` as Jinja delimiters (`_envops` in `copier.yml`), because workflows and
justfiles use `{{ }}`. Only files ending in `.jinja` are rendered; the rest are copied as they are. A file or folder
whose name renders to an empty string is skipped, which is how the optional files work.

### Release

Merge to `main`, then tag `vX.Y.Z` (SemVer: a new question or file is minor, a fix is patch, a change that needs
manual steps in generated repos is major). `copier copy` and `copier update` use the latest tag.

## Licence

MIT, see [LICENSE](LICENSE).
