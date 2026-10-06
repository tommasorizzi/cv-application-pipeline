import json
import subprocess
from pathlib import Path
import pytest
from app.codex_runner import CodexRunner, CodexRunnerError, CodexUsageLimitError
from app.models import Review


@pytest.fixture
def configured_runner(monkeypatch):
    monkeypatch.setattr("app.codex_runner.resolve_codex_executable", lambda: "/fixture/codex")


def test_runner_uses_stdin_readonly_and_repairs_invalid_output(tmp_path, monkeypatch, configured_runner):
    calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "not-for-use")
    def execute(command, **kwargs):
        calls.append((command, kwargs))
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text("not-json" if len(calls) == 1 else json.dumps({"approved": True, "findings": [], "checked_claim_paths": []}))
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(subprocess, "run", execute)
    result = CodexRunner().run("Review", {"text": "private job"}, Review, tmp_path, "test")
    assert result["approved"] and len(calls) == 2
    assert calls[0][0][-1] == "-" and "private job" not in " ".join(calls[0][0])
    assert "read-only" in calls[0][0]
    assert calls[0][0][0] == "/fixture/codex"
    assert "OPENAI_API_KEY" not in calls[0][1]["env"]
    assert "not-json" in calls[1][1]["input"]
    assert (tmp_path / "test.response-0.json").read_text() == "not-json"


def test_runner_propagates_auth_failure_without_fallback(tmp_path, monkeypatch, configured_runner):
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", "authentication unavailable"))
    with pytest.raises(CodexRunnerError, match="authentication"):
        CodexRunner().run("Review", {}, Review, tmp_path, "audit")


def test_usage_limit_is_reported_without_auth_retries(tmp_path, monkeypatch, configured_runner):
    calls = []
    def execute(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, "", "ERROR: You’ve hit your usage limit. Please try again at 7:01 PM.")
    monkeypatch.setattr(subprocess, "run", execute)
    with pytest.raises(CodexUsageLimitError, match="reset at 7:01 PM"):
        CodexRunner().run("Review", {}, Review, tmp_path, "audit")
    assert len(calls) == 1


def test_timeout_retains_live_diagnostics(tmp_path, monkeypatch, configured_runner):
    def execute(command, **kwargs):
        kwargs["stderr"].write("A transport retry is pending.\n")
        kwargs["stderr"].flush()
        raise subprocess.TimeoutExpired(command, 1)
    monkeypatch.setattr(subprocess, "run", execute)
    with pytest.raises(CodexRunnerError, match="timed out"):
        CodexRunner(timeout=1).run("Review", {}, Review, tmp_path, "audit")
    assert "transport retry" in (tmp_path / "audit.log-0.txt").read_text()


def test_resolver_finds_latest_native_vscode_binary_without_path(tmp_path, monkeypatch):
    from app.codex_runner import resolve_codex_executable
    monkeypatch.delenv("CV_CODEX_BIN", raising=False)
    monkeypatch.setattr("app.codex_runner.shutil.which", lambda name: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("app.codex_runner.platform.system", lambda: "Linux")
    monkeypatch.setattr("app.codex_runner.platform.machine", lambda: "x86_64")
    def executable(version, architecture="linux-x86_64"):
        path = tmp_path / f".vscode/extensions/openai.chatgpt-{version}/bin/{architecture}/codex"
        path.parent.mkdir(parents=True)
        path.touch()
        path.chmod(0o755)
        return path
    executable("2.9.0-linux-x64")
    chosen = executable("2.10.0-linux-x64")
    executable("3.0.0-linux-arm64", "linux-aarch64")
    assert resolve_codex_executable() == str(chosen)


def test_invalid_explicit_binary_does_not_silently_fall_back(monkeypatch):
    from app.codex_runner import resolve_codex_executable
    monkeypatch.setenv("CV_CODEX_BIN", "/nonexistent/codex")
    with pytest.raises(CodexRunnerError, match="CV_CODEX_BIN"):
        resolve_codex_executable()


def test_missing_binary_has_actionable_error(tmp_path, monkeypatch):
    from app.codex_runner import resolve_codex_executable
    monkeypatch.delenv("CV_CODEX_BIN", raising=False)
    monkeypatch.setattr("app.codex_runner.shutil.which", lambda name: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with pytest.raises(CodexRunnerError, match="Set CV_CODEX_BIN"):
        resolve_codex_executable()
