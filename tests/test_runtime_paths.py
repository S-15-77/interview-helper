from pathlib import Path

from src.runtime_paths import prepare_runtime_directory


def test_source_run_keeps_current_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("INTERVIEW_HELPER_DATA_DIR", raising=False)

    assert prepare_runtime_directory() == tmp_path
    assert Path.cwd() == tmp_path


def test_packaged_runtime_uses_override_and_seeds_resources(tmp_path, monkeypatch):
    resources = tmp_path / "bundle"
    (resources / "skills").mkdir(parents=True)
    (resources / "skills" / "coach.md").write_text("local coaching")
    data = tmp_path / "application-support"
    monkeypatch.setenv("INTERVIEW_HELPER_DATA_DIR", str(data))
    monkeypatch.setattr("src.runtime_paths.sys._MEIPASS", str(resources), raising=False)

    result = prepare_runtime_directory()

    assert result == data
    assert (data / "skills" / "coach.md").read_text() == "local coaching"
