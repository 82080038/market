"""Tests for CLI entrypoint."""

from __future__ import annotations

from market.cli.main import main


def test_env_command(capsys):
    assert main(["env"]) == 0
    captured = capsys.readouterr()
    assert "env:" in captured.out
    assert "db_path:" in captured.out
    assert "live_approved: False" in captured.out


def test_migrate_command(capsys, tmp_path, monkeypatch):
    import market.cli.main
    import market.config
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test_migrate.db"))
    monkeypatch.setenv("ENV", "research")
    new_settings = market.config.Settings()
    monkeypatch.setattr(market.config, "settings", new_settings)
    monkeypatch.setattr(market.cli.main, "settings", new_settings)
    assert main(["migrate"]) == 0
    captured = capsys.readouterr()
    assert "Running migrations" in captured.out
    assert "Migrations complete" in captured.out


def test_api_command(capsys, monkeypatch):
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: None)
    assert main(["api"]) == 0
    captured = capsys.readouterr()
    assert "Starting API server" in captured.out


def test_scheduler_command(capsys):
    assert main(["scheduler"]) == 0
    captured = capsys.readouterr()
    assert "Starting scheduler" in captured.out
