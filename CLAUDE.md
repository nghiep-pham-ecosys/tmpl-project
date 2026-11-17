# tmpl-project: agent notes

Copier template for new repos in the `nghiep-pham-ecosys` org (spec §5.5, ecosys#7). Area `ecosys`.

- The workspace rules apply: read `../../CLAUDE.md` (the `ecosys` root) first. This file imports nothing.
- `copier.yml` holds the questions; `template/` is what gets rendered. See `README.md`.
- Jinja delimiters are `[[ ]]` and `[% %]`. Never write bash `[[` in a `.jinja` file.
- After any change run `just ci`: static pin checks (`tests/test_repo.py`), an offline run of
  `scripts/install-tools` (`tests/test_install_tools.py`), every answer set in
  `tests/test_render.py` including `just ci` in each generated repo, and a `copier update` run (`tests/test_update.py`).
- Run it with temp output in the workspace scratch folder, for example
  `TMPDIR=<root>/.tmp-session/<session>/kit mise exec -- just ci`.
- Keep tool pins and action SHAs in step with the ecosys root (`.mise.toml`, `.github/workflows/ci.yml`).
  A tool bump touches `.mise.toml`, `template/.mise.toml`, `scripts/install-tools` and `template/.github/workflows/ci.yml.jinja`;
  `tests/test_repo.py` fails until all four agree.
- Release: tag `vX.Y.Z` on `main`. `copier copy` and `copier update` use the latest tag, so an untagged change reaches nobody.
