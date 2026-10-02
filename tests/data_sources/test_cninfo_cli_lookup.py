import stat

from data_sources.cninfo import CninfoDataSource


def _make_fake_cli(directory) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    cli = directory / "cninfo"
    cli.write_text("#!/bin/sh\nexit 0\n")
    cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    return str(cli)


def test_cli_found_beside_interpreter_when_not_on_path(tmp_path, monkeypatch):
    fake_cli = _make_fake_cli(tmp_path)
    monkeypatch.setattr("data_sources.cninfo.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "data_sources.cninfo.sys.executable", str(tmp_path / "python")
    )

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
