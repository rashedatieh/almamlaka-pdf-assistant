"""Abort unless the active gcloud project is exactly $GCP_PROJECT.

First prerequisite of every Make target that touches GCP (PROJECT_PLAN §3.6, ACCEPTANCE_TESTS Q-05).
It reads the local gcloud configuration and the labels of GCP_PROJECT (one read-only call on that
project only). Nothing is listed and no other project is read.

Checks, in order:
  1. GCP_PROJECT (environment, else .env) is set and is a well-formed project ID.
  2. CLOUDSDK_CORE_PROJECT is unset or equal to GCP_PROJECT (it overrides any configuration).
  3. The gcloud configuration "almamlaka" exists and its project equals GCP_PROJECT.
  4. That project carries the label app=almamlaka-assistant, set only by docs/SETUP_ACCOUNTS.md
     step A, so a mistyped ID that names another existing project is refused.

Usage: uv run python -m tools.gcp_guard        Exit codes: 0 ok, 2 refused.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

CONFIG_NAME = "almamlaka"
APP_LABEL = "almamlaka-assistant"
ROOT = Path(__file__).resolve().parent.parent
# Project ID rules: 6-30 chars, lowercase letters, digits and hyphens, starts with a letter,
# does not end with a hyphen (docs/adr/0001-stack-and-models.md, "GCP project setup").
PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
# Command verified in docs/adr/0001-stack-and-models.md ("gcloud CLI").
GET_PROJECT_ARGS = ["config", "get", "project"]


def label_args(project: str) -> list[str]:
    """`gcloud projects describe` of GCP_PROJECT only, printing its app label."""
    return ["projects", "describe", project, "--format=value(labels.app)"]


GcloudRunner = Callable[[list[str], Mapping[str, str]], str]


class GuardError(Exception):
    """The active GCP context is not the dedicated project; refuse to continue."""


def read_dotenv(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE reader for .env (comments and blank lines ignored)."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    # utf-8-sig: Windows editors may save .env with a byte-order mark.
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip().removeprefix("export ")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def expected_project(env: Mapping[str, str], dotenv_path: Path = ROOT / ".env") -> str:
    project = env.get("GCP_PROJECT") or read_dotenv(dotenv_path).get("GCP_PROJECT", "")
    if not project:
        raise GuardError("GCP_PROJECT is not set (environment or .env).")
    if not PROJECT_ID_RE.fullmatch(project):
        raise GuardError(f"GCP_PROJECT={project!r} is not a valid project ID.")
    return project


def run_gcloud(args: list[str], env: Mapping[str, str]) -> str:
    """Run gcloud with the given environment and return stripped stdout."""
    gcloud = shutil.which("gcloud")  # resolves gcloud.cmd on Windows
    if gcloud is None:
        raise GuardError("gcloud CLI not found on PATH.")
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argument list, resolved executable, no shell
            [gcloud, *args],
            env=dict(env),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise GuardError(f"gcloud {' '.join(args)} did not complete: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        raise GuardError(f"gcloud {' '.join(args)} failed: {detail[-1] if detail else proc.returncode}")
    return proc.stdout.strip()


def check(
    env: Mapping[str, str] | None = None, runner: GcloudRunner = run_gcloud, dotenv_path: Path = ROOT / ".env"
) -> str:
    """Return the verified project ID, or raise GuardError."""
    env = dict(os.environ if env is None else env)
    project = expected_project(env, dotenv_path)

    override = env.get("CLOUDSDK_CORE_PROJECT")
    if override and override != project:
        raise GuardError(f"CLOUDSDK_CORE_PROJECT={override!r} overrides the configuration; unset it.")

    gcloud_env = {**env, "CLOUDSDK_ACTIVE_CONFIG_NAME": CONFIG_NAME}
    active = runner(GET_PROJECT_ARGS, gcloud_env)
    if active != project:
        shown = active or "(unset)"
        raise GuardError(f"gcloud configuration {CONFIG_NAME!r} points at {shown!r}, expected {project!r}.")

    label = runner(label_args(project), gcloud_env)
    if label != APP_LABEL:
        raise GuardError(
            f"project {project!r} is not labelled app={APP_LABEL}, so it is not the project created in "
            "docs/SETUP_ACCOUNTS.md step A."
        )
    return project


def main() -> int:
    try:
        project = check()
    except GuardError as exc:
        print(f"gcp-guard: REFUSED - {exc}", file=sys.stderr)
        print("gcp-guard: see docs/SETUP_ACCOUNTS.md step A (gcloud configuration).", file=sys.stderr)
        return 2
    print(f"gcp-guard: ok - configuration {CONFIG_NAME!r} -> project {project!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
