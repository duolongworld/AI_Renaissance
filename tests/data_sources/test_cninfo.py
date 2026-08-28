from types import SimpleNamespace

from data_sources.cninfo import CninfoDataSource


def test_cninfo_accepts_dependency_warning_before_json(monkeypatch):
    monkeypatch.setattr("data_sources.cninfo.shutil.which", lambda _: "/tmp/cninfo")
    monkeypatch.setattr(
        "data_sources.cninfo.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=(
                "warning: The fitz API is deprecated.\n"
                '{"ann_id":"1225507370","title":"2026年半年度报告"}\n'
            ),
            stderr="",
        ),
    )

    result = CninfoDataSource().get_periodic_report("300757", 2026, "h1")

    assert result["status"] == "success"
    assert result["report"]["ann_id"] == "1225507370"


def test_cninfo_still_rejects_non_json_stdout(monkeypatch):
    monkeypatch.setattr("data_sources.cninfo.shutil.which", lambda _: "/tmp/cninfo")
    monkeypatch.setattr(
        "data_sources.cninfo.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="warning only\nnot json\n",
            stderr="",
        ),
    )

    result = CninfoDataSource().get_periodic_report("300757", 2026, "h1")

    assert result["status"] == "error"
    assert "无法解析 cninfo 输出" in result["error"]
