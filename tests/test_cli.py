"""Tests for CLI entrypoint."""

from __future__ import annotations

import pytest

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


def test_scheduler_list_command(capsys):
    assert main(["scheduler", "list"]) == 0
    captured = capsys.readouterr()
    assert "fetch_eod" in captured.out
    assert "quality_check" in captured.out
    assert "Total: 5 tasks" in captured.out


def test_scheduler_run_command(capsys):
    assert main(["scheduler", "run"]) == 0
    captured = capsys.readouterr()
    assert "Executed:" in captured.out


def test_model_list_command(capsys):
    assert main(["model", "list"]) == 0
    captured = capsys.readouterr()
    assert "No models registered" in captured.out or "Total:" in captured.out


def test_model_champion_command(capsys):
    assert main(["model", "champion"]) == 0
    captured = capsys.readouterr()
    assert "champion" in captured.out.lower()


def test_model_promote_not_found(capsys):
    assert main(["model", "promote", "--model-id", "nonexistent"]) == 1
    captured = capsys.readouterr()
    assert "not found" in captured.out.lower()


def test_model_rollback_no_champion(capsys):
    assert main(["model", "rollback"]) == 1
    captured = capsys.readouterr()
    assert "champion" in captured.out.lower()


def test_no_command_exits():
    with pytest.raises(SystemExit):
        main([])
