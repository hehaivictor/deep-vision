from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent

SERVER_RUNTIME_DEPS = [
    "flask",
    "flask-cors",
    "anthropic",
    "requests",
    "reportlab",
    "pillow",
    "jdcloud-sdk",
    "psycopg[binary]",
    "boto3",
]


@dataclass(frozen=True)
class SuiteCase:
    test_id: str
    label: str


@dataclass(frozen=True)
class SuiteExecution:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def build_unittest_command(cases: list[SuiteCase], *, quiet: bool = False, failfast: bool = False) -> list[str]:
    uv_path = shutil.which("uv")
    command: list[str]
    if uv_path:
        command = [uv_path, "run"]
        for dep in SERVER_RUNTIME_DEPS:
            command.extend(["--with", dep])
        command.extend(["python3", "-m", "unittest"])
    else:
        command = [sys.executable, "-m", "unittest"]

    if quiet:
        command.append("-q")
    if failfast:
        command.append("-f")

    for case in cases:
        command.append(case.test_id)
    return command


def run_suite_process(cases: list[SuiteCase], *, quiet: bool = False, failfast: bool = False) -> SuiteExecution:
    command = build_unittest_command(cases, quiet=quiet, failfast=failfast)
    completed = subprocess.run(
        command,
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    return SuiteExecution(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def print_suite_listing(*, suite_name: str, description: str, cases: list[SuiteCase]) -> int:
    print(f"Suite: {suite_name}")
    print(f"描述: {description}")
    for index, case in enumerate(cases, 1):
        print(f"{index}. {case.label}: {case.test_id}")
    return 0


def execute_suite(
    *,
    suite_name: str,
    title: str,
    description: str,
    cases: list[SuiteCase],
    quiet: bool = False,
    failfast: bool = False,
) -> int:
    print(f"{title} | suite={suite_name}")
    print(f"描述: {description}")
    print(f"用例数: {len(cases)}")
    execution = run_suite_process(cases, quiet=quiet, failfast=failfast)

    print("")
    if execution.stdout.strip():
        print(execution.stdout.rstrip())
    if execution.stderr.strip():
        print(execution.stderr.rstrip())
    print("")
    print(f"Command: {' '.join(execution.command)}")
    print(f"Exit code: {execution.returncode}")
    return 0 if execution.returncode == 0 else 2
