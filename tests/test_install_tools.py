"""Run scripts/install-tools offline: a fake curl serves synthetic archives and checksum files.

The real release archives need network, so the test copies the script, swaps the pinned hashes for the hashes of
synthetic archives, and checks both checksum line formats: "<sha>  <file>" and uv's binary-mode "<sha> *<file>".
Stdlib unittest only; synthetic data only.
"""

from __future__ import annotations

import hashlib
import io
import os
import platform
import re
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from _kit import TEMPLATE

INSTALL_TOOLS = TEMPLATE / "scripts" / "install-tools"
UV_ARCHIVE = "uv-x86_64-unknown-linux-gnu.tar.gz"

FAKE_CURL = """#!/usr/bin/env bash
# Fake curl: serve files from $FAKE_SERVE by URL basename and log each URL.
out=""
url=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    --retry) shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
echo "${url}" >> "${FAKE_SERVE}/urls.log"
cp "${FAKE_SERVE}/${url##*/}" "${out}"
"""


def tool_stub(name: str) -> bytes:
    return f"#!/bin/sh\necho '{name} 0.0.0-test'\n".encode()


def make_archive(path: Path, members: dict[str, bytes]) -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(data))
    path.write_bytes(buf.getvalue())
    return hashlib.sha256(buf.getvalue()).hexdigest()


def pins(text: str) -> dict[str, str]:
    return dict(re.findall(r"(?m)^([A-Z]+_(?:VERSION|SHA256))=(\S+)$", text))


@unittest.skipUnless(platform.system() == "Linux" and platform.machine() == "x86_64", "install-tools is Linux x86_64 only")
class InstallToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="install-tools-")
        self.tmp = Path(self._tmp.name)
        self.serve = self.tmp / "serve"
        self.bin = self.tmp / "fakebin"
        self.serve.mkdir()
        self.bin.mkdir()
        curl = self.bin / "curl"
        curl.write_text(FAKE_CURL, encoding="utf-8")
        curl.chmod(0o755)

        text = INSTALL_TOOLS.read_text(encoding="utf-8")
        just_version = pins(text)["JUST_VERSION"]
        self.just_archive = f"just-{just_version}-x86_64-unknown-linux-musl.tar.gz"
        self.uv_sha = make_archive(
            self.serve / UV_ARCHIVE,
            {
                "uv-x86_64-unknown-linux-gnu/uv": tool_stub("uv"),
                "uv-x86_64-unknown-linux-gnu/uvx": tool_stub("uvx"),
            },
        )
        self.just_sha = make_archive(self.serve / self.just_archive, {"just": tool_stub("just")})
        text = re.sub(r"(?m)^UV_SHA256=\S+$", f"UV_SHA256={self.uv_sha}", text)
        text = re.sub(r"(?m)^JUST_SHA256=\S+$", f"JUST_SHA256={self.just_sha}", text)
        self.script = self.tmp / "install-tools"
        self.script.write_text(text, encoding="utf-8")
        self.script.chmod(0o755)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_script(self, *tools: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}", FAKE_SERVE=str(self.serve))
        dest = self.tmp / "out"
        return subprocess.run(
            [str(self.script), str(dest), *tools], capture_output=True, text=True, env=env, timeout=60
        )

    def write_sums(self, uv_line: str) -> None:
        # uv publishes one .sha256 file per archive in binary mode; just publishes SHA256SUMS in text mode.
        (self.serve / f"{UV_ARCHIVE}.sha256").write_text(uv_line + "\n", encoding="utf-8")
        other = "0" * 64
        (self.serve / "SHA256SUMS").write_text(
            f"{other}  just-other.tar.gz\n{self.just_sha}  {self.just_archive}\n", encoding="utf-8"
        )

    def test_accepts_binary_and_text_mode_checksum_lines(self) -> None:
        self.write_sums(f"{self.uv_sha} *{UV_ARCHIVE}")
        result = self.run_script("uv", "just")
        self.assertEqual(result.returncode, 0, result.stderr)
        out = self.tmp / "out"
        for name in ("uv", "uvx", "just"):
            with self.subTest(binary=name):
                self.assertTrue(os.access(out / name, os.X_OK))
        self.assertIn("uv 0.0.0-test", result.stdout)
        self.assertIn("just 0.0.0-test", result.stdout)
        urls = (self.serve / "urls.log").read_text(encoding="utf-8").split()
        self.assertTrue(all(u.startswith("https://github.com/") for u in urls), urls)

    def test_accepts_text_mode_uv_line(self) -> None:
        self.write_sums(f"{self.uv_sha}  {UV_ARCHIVE}")
        result = self.run_script("uv")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_a_pin_missing_from_the_checksum_file(self) -> None:
        self.write_sums(f"{'f' * 64} *{UV_ARCHIVE}")
        result = self.run_script("uv")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not in", result.stderr)

    def test_rejects_a_pin_listed_for_another_file(self) -> None:
        self.write_sums(f"{self.uv_sha} *uv-aarch64-unknown-linux-gnu.tar.gz")
        result = self.run_script("uv")
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
