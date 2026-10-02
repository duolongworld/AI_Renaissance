import json
import stat
import subprocess

from data_sources.cninfo import CLI_NAME, CninfoDataSource


def _make_fake_cli(directory) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    cli = directory / "cninfo"
    cli.write_text("#!/bin/sh\nexit 0\n")
    cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    return str(cli)


def _cli_only_beside_interpreter(monkeypatch, directory) -> str:
    fake_cli = _make_fake_cli(directory)
    monkeypatch.setattr("data_sources.cninfo.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "data_sources.cninfo.sys.executable", str(directory / "python")
    )
    return fake_cli


def _capture_run(monkeypatch, stdout: str):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd, returncode=0, stdout=stdout, stderr=""
        )

    monkeypatch.setattr("data_sources.cninfo.subprocess.run", fake_run)
    return calls


def test_cli_found_beside_interpreter_when_not_on_path(tmp_path, monkeypatch):
    fake_cli = _cli_only_beside_interpreter(monkeypatch, tmp_path)

    ds = CninfoDataSource()

    assert ds._cli_path == fake_cli


def test_cli_on_path_takes_precedence(tmp_path, monkeypatch):
    on_path_cli = _make_fake_cli(tmp_path / "path_bin")
    monkeypatch.setattr(
        "data_sources.cninfo.shutil.which", lambda name: str(on_path_cli)
    )
    monkeypatch.setattr(
        "data_sources.cninfo.sys.executable", str(tmp_path / "elsewhere" / "python")
    )

    ds = CninfoDataSource()

    assert ds._cli_path == str(on_path_cli)


def test_cli_missing_keeps_none(tmp_path, monkeypatch):
    monkeypatch.setattr("data_sources.cninfo.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "data_sources.cninfo.sys.executable", str(tmp_path / "python")
    )

    ds = CninfoDataSource()

    assert ds._cli_path is None


def test_cli_without_exec_bit_is_rejected(tmp_path, monkeypatch):
    cli = tmp_path / "cninfo"
    cli.write_text("#!/bin/sh\nexit 0\n")
    monkeypatch.setattr("data_sources.cninfo.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "data_sources.cninfo.sys.executable", str(tmp_path / "python")
    )

    ds = CninfoDataSource()

    assert ds._cli_path is None


def test_get_periodic_report_invokes_resolved_cli_path(tmp_path, monkeypatch):
    fake_cli = _cli_only_beside_interpreter(monkeypatch, tmp_path)
    calls = _capture_run(monkeypatch, stdout=json.dumps({"ann_id": "1"}))

    ds = CninfoDataSource()
    result = ds.get_periodic_report("600000", 2025)

    assert calls[0][0] == fake_cli
    assert calls[0][1] == "fetch-report"
    assert result["status"] == "success"


def test_get_announcements_invokes_resolved_cli_path(tmp_path, monkeypatch):
    fake_cli = _cli_only_beside_interpreter(monkeypatch, tmp_path)
    calls = _capture_run(monkeypatch, stdout=json.dumps([{"ann_id": "1"}]))

    ds = CninfoDataSource()
    result = ds.get_announcements("600000", since="2025-01-01", until="2025-06-30")

    assert calls[0][0] == fake_cli
    assert calls[0][1] == "fetch-stock"
    assert result["status"] == "success"
    assert result["total"] == 1


def test_missing_cli_short_circuits_without_subprocess(tmp_path, monkeypatch):
    empty_dir = tmp_path / "bin"
    empty_dir.mkdir()
    monkeypatch.setattr("data_sources.cninfo.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "data_sources.cninfo.sys.executable", str(empty_dir / "python")
    )

    def _no_call(*args, **kwargs):
        raise AssertionError("subprocess.run 不应在 CLI 缺失时被调用")

    monkeypatch.setattr("data_sources.cninfo.subprocess.run", _no_call)

    ds = CninfoDataSource()
    result = ds.get_periodic_report("600000", 2025)

    assert result["status"] == "error"
    assert CLI_NAME in result["error"]


def test_run_json_tolerates_cli_warning_on_stdout(tmp_path, monkeypatch):
    _cli_only_beside_interpreter(monkeypatch, tmp_path)
    calls = _capture_run(
        monkeypatch,
        stdout='warning: The `fitz` API is deprecated.\n[{"ann_id": "1"}]',
    )

    ds = CninfoDataSource()
    result = ds.get_announcements("600000", since="2025-01-01", until="2025-06-30")

    assert calls[0][0] == str(tmp_path / "cninfo")
    assert result["status"] == "success"
    assert result["total"] == 1
