"""Tests for CLI entrypoint."""

from __future__ import annotations

from market.cli.main import main


def test_env_command(capsys):
    assert main(["env"]) == 0
    captured = capsys.readouterr()
    assert "env:" in captured.out
    assert "db_path:" in captured.out
    assert "live_approved: False" in captured.out


def test_migrate_command(capsys):
    assert main(["migrate"]) == 0
    captured = capsys.readouterr()
    assert "Running migrations" in captured.out


def test_api_command(capsys):
    assert main(["api"]) == 0
    captured = capsys.readouterr()
    assert "Starting API server" in captured.out


def test_scheduler_command(capsys):
    assert main(["scheduler"]) == 0
    captured = capsys.readouterr()
    assert "Starting scheduler" in captured.out
