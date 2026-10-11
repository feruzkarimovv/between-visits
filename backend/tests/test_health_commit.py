"""Health `commit` inside a container image (no .git): GIT_COMMIT, then RENDER_GIT_COMMIT, 7 characters (WS0 R5)."""

from pathlib import Path

import pytest

from app import main


@pytest.fixture
def no_commit_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for var in main.COMMIT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_git_commit_env_wins(no_commit_env: pytest.MonkeyPatch) -> None:
    no_commit_env.setenv("GIT_COMMIT", "abc1234def5678")
    no_commit_env.setenv("RENDER_GIT_COMMIT", "0123456789abcdef0123456789abcdef01234567")
    assert main.git_commit() == "abc1234"


def test_render_git_commit_is_the_fallback(no_commit_env: pytest.MonkeyPatch) -> None:
    no_commit_env.setenv("GIT_COMMIT", "")  # docker-compose.prod.yml passes an empty value outside `make up`
    no_commit_env.setenv("RENDER_GIT_COMMIT", "0123456789abcdef0123456789abcdef01234567")
    assert main.git_commit() == "0123456"


def test_no_env_and_no_git_is_unknown(no_commit_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    no_commit_env.setattr(main, "ROOT", tmp_path)  # not a git checkout, like /app in the image
    no_commit_env.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert main.git_commit() == "unknown"
