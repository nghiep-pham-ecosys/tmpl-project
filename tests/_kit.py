"""Shared helpers for the template tests: Copier through uvx at a pinned version, git, tool lookup.

`python3 -m unittest discover -s tests` puts this folder on sys.path, so the tests import it as `_kit`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

COPIER_VERSION = "9.19.1"
TEMPLATE = Path(__file__).resolve().parent.parent

# Synthetic identity for commits in throwaway repos; signing off so no key is needed.
GIT = ["git", "-c", "user.name=Example Co", "-c", "user.email=dev@example.com", "-c", "commit.gpgsign=false"]


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run([*GIT, *args], capture_output=True, text=True, cwd=cwd, check=True)
    return result.stdout.strip()


def copier_command() -> list[str] | None:
    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, "--from", f"copier=={COPIER_VERSION}", "copier"]
    return None


def answer_args(answers: dict) -> list[str]:
    args: list[str] = []
    for key, value in answers.items():
        if isinstance(value, bool):
            value = "true" if value else "false"
        args += ["--data", f"{key}={value}"]
    return args


def copier(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    cmd = copier_command()
    assert cmd is not None, "uvx not found"
    return subprocess.run([*cmd, *args], capture_output=True, text=True, cwd=cwd, timeout=600)


def render(dest: Path, answers: dict, src: Path = TEMPLATE, ref: str = "HEAD") -> subprocess.CompletedProcess:
    """Render `src` at `ref` into `dest`.

    Copier picks the latest git tag when no ref is given; HEAD renders the working tree, including uncommitted
    changes, which is what a template change under test needs.
    """
    return copier("copy", "--defaults", "--quiet", "--vcs-ref", ref, *answer_args(answers), str(src), str(dest))


def tool_env(root: Path) -> dict[str, str]:
    """Environment for commands run inside generated repos.

    mise refuses an untrusted .mise.toml when a shim runs in a new folder; trusting the temp root avoids that.
    """
    return {**os.environ, "MISE_TRUSTED_CONFIG_PATHS": str(root), "PYTHONDONTWRITEBYTECODE": "1"}


def missing_tools(*names: str) -> list[str]:
    return [name for name in names if shutil.which(name) is None]
