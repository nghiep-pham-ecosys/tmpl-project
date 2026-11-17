"""Render the template for several answer sets and check the generated repos.

Runs Copier through uvx at a pinned version, so the test needs uv on PATH (mise installs it).
Stdlib unittest; PyYAML is used when present for stricter YAML checks.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # the checks fall back to regexes
    yaml = None

COPIER_VERSION = "9.19.1"
TEMPLATE = Path(__file__).resolve().parent.parent

BASE_FILES = (
    ".copier-answers.yml",
    ".github/workflows/ci.yml",
    ".github/workflows/pr-title.yml",
    ".gitignore",
    ".gitleaks.toml",
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


def copier_command() -> list[str] | None:
    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, "--from", f"copier=={COPIER_VERSION}", "copier"]
    return None


def render(dest: Path, answers: dict) -> subprocess.CompletedProcess:
    cmd = copier_command()
    assert cmd is not None
    args = [*cmd, "copy", "--defaults", "--quiet"]
    for key, value in answers.items():
        if isinstance(value, bool):
            value = "true" if value else "false"
        args += ["--data", f"{key}={value}"]
    args += [str(TEMPLATE), str(dest)]
    return subprocess.run(args, capture_output=True, text=True, timeout=600)


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
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_bad_project_name_is_refused(self) -> None:
        dest = Path(self.tmp.name) / "bad-name"
        result = render(dest, {"project_name": "Bad_Name"})
        self.assertNotEqual(result.returncode, 0, "copier accepted an invalid project_name")


if __name__ == "__main__":
    unittest.main()
