"""ACCEPTANCE_TESTS Q-05: GCP-touching targets abort unless the active project is GCP_PROJECT.

gcloud is replaced by a fake runner that simulates named configurations and project labels, so
these tests need no gcloud installation and never touch a real project.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from tools import gcp_guard as g

PROJECT = "getai-almamlaka-assist-x1"
OTHER = "someone-elses-project"


class FakeGcloud:
    """Answers `gcloud config get project` from a {configuration: project} map and
    `gcloud projects describe P --format=value(labels.app)` from a {project: label} map."""

    def __init__(self, projects_by_config: dict[str, str], labels: dict[str, str] | None = None) -> None:
        self.projects_by_config = projects_by_config
        self.labels = {PROJECT: g.APP_LABEL} if labels is None else labels
        self.calls: list[tuple[list[str], str | None]] = []

    def __call__(self, args: list[str], env: Mapping[str, str]) -> str:
        config = env.get("CLOUDSDK_ACTIVE_CONFIG_NAME")
        self.calls.append((args, config))
        if config not in self.projects_by_config:
            raise g.GuardError(f"configuration [{config}] does not exist")
        if args == g.GET_PROJECT_ARGS:
            return self.projects_by_config[config]
        project = args[2]
        assert args == g.label_args(project), f"unexpected gcloud call: {args}"
        return self.labels.get(project, "")


@pytest.fixture
def no_dotenv(tmp_path: Path) -> Path:
    return tmp_path / ".env"  # does not exist


def test_accepts_matching_labelled_project(no_dotenv: Path) -> None:
    fake = FakeGcloud({"almamlaka": PROJECT})
    assert g.check({"GCP_PROJECT": PROJECT}, fake, no_dotenv) == PROJECT
    assert fake.calls == [(g.GET_PROJECT_ARGS, "almamlaka"), (g.label_args(PROJECT), "almamlaka")]


def test_refuses_when_configuration_points_elsewhere(no_dotenv: Path) -> None:
    fake = FakeGcloud({"almamlaka": OTHER})
    with pytest.raises(g.GuardError, match=OTHER):
        g.check({"GCP_PROJECT": PROJECT}, fake, no_dotenv)


def test_refuses_another_existing_project_named_by_mistake(no_dotenv: Path) -> None:
    # GCP_PROJECT and the configuration agree, but both name another (unlabelled) project.
    fake = FakeGcloud({"almamlaka": OTHER}, labels={OTHER: "other-bot"})
    with pytest.raises(g.GuardError, match="not labelled"):
        g.check({"GCP_PROJECT": OTHER}, fake, no_dotenv)


def test_refuses_project_without_label(no_dotenv: Path) -> None:
    fake = FakeGcloud({"almamlaka": PROJECT}, labels={})
    with pytest.raises(g.GuardError, match="not labelled"):
        g.check({"GCP_PROJECT": PROJECT}, fake, no_dotenv)


def test_always_reads_the_almamlaka_configuration(no_dotenv: Path) -> None:
    # Another configuration is active globally; the guard must still read "almamlaka" only.
    fake = FakeGcloud({"default": OTHER, "almamlaka": PROJECT})
    env = {"GCP_PROJECT": PROJECT, "CLOUDSDK_ACTIVE_CONFIG_NAME": "default"}
    assert g.check(env, fake, no_dotenv) == PROJECT
    assert [config for _, config in fake.calls] == ["almamlaka", "almamlaka"]


def test_refuses_when_configuration_is_missing(no_dotenv: Path) -> None:
    fake = FakeGcloud({"default": OTHER})
    with pytest.raises(g.GuardError, match="does not exist"):
        g.check({"GCP_PROJECT": PROJECT}, fake, no_dotenv)


def test_refuses_when_configuration_has_no_project(no_dotenv: Path) -> None:
    fake = FakeGcloud({"almamlaka": ""})
    with pytest.raises(g.GuardError, match="unset"):
        g.check({"GCP_PROJECT": PROJECT}, fake, no_dotenv)


def test_refuses_env_override_of_project(no_dotenv: Path) -> None:
    fake = FakeGcloud({"almamlaka": PROJECT})
    env = {"GCP_PROJECT": PROJECT, "CLOUDSDK_CORE_PROJECT": OTHER}
    with pytest.raises(g.GuardError, match="CLOUDSDK_CORE_PROJECT"):
        g.check(env, fake, no_dotenv)
    assert fake.calls == []


@pytest.mark.parametrize("value", ["", "Bad_Project", "short", "ends-with-hyphen-", f"{PROJECT}\n"])
def test_refuses_missing_or_malformed_gcp_project(no_dotenv: Path, value: str) -> None:
    fake = FakeGcloud({"almamlaka": PROJECT})
    with pytest.raises(g.GuardError):
        g.check({"GCP_PROJECT": value}, fake, no_dotenv)
    assert fake.calls == []


def test_reads_gcp_project_from_dotenv(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"# local settings\nGCP_PROJECT={PROJECT}\n", encoding="utf-8")
    fake = FakeGcloud({"almamlaka": PROJECT})
    assert g.check({}, fake, dotenv) == PROJECT


def test_reads_dotenv_with_bom_and_export(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"export GCP_PROJECT={PROJECT}\n", encoding="utf-8-sig")
    fake = FakeGcloud({"almamlaka": PROJECT})
    assert g.check({}, fake, dotenv) == PROJECT


def test_environment_wins_over_dotenv(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"GCP_PROJECT={OTHER}\n", encoding="utf-8")
    fake = FakeGcloud({"almamlaka": PROJECT})
    assert g.check({"GCP_PROJECT": PROJECT}, fake, dotenv) == PROJECT


def test_missing_gcloud_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(g.shutil, "which", lambda _name: None)
    with pytest.raises(g.GuardError, match="not found"):
        g.run_gcloud(g.GET_PROJECT_ARGS, {})


@pytest.mark.parametrize("error", [subprocess.TimeoutExpired(cmd="gcloud", timeout=60), OSError("boom")])
def test_hung_or_broken_gcloud_is_a_refusal(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(g.shutil, "which", lambda _name: "gcloud")
    monkeypatch.setattr(g.subprocess, "run", fail)
    with pytest.raises(g.GuardError, match="did not complete"):
        g.run_gcloud(g.GET_PROJECT_ARGS, {})


def test_main_exits_2_on_refusal(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def refuse() -> str:
        raise g.GuardError("wrong project")

    monkeypatch.setattr(g, "check", refuse)
    assert g.main() == 2
    assert "REFUSED" in capsys.readouterr().err
