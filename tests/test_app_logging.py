import json
import zipfile

from src.app_logging import export_troubleshooting_bundle


def test_troubleshooting_bundle_excludes_private_data_and_device_names(tmp_path):
    log = tmp_path / "app.jsonl"
    log.write_text('{"message":"started"}\n')
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "audio": {
                    "device_index": 1,
                    "device_name": "Santhosh microphone",
                    "candidate_device_name": "Private headset",
                }
            }
        )
    )
    output = export_troubleshooting_bundle(
        tmp_path / "support.zip", log_path=log, settings_path=settings
    )

    with zipfile.ZipFile(output) as archive:
        assert "diagnostics.json" in archive.namelist()
        redacted = archive.read("settings-redacted.json").decode()
        assert "Santhosh" not in redacted
        assert "Private headset" not in redacted
        assert (
            json.loads(archive.read("diagnostics.json"))["includes_private_profile_or_session_data"]
            is False
        )
