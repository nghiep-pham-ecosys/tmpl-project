"""Render the template for several answer sets and check the generated repos.

Runs Copier through uvx at a pinned version (tests/_kit.py), so the test needs uv on PATH (mise installs it).
Stdlib unittest; PyYAML is used when present for stricter YAML checks.
"""

from __future__ import annotations

import random
import re
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from _kit import TEMPLATE, copier_command, git, missing_tools, render, tool_env

try:
    import yaml
except ImportError:  # the checks fall back to regexes
    yaml = None

# The base list of ADR 0005 §1: README, project.yaml and a CLAUDE.md stub; LICENSE (MIT) and NOTICE, with the
# optional LICENSE-content (CC BY 4.0) checked in test_optional_files_follow_answers; justfile and .mise.toml;
# CI with gitleaks, ci-result and pr-title; the private pre-push hook (also in that test). The rest supports them.
BASE_FILES = (
    ".copier-answers.yml",
    ".github/workflows/ci.yml",
    ".github/workflows/pr-title.yml",
    ".gitignore",
    ".gitleaks-worktree.toml",
    ".mise.toml",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "NOTICE",
    "README.md",
    "justfile",
    "project.yaml",
)

CASES = {
    "public-python": {
        "project_name": "acme-lab",
        "visibility": "public",
        "python": True,
        "content_licence": True,
        "area": "lab",
    },
    "private-plain": {
        "project_name": "example-notes",
        "visibility": "private",
        "python": False,
        "content_licence": False,
        "area": "learn",
        "status": "paused",
    },
    "private-python": {
        "project_name": "example-co-tools",
        "visibility": "private",
        "python": True,
        "content_licence": True,
        "area": "ecosys",
    },
}

SHA_PIN = re.compile(r"^\s*-?\s*uses:\s*[\w.-]+/[\w./-]+@[0-9a-f]{40}(\s|$)")
# Template delimiters left in the output (the template always writes "[[ name ]]" with spaces).
# Bash tests such as [[ "$x" ]] and TOML tables such as [[allowlists]] in verbatim files do not match.
LEFTOVER = re.compile(r"\[\[ [a-z_]|\[% |\[# ")


# Paths that .gitignore keeps out of commits and the working-tree scan skips. A secret force-added
# under any of them must still fail the history scan, except node_modules/: the gitleaks default
# rules (upstream, not this template) allowlist it in every scan mode.
IGNORED_SECRET_PATHS = (".env", ".env.local", ".venv/lib/leak.txt", "node_modules/pkg/leak.txt")
HISTORY_SECRET_PATHS = tuple(p for p in IGNORED_SECRET_PATHS if not p.startswith("node_modules/"))


def fake_aws_key() -> str:
    """An AWS-style access key id built at run time, so no key literal sits in this file.

    The AWS docs example key ends in EXAMPLE, which the default gitleaks rules allow.
    """
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    return "AKIA" + "".join(random.SystemRandom().choice(alphabet) for _ in range(16))


def gitleaks(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gitleaks", *args, "--redact", "--no-banner", "."], capture_output=True, text=True, cwd=cwd, timeout=120
    )


@unittest.skipIf(copier_command() is None, "uvx not found: run `mise install` (uv) first")
class RenderTest(unittest.TestCase):
    tmp: tempfile.TemporaryDirectory
    out: dict[str, Path]

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory(prefix="tmpl-project-")
        cls.out = {}
        for name, answers in CASES.items():
            dest = Path(cls.tmp.name) / name
            result = render(dest, answers)
            if result.returncode != 0:
                raise AssertionError(f"copier failed for {name}:\n{result.stdout}\n{result.stderr}")
            cls.out[name] = dest

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def cases(self):
        """Yield (case name, output folder, answers); each test wraps its body in subTest."""
        for name, answers in CASES.items():
            yield name, self.out[name], answers

    def test_base_files_exist(self) -> None:
        for case, out, _ in self.cases():
            with self.subTest(case=case):
                for rel in BASE_FILES:
                    self.assertTrue((out / rel).is_file(), f"{rel} missing")

    def test_optional_files_follow_answers(self) -> None:
        for case, out, answers in self.cases():
            with self.subTest(case=case):
                self.assertEqual((out / "LICENSE-content").exists(), answers["content_licence"])
                self.assertEqual((out / "tests/test_smoke.py").exists(), answers["python"])
                hook = out / ".githooks/pre-push"
                self.assertEqual(hook.exists(), answers["visibility"] == "private")
                self.assertEqual((out / ".githooks").exists(), answers["visibility"] == "private")
                if hook.exists():
                    self.assertTrue(hook.stat().st_mode & stat.S_IXUSR, "pre-push is not executable")

    def test_nothing_left_unrendered(self) -> None:
        for case, out, _ in self.cases():
            with self.subTest(case=case):
                for path in out.rglob("*"):
                    if not path.is_file():
                        continue
                    self.assertFalse(path.name.endswith(".jinja"), f"{path} kept its .jinja suffix")
                    text = path.read_text(encoding="utf-8")
                    self.assertIsNone(LEFTOVER.search(text), f"template syntax left in {path}")

    def test_project_card(self) -> None:
        for case, out, answers in self.cases():
            with self.subTest(case=case):
                text = (out / "project.yaml").read_text(encoding="utf-8")
                for key in ("name", "area", "status", "stack", "highlights", "links", "visibility"):
                    self.assertRegex(text, rf"(?m)^{key}:", f"project.yaml has no {key}")
                if yaml is not None:
                    card = yaml.safe_load(text)
                    self.assertEqual(card["name"], answers["project_name"])
                    self.assertEqual(card["area"], answers["area"])
                    self.assertEqual(card["status"], answers.get("status", "active"))
                    self.assertEqual(card["visibility"], answers["visibility"])
                    self.assertEqual(
                        card["links"]["repo"], f"https://github.com/nghiep-pham-ecosys/{answers['project_name']}"
                    )
                    self.assertEqual("python 3.12" in card["stack"], answers["python"])

    def test_workflows_pin_actions_and_aggregate(self) -> None:
        for case, out, answers in self.cases():
            with self.subTest(case=case):
                for wf in (out / ".github/workflows").glob("*.yml"):
                    for line in wf.read_text(encoding="utf-8").splitlines():
                        if re.match(r"^\s*-?\s*uses:", line):
                            self.assertRegex(line, SHA_PIN, f"{wf.name}: action not pinned by SHA: {line.strip()}")
                ci = (out / ".github/workflows/ci.yml").read_text(encoding="utf-8")
                if yaml is not None:
                    jobs = yaml.safe_load(ci)["jobs"]
                    expected = {"gitleaks", "actionlint"} | ({"test"} if answers["python"] else set())
                    self.assertEqual(set(jobs) - {"ci-result"}, expected)
                    self.assertEqual(set(jobs["ci-result"]["needs"]), expected)
                    self.assertEqual(jobs["ci-result"]["if"], "always()")

    def test_claude_stub_points_to_root(self) -> None:
        for case, out, answers in self.cases():
            with self.subTest(case=case):
                text = (out / "CLAUDE.md").read_text(encoding="utf-8")
                self.assertIn("../../CLAUDE.md", text)
                self.assertNotRegex(text, r"(?m)^@", "the stub must import nothing")
                self.assertIn(f"{answers['visibility']} repo", text)

    def test_justfile_recipes(self) -> None:
        for case, out, answers in self.cases():
            with self.subTest(case=case):
                text = (out / "justfile").read_text(encoding="utf-8")
                ci = re.search(r"(?m)^ci:(.*)$", text)
                self.assertIsNotNone(ci)
                deps = ci.group(1).split()
                self.assertEqual("test" in deps, answers["python"])
                self.assertIn("gitleaks", deps)
                self.assertIn("actionlint", deps)
                self.assertEqual(bool(re.search(r"(?m)^hooks:", text)), answers["visibility"] == "private")

    def test_mise_pins_match_ecosys(self) -> None:
        for case, out, _ in self.cases():
            with self.subTest(case=case):
                text = (out / ".mise.toml").read_text(encoding="utf-8")
                for line in ('just = "1.59.0"', 'gitleaks = "8.30.1"', 'actionlint = "1.7.12"'):
                    self.assertIn(line, text)

    @unittest.skipIf(shutil.which("actionlint") is None, "actionlint not on PATH")
    def test_actionlint_passes(self) -> None:
        for case, out, _ in self.cases():
            with self.subTest(case=case):
                files = sorted(str(p) for p in (out / ".github/workflows").glob("*.yml"))
                result = subprocess.run(["actionlint", *files], capture_output=True, text=True, cwd=out)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_generated_smoke_test_passes(self) -> None:
        for case, out, answers in self.cases():
            with self.subTest(case=case):
                if not answers["python"]:
                    continue
                result = subprocess.run(
                    ["python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
                    capture_output=True,
                    text=True,
                    cwd=out,
                    env=tool_env(Path(self.tmp.name)),
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def committed_copy(self, case: str, label: str) -> Path:
        """A fresh copy of a rendered repo with everything committed on main."""
        repo = Path(self.tmp.name) / "git" / f"{case}-{label}"
        shutil.copytree(self.out[case], repo)
        git("init", "-q", "-b", "main", cwd=repo)
        git("add", "-A", cwd=repo)
        git("commit", "-q", "-m", "chore: initial commit", cwd=repo)
        return repo

    def test_no_default_gitleaks_config(self) -> None:
        # gitleaks loads .gitleaks.toml by default, also for `gitleaks git`. The allowlist must stay
        # in the worktree-only file, which only `gitleaks dir --config` reads.
        for case, out, _ in self.cases():
            with self.subTest(case=case):
                self.assertFalse((out / ".gitleaks.toml").exists())
                justfile = (out / "justfile").read_text(encoding="utf-8")
                self.assertIn("gitleaks dir --config .gitleaks-worktree.toml", justfile)
                for line in justfile.splitlines():
                    if "gitleaks git" in line:
                        self.assertNotIn("--config", line)
                for path in (out / ".github/workflows/ci.yml", out / ".githooks/pre-push"):
                    if path.exists():
                        self.assertNotIn("gitleaks-worktree", path.read_text(encoding="utf-8"))

    @unittest.skipIf(shutil.which("gitleaks") is None, "gitleaks not on PATH")
    def test_clean_repo_passes_gitleaks(self) -> None:
        for case in CASES:
            with self.subTest(case=case):
                repo = self.committed_copy(case, "clean")
                result = gitleaks("dir", "--config", ".gitleaks-worktree.toml", cwd=repo)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                result = gitleaks("git", cwd=repo)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipIf(shutil.which("gitleaks") is None, "gitleaks not on PATH")
    def test_worktree_scan_skips_only_ignored_paths(self) -> None:
        repo = self.committed_copy("public-python", "worktree")
        for rel in IGNORED_SECRET_PATHS:
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"aws_access_key_id = {fake_aws_key()}\n", encoding="utf-8")
        result = gitleaks("dir", "--config", ".gitleaks-worktree.toml", cwd=repo)
        self.assertEqual(result.returncode, 0, "worktree scan read a gitignored path:\n" + result.stdout)
        (repo / "notes.txt").write_text(f"aws_access_key_id = {fake_aws_key()}\n", encoding="utf-8")
        result = gitleaks("dir", "--config", ".gitleaks-worktree.toml", cwd=repo)
        self.assertNotEqual(result.returncode, 0, "worktree scan missed a secret in a normal file")

    @unittest.skipIf(shutil.which("gitleaks") is None, "gitleaks not on PATH")
    def test_force_committed_secret_fails_history_scan(self) -> None:
        for case, _, answers in self.cases():
            for rel in HISTORY_SECRET_PATHS:
                with self.subTest(case=case, path=rel):
                    repo = self.committed_copy(case, "leak-" + re.sub(r"\W", "_", rel))
                    base = git("rev-parse", "HEAD", cwd=repo)
                    path = repo / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(f"aws_access_key_id = {fake_aws_key()}\n", encoding="utf-8")
                    git("check-ignore", "-q", rel, cwd=repo)  # raises if .gitignore does not cover it
                    git("add", "-f", rel, cwd=repo)
                    git("commit", "-q", "-m", "chore: leak", cwd=repo)
                    head = git("rev-parse", "HEAD", cwd=repo)
                    result = gitleaks("git", cwd=repo)
                    self.assertNotEqual(result.returncode, 0, f"gitleaks git missed a committed {rel}")
                    if answers["visibility"] != "private":
                        continue
                    hook = subprocess.run(
                        [str(repo / ".githooks/pre-push"), "origin", "git@example.com:acme/x.git"],
                        input=f"refs/heads/main {head} refs/heads/main {base}\n",
                        capture_output=True,
                        text=True,
                        cwd=repo,
                        timeout=120,
                    )
                    self.assertNotEqual(hook.returncode, 0, f"pre-push let a committed {rel} through")
                    self.assertIn("Push blocked", hook.stderr)

    @unittest.skipIf(missing_tools("just", "gitleaks", "actionlint"), "just, gitleaks or actionlint not on PATH")
    def test_generated_just_ci_passes(self) -> None:
        # What a new repo runs first: `just ci` on a fresh commit, the same recipe its CI mirrors.
        for case in CASES:
            with self.subTest(case=case):
                repo = self.committed_copy(case, "just-ci")
                env = tool_env(Path(self.tmp.name))
                result = subprocess.run(["just", "ci"], capture_output=True, text=True, cwd=repo, env=env, timeout=300)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_copyright_year_is_the_render_year(self) -> None:
        # No case passes copyright_year, so the default applies: the year of the render, not a literal.
        year = time.strftime("%Y")
        for case, out, _ in self.cases():
            with self.subTest(case=case):
                self.assertIn(f"Copyright (c) {year} Nghiep Pham", (out / "LICENSE").read_text(encoding="utf-8"))
                answers = (out / ".copier-answers.yml").read_text(encoding="utf-8")
                self.assertRegex(answers, rf"(?m)^copyright_year: {year}$")
        config = (TEMPLATE / "copier.yml").read_text(encoding="utf-8")
        block = re.search(r"(?ms)^copyright_year:\n(.*?)(?=^\S)", config)
        self.assertIsNotNone(block)
        self.assertRegex(block.group(1), r"default: .*strftime", "copyright_year default must not be a literal year")
        self.assertNotIn("_jinja_extensions", config, "a Jinja extension would make every render need --trust")

    def test_bad_project_name_is_refused(self) -> None:
        dest = Path(self.tmp.name) / "bad-name"
        result = render(dest, {"project_name": "Bad_Name"})
        self.assertNotEqual(result.returncode, 0, "copier accepted an invalid project_name")


if __name__ == "__main__":
    unittest.main()
