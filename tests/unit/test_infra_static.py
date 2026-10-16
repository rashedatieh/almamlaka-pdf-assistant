"""ACCEPTANCE_TESTS Q-06: every gcloud command in infra/, the Makefile and docs/SETUP_ACCOUNTS.md
addresses only $GCP_PROJECT, explicitly, and nothing lists or touches other projects or accounts.

A command line passes only when all of these hold:
  * It makes exactly one gcloud call and uses no forbidden command.
  * Every project it names is $GCP_PROJECT. That covers --project and --billing-project values,
    projects/<id> resource names, service-account e-mails, image paths and configuration values,
    and --configuration must be "almamlaka".
  * Commands in the projects, billing, config and auth groups match one of the exact allow-listed
    forms below; a --project flag never admits them. Every other command carries
    --project=$GCP_PROJECT outside any trailing comment.
NEGATIVE_CASES must all be rejected, so the scan cannot silently become permissive.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = sorted((ROOT / "infra").glob("*.sh"))
SETUP_DOC = ROOT / "docs" / "SETUP_ACCOUNTS.md"

PROJECT_REF = r'"?\$\{?GCP_PROJECT\}?"?'
OWN_PROJECT = re.compile(PROJECT_REF)
END = r"(?=[\s;|&)]|$)"
GCLOUD = re.compile(r"(?<![\w/.-])gcloud(?:\.cmd)?(?=\s)")
INLINE_COMMENT = re.compile(r"\s#.*$")

PROJECT_FLAG = re.compile(rf"(?<![\w-])--project[= ]{PROJECT_REF}{END}")
STRICT_GROUP = re.compile(
    r"(?<![\w/.-])gcloud(?:\.cmd)? (?:(?:alpha|beta) )?"
    r"(?:projects|billing|config|auth|organizations|resource-manager)\b"
)
EXACT_FORMS = [
    re.compile(
        r"gcloud projects (create|describe|get-iam-policy|add-iam-policy-binding|remove-iam-policy-binding) "
        + PROJECT_REF
        + END
    ),
    re.compile(r"gcloud billing projects link " + PROJECT_REF + END),
    re.compile(r'gcloud billing budgets create .*--filter-projects="?projects/\$\{?GCP_PROJECT\}?"?' + END),
    re.compile(r"gcloud config configurations (create|describe) almamlaka" + END),
    re.compile(r"gcloud config (set|get) \S+( \S+)* --configuration=almamlaka" + END),
    re.compile(r"gcloud auth list" + END),  # local: shows credentialed accounts, touches no project
]
# Each pattern captures a project ID, which must be $GCP_PROJECT.
PROJECT_VALUES = [
    ("--project", re.compile(r"(?<![\w-])--project[= ]([^\s;|&)]+)")),
    ("--billing-project", re.compile(r"(?<![\w-])--billing-project[= ]([^\s;|&)]+)")),
    ("projects/<id>", re.compile(r"(?<![\w-])projects/([^/\s;|&)\"']+)")),
    ("service-account e-mail", re.compile(r"@([^@\s;|&)\"']+)\.iam\.gserviceaccount\.com")),
    ("image path", re.compile(r"docker\.pkg\.dev/([^/\s;|&)\"']+)")),
    ("config project", re.compile(r"config set (?:core/)?project ([^\s;|&)]+)")),
]
CONFIGURATION = re.compile(r"(?<![\w-])--configuration[= ]([^\s;|&)]+)")
_G = r"gcloud(?:\.cmd)? (?:(?:alpha|beta) )?"
FORBIDDEN = [
    re.compile(_G + r"projects (list|search|delete|undelete|move)\b"),
    re.compile(_G + r"organizations\b"),
    re.compile(_G + r"billing (accounts|projects (list|unlink)|budgets (list|delete|update))\b"),
    re.compile(_G + r"resource-manager\b"),
    re.compile(_G + r"config configurations (activate|delete)\b"),
    re.compile(r"(?<![\w-])CLOUDSDK_[A-Z_]+="),  # inline overrides of the configuration or project
]


def violations(command: str) -> list[str]:
    """Why one gcloud command line breaks Q-06; empty when it is allowed."""
    problems: list[str] = []
    if len(GCLOUD.findall(command)) != 1:
        problems.append("not exactly one gcloud call on the line")
    problems += [f"forbidden: {rule.pattern}" for rule in FORBIDDEN if rule.search(command)]
    for what, rule in PROJECT_VALUES:
        problems += [f"{what} names {v!r}" for v in rule.findall(command) if not OWN_PROJECT.fullmatch(v)]
    problems += [f"--configuration={v}" for v in CONFIGURATION.findall(command) if v != "almamlaka"]
    code = INLINE_COMMENT.sub("", command)
    forms = EXACT_FORMS if STRICT_GROUP.search(code) else [PROJECT_FLAG]
    if not any(form.search(code) for form in forms):
        problems.append("not scoped to $GCP_PROJECT")
    return problems


def logical_lines(text: str) -> list[str]:
    """Join backslash continuations and drop comment lines."""
    joined = re.sub(r"\\\r?\n\s*", " ", text)
    return [line.strip() for line in joined.splitlines() if line.strip() and not line.strip().startswith("#")]


def fenced_code(markdown: str) -> str:
    return "\n".join(re.findall(r"```[a-z]*\n(.*?)```", markdown, flags=re.S))


def gcloud_commands() -> list[tuple[str, str]]:
    sources = [(p.name, p.read_text(encoding="utf-8")) for p in SCRIPTS]
    sources.append(("Makefile", (ROOT / "Makefile").read_text(encoding="utf-8")))
    sources.append((SETUP_DOC.name, fenced_code(SETUP_DOC.read_text(encoding="utf-8"))))
    return [(name, line) for name, text in sources for line in logical_lines(text) if GCLOUD.search(line)]


COMMANDS = gcloud_commands()

NEGATIVE_CASES = [
    'gcloud billing projects unlink other-1 --project="${GCP_PROJECT}"',
    'gcloud projects delete other-1 --project="${GCP_PROJECT}"',
    "gcloud projects add-iam-policy-binding other-1 --member=user:a@b.c --role=roles/viewer "
    '--project="${GCP_PROJECT}"',
    'gcloud beta projects list --project="${GCP_PROJECT}"',
    'gcloud billing projects list --billing-account=X --project="${GCP_PROJECT}"',
    'gcloud secrets versions access latest --secret=projects/other-1/secrets/k --project="${GCP_PROJECT}"',
    "gcloud config set core/project other-1 --configuration=almamlaka",
    "gcloud config set project other-1 --configuration=almamlaka",
    'gcloud config set project "${GCP_PROJECT}" --configuration=default',
    'gcloud config set project "${GCP_PROJECT}"',
    "gcloud run services delete x # --project=$GCP_PROJECT",
    "gcloud.cmd run services delete x",
    'gcloud run deploy app --image=me-central1-docker.pkg.dev/other-1/r/app --project="${GCP_PROJECT}"',
    'gcloud run deploy app --service-account=bot@other-1.iam.gserviceaccount.com --project="${GCP_PROJECT}"',
    "gcloud run services list --project=other-1",
    'gcloud run services list --project="${GCP_PROJECT}" --project=other-1',
    'gcloud run services list --billing-project=other-1 --project="${GCP_PROJECT}"',
    'CLOUDSDK_CORE_PROJECT=other-1 gcloud run services list --project="${GCP_PROJECT}"',
    "gcloud config configurations activate almamlaka",
    "gcloud organizations list",
    "gcloud billing accounts list",
    'gcloud billing budgets list --billing-account=X --billing-project="${GCP_PROJECT}"',
    "gcloud services enable run.googleapis.com",
    'gcloud run services list --project="${GCP_PROJECT}"; gcloud run services list',
]


def test_scan_is_not_vacuous() -> None:
    assert len(SCRIPTS) >= 7
    assert len(COMMANDS) >= 40
    assert any(name == SETUP_DOC.name for name, _ in COMMANDS)


@pytest.mark.parametrize(("source", "command"), COMMANDS)
def test_command_is_scoped_to_gcp_project(source: str, command: str) -> None:
    assert violations(command) == [], f"{source}: {command}"


@pytest.mark.parametrize("command", NEGATIVE_CASES)
def test_scan_rejects_commands_that_reach_other_projects(command: str) -> None:
    assert violations(command), f"Q-06 scan accepted: {command}"


@pytest.mark.parametrize("script", [p for p in SCRIPTS if p.name != "_common.sh"], ids=lambda p: p.name)
def test_step_scripts_use_the_shared_guards(script: Path) -> None:
    text = script.read_text(encoding="utf-8")
    assert 'source "$(dirname "$0")/_common.sh"' in text
    if not script.name.startswith("01_"):
        assert "require_almamlaka_config" in text


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_scripts_call_gcloud_directly(script: Path) -> None:
    # A wrapper, alias or variable would hide commands from this scan.
    text = script.read_text(encoding="utf-8")
    assert not re.search(r"\$\{?GCLOUD\b|alias gcloud|gcloud\s*\(\)", text)


def test_common_defaults_to_dry_run_and_pins_the_configuration() -> None:
    common = (ROOT / "infra" / "_common.sh").read_text(encoding="utf-8")
    assert 'APPLY="${APPLY:-0}"' in common
    assert "export CLOUDSDK_ACTIVE_CONFIG_NAME=almamlaka" in common
    assert "set -euo pipefail" in common
    # Service accounts used through variables are always derived from GCP_PROJECT.
    assert 'RUNTIME_SA="almamlaka-runtime@${GCP_PROJECT}.iam.gserviceaccount.com"' in common
    assert 'DEPLOYER_SA="almamlaka-deployer@${GCP_PROJECT}.iam.gserviceaccount.com"' in common
    # Later steps refuse a project that step A did not label.
    assert 'APP_LABEL="almamlaka-assistant"' in common
    assert '--format="value(labels.app)"' in common


def test_makefile_pins_the_configuration() -> None:
    assert "export CLOUDSDK_ACTIVE_CONFIG_NAME := almamlaka" in (ROOT / "Makefile").read_text(
        encoding="utf-8"
    )
