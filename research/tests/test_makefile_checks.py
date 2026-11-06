"""Local quality gates must fail when tooling is missing or a check fails."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

MAKE = shutil.which("make")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(MAKE and os.name == "posix", "requires make and a POSIX shell")
class MakefileCheckTests(unittest.TestCase):
    def run_target(self, target, tools):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "research").mkdir()
            (root / "rust").mkdir()
            bin_dir = root / "bin"
            bin_dir.mkdir()
            shutil.copyfile(REPOSITORY_ROOT / "Makefile", root / "Makefile")
            log = root / "checks.log"
            for name, exit_code in tools.items():
                executable = bin_dir / name
                executable.write_text(
                    "#!/bin/sh\n"
                    f'printf \'%s\\n\' "{name} $*" >> "$CHECK_LOG"\n'
                    f"exit {exit_code}\n"
                )
                executable.chmod(0o755)
            result = subprocess.run(
                [MAKE, "--no-print-directory", target],
                cwd=root,
                env={**os.environ, "PATH": str(bin_dir), "CHECK_LOG": str(log)},
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            calls = log.read_text().splitlines() if log.exists() else []
            return result, calls

    def test_python_check_runs_every_gate(self):
        result, calls = self.run_target("python-check", {"python": 0, "ruff": 0, "pytest": 0})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["python -m compileall -q src tests", "ruff check .", "pytest -q"])

    def test_python_check_rejects_missing_tools(self):
        for missing in ("python", "ruff", "pytest"):
            with self.subTest(missing=missing):
                tools = {"python": 0, "ruff": 0, "pytest": 0}
                del tools[missing]
                result, _ = self.run_target("python-check", tools)
                self.assertNotEqual(result.returncode, 0, f"missing {missing} reported success")

    def test_python_check_stops_after_failure(self):
        for failing in ("python", "ruff", "pytest"):
            with self.subTest(failing=failing):
                tools = {"python": 0, "ruff": 0, "pytest": 0}
                tools[failing] = 1
                result, calls = self.run_target("python-check", tools)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(calls[-1].startswith(failing + " "), calls)

    def test_rust_check_runs_every_gate(self):
        result, calls = self.run_target("rust-check", {"cargo": 0})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls,
            [
                "cargo fmt --check",
                "cargo clippy --workspace --all-targets -- -D warnings",
                "cargo test --workspace",
            ],
        )

    def test_rust_check_rejects_missing_cargo(self):
        result, _ = self.run_target("rust-check", {})
        self.assertNotEqual(result.returncode, 0, "missing cargo reported success")

    def test_rust_check_stops_after_failure(self):
        result, calls = self.run_target("rust-check", {"cargo": 1})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, ["cargo fmt --check"])


if __name__ == "__main__":
    unittest.main()
