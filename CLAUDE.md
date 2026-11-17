# tmpl-project: agent notes

Copier template for new repos in the `nghiep-pham-ecosys` org (spec §5.5, ecosys#7). Area `ecosys`.

- The workspace rules apply: read `../../CLAUDE.md` (the `ecosys` root) first. This file imports nothing.
- `copier.yml` holds the questions; `template/` is what gets rendered. See `README.md`.
- Jinja delimiters are `[[ ]]` and `[% %]`. Never write bash `[[` in a `.jinja` file.
- After any change run `just ci`: it renders every answer set in `tests/test_render.py` and checks the output.
- Keep tool pins and action SHAs in step with the ecosys root (`.mise.toml`, `.github/workflows/ci.yml`).
