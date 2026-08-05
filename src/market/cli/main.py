"""CLI entrypoint for the Market application."""

from __future__ import annotations

import argparse
import sys

from market.config import settings


def cmd_env(args: argparse.Namespace) -> int:
    """Print active environment configuration (without secrets)."""
    print(f"env: {settings.env}")
    print(f"db_path: {settings.resolved_db_path}")
    print(f"reporting_currency: {settings.reporting_currency}")
    print(f"device: {settings.device}")
    print(f"broker_adapter: {settings.broker_adapter}")
    print(f"live_approved: {settings.live_approved}")
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    """Run database migrations for the active environment."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    print(f"Running migrations for environment: {settings.env}")
    print(f"Database: {settings.resolved_db_path}")

    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option(
        "sqlalchemy.url",
        f"sqlite:///{settings.resolved_db_path}",
    )
    command.upgrade(alembic_cfg, "head")
    print("Migrations complete.")
    return 0


def cmd_api(args: argparse.Namespace) -> int:
    """Start the FastAPI development server."""
    print(f"Starting API server for environment: {settings.env}")
    # Uvicorn integration will be wired in Fase 6.
    return 0


def cmd_scheduler(args: argparse.Namespace) -> int:
    """Start the daily data & analysis scheduler."""
    print(f"Starting scheduler for environment: {settings.env}")
    # Scheduler integration will be wired in Fase 1.
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="market",
        description="Market: single-user capital market decision-support application.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    env_p = sub.add_parser("env", help="Show active environment config")
    env_p.set_defaults(func=cmd_env)

    migrate_p = sub.add_parser("migrate", help="Run Alembic migrations")
    migrate_p.set_defaults(func=cmd_migrate)

    api_p = sub.add_parser("api", help="Start FastAPI server")
    api_p.set_defaults(func=cmd_api)

    scheduler_p = sub.add_parser("scheduler", help="Start daily scheduler")
    scheduler_p.set_defaults(func=cmd_scheduler)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
