from click.testing import CliRunner

from cloudra.cli import cli
from cloudra.config import get_config
from cloudra.device_broker import DeviceBroker


def test_backup_cli_create_verify_and_restore(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "state.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(get_config(), "data_dir", data)
    archive = tmp_path / "cloudra.zip"
    restored = tmp_path / "restored"
    runner = CliRunner()

    assert runner.invoke(cli, ["backup", "create", str(archive)]).exit_code == 0
    assert runner.invoke(cli, ["backup", "verify", str(archive)]).exit_code == 0
    result = runner.invoke(cli, ["backup", "restore", str(archive), str(restored)])
    assert result.exit_code == 0
    assert (restored / "state.json").read_text() == "{}"


def test_devices_cli_revokes_pairing(tmp_path, monkeypatch):
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    broker = DeviceBroker(tmp_path)
    pairing = broker.start_pairing()
    credential = broker.complete_pairing(
        pairing_id=pairing["pairing_id"],
        pairing_secret=pairing["pairing_secret"],
        display_name="Phone",
        client_version="test",
        capabilities=[],
        capability_revision=1,
        workspace_revision=1,
        config_revision=1,
    )
    result = CliRunner().invoke(
        cli, ["devices", "revoke", credential["device_id"], "--yes"]
    )
    assert result.exit_code == 0
    assert broker.list_devices() == []
