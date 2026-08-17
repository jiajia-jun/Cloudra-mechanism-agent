from click.testing import CliRunner

from cloudra.cli import cli
from cloudra.infra.config import get_config


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


