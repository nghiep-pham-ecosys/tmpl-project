"""Static checks on the template repo itself: action pins, tool pins and the Copier version stay in step.

No rendering here, so these run without uvx. Stdlib unittest only.
"""

from __future__ import annotations

import os
import re
import tomllib
import unittest
from pathlib import Path

from _kit import COPIER_VERSION, TEMPLATE

ROOT_WORKFLOWS = TEMPLATE / ".github" / "workflows"
TEMPLATE_WORKFLOWS = TEMPLATE / "template" / ".github" / "workflows"
INSTALL_TOOLS = TEMPLATE / "scripts" / "install-tools"
USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)")
# ADR 0002: GitHub-owned actions only in these workflows (the org also allows four third-party patterns,
# which the template does not need). Pinned by a full 40-character commit SHA.
ALLOWED_ACTION = re.compile(r"^(actions|github)/[\w.-]+(/[\w./-]+)?@[0-9a-f]{40}$")


def uses_lines(path: Path) -> list[str]:
    return [m.group(1) for line in path.read_text(encoding="utf-8").splitlines() if (m := USES.match(line))]


def mise_tools(path: Path) -> dict[str, str]:
    return tomllib.loads(path.read_text(encoding="utf-8"))["tools"]


def script_pins() -> dict[str, str]:
    text = INSTALL_TOOLS.read_text(encoding="utf-8")
    return dict(re.findall(r"(?m)^([A-Z]+_(?:VERSION|SHA256))=(\S+)$", text))


def workflow_env(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    return dict(re.findall(r"(?m)^  ([A-Z0-9_]+): (\S+)$", text))


class RepoTest(unittest.TestCase):
    def test_actions_are_github_owned_and_sha_pinned(self) -> None:
        files = sorted(ROOT_WORKFLOWS.glob("*.yml")) + sorted(TEMPLATE_WORKFLOWS.glob("*"))
        self.assertTrue(files)
        for path in files:
            for ref in uses_lines(path):
                with self.subTest(file=path.name, uses=ref):
                    self.assertRegex(ref, ALLOWED_ACTION)

    def test_root_and_generated_ci_use_the_same_action_pins(self) -> None:
        root = set(uses_lines(ROOT_WORKFLOWS / "ci.yml"))
        generated = set(uses_lines(TEMPLATE_WORKFLOWS / "ci.yml.jinja"))
        self.assertEqual(root, generated)

    def test_pr_title_is_the_same_in_both(self) -> None:
        self.assertEqual(
            (ROOT_WORKFLOWS / "pr-title.yml").read_text(encoding="utf-8"),
            (TEMPLATE_WORKFLOWS / "pr-title.yml").read_text(encoding="utf-8"),
        )

    def test_install_tools_matches_mise_pins(self) -> None:
        self.assertTrue(os.access(INSTALL_TOOLS, os.X_OK), "scripts/install-tools is not executable")
        pins = script_pins()
        root = mise_tools(TEMPLATE / ".mise.toml")
        for tool in ("uv", "just", "gitleaks", "actionlint"):
            with self.subTest(tool=tool):
                self.assertEqual(pins[f"{tool.upper()}_VERSION"], root[tool])
                self.assertRegex(pins[f"{tool.upper()}_SHA256"], r"^[0-9a-f]{64}$")

    def test_generated_pins_match_install_tools(self) -> None:
        pins = script_pins()
        generated = mise_tools(TEMPLATE / "template" / ".mise.toml")
        root = mise_tools(TEMPLATE / ".mise.toml")
        env = workflow_env(TEMPLATE_WORKFLOWS / "ci.yml.jinja")
        for tool in ("just", "gitleaks", "actionlint"):
            with self.subTest(tool=tool):
                self.assertEqual(generated[tool], root[tool])
        for key in ("GITLEAKS_VERSION", "GITLEAKS_SHA256", "ACTIONLINT_VERSION", "ACTIONLINT_SHA256"):
            with self.subTest(key=key):
                self.assertEqual(env[key], pins[key])

    def test_copier_version_is_the_same_everywhere(self) -> None:
        self.assertEqual(workflow_env(ROOT_WORKFLOWS / "ci.yml")["COPIER_VERSION"], COPIER_VERSION)
        for name in ("README.md", "copier.yml"):
            with self.subTest(file=name):
                found = set(re.findall(r"copier==([\d.]+)", (TEMPLATE / name).read_text(encoding="utf-8")))
                self.assertEqual(found, {COPIER_VERSION})


if __name__ == "__main__":
    unittest.main()
