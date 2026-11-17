"""`copier update` brings a template change into generated repos without conflicts.

The test copies the template into a scratch git repo, tags v0.1.0, renders repos from the tag and commits them
with a local edit, then changes the template, tags v0.1.1 and runs a plain `copier update` in each repo (no ref,
so Copier picks the latest tag, as the README tells users). Stdlib unittest; Copier through uvx (tests/_kit.py).
"""

from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from _kit import TEMPLATE, copier, copier_command, git, render

CASES = {
    "public-python": {"project_name": "acme-lab", "visibility": "public", "python": True},
    "private-plain": {
        "project_name": "example-notes",
        "visibility": "private",
        "python": False,
        "content_licence": False,
    },
}

# One change to a rendered (.jinja) file and one to a file copied as it is.
CONTRIBUTING_LINE = "- Keep a pull request small: one issue, one change.\n"
GITIGNORE_LINE = ".ruff_cache/\n"
# A local edit in a file the template also renders; the three-way merge must keep it.
LOCAL_README = "\n## Local notes\n\nWritten in the generated repo; kept across template updates.\n"
CONFLICT_MARKER = re.compile(r"(?m)^(<<<<<<<|>>>>>>>) ")


@unittest.skipIf(copier_command() is None, "uvx not found: run `mise install` (uv) first")
class UpdateTest(unittest.TestCase):
    def test_update_applies_template_change_without_conflicts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmpl-update-") as tmp_name:
            tmp = Path(tmp_name)
            src = tmp / "tmpl-project"
            shutil.copytree(TEMPLATE, src, ignore=shutil.ignore_patterns(".git", "__pycache__", ".tmp-session"))
            git("init", "-q", "-b", "main", cwd=src)
            git("add", "-A", cwd=src)
            git("commit", "-q", "-m", "feat: template v0.1.0", cwd=src)
            git("tag", "v0.1.0", cwd=src)

            repos = {}
            for case, answers in CASES.items():
                dest = tmp / case
                result = render(dest, answers, src=src, ref="v0.1.0")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                git("init", "-q", "-b", "main", cwd=dest)
                git("add", "-A", cwd=dest)
                git("commit", "-q", "-m", "chore: generate from tmpl-project v0.1.0", cwd=dest)
                with (dest / "README.md").open("a", encoding="utf-8") as fh:
                    fh.write(LOCAL_README)
                git("commit", "-q", "-am", "docs: add local notes", cwd=dest)
                repos[case] = dest

            contributing = src / "template" / "CONTRIBUTING.md.jinja"
            text = contributing.read_text(encoding="utf-8")
            anchor = "- Tests use synthetic data only (Example Co, Acme).\n"
            self.assertIn(anchor, text)
            contributing.write_text(text.replace(anchor, anchor + CONTRIBUTING_LINE), encoding="utf-8")
            with (src / "template" / ".gitignore").open("a", encoding="utf-8") as fh:
                fh.write(GITIGNORE_LINE)
            git("commit", "-q", "-am", "feat: template v0.1.1", cwd=src)
            git("tag", "v0.1.1", cwd=src)

            for case, dest in repos.items():
                with self.subTest(case=case):
                    result = copier("update", "--defaults", "--quiet", cwd=dest)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

                    changed = set(git("diff", "--name-only", "HEAD", cwd=dest).splitlines())
                    self.assertEqual(changed, {".copier-answers.yml", ".gitignore", "CONTRIBUTING.md"})
                    new_files = git("ls-files", "--others", "--exclude-standard", cwd=dest)
                    self.assertEqual(new_files, "", "update left new files (for example .rej)")
                    for path in dest.rglob("*"):
                        if path.is_file() and ".git" not in path.parts:
                            self.assertIsNone(
                                CONFLICT_MARKER.search(path.read_text(encoding="utf-8", errors="replace")),
                                f"conflict markers in {path.name}",
                            )
                    self.assertIn(CONTRIBUTING_LINE, (dest / "CONTRIBUTING.md").read_text(encoding="utf-8"))
                    self.assertIn(GITIGNORE_LINE, (dest / ".gitignore").read_text(encoding="utf-8"))
                    self.assertIn(LOCAL_README, (dest / "README.md").read_text(encoding="utf-8"))
                    answers = (dest / ".copier-answers.yml").read_text(encoding="utf-8")
                    self.assertRegex(answers, r"(?m)^_commit: v0\.1\.1$")
                    self.assertRegex(answers, rf"(?m)^project_name: {CASES[case]['project_name']}$")


if __name__ == "__main__":
    unittest.main()
