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
    import uvicorn

    host = args.host
    port = args.port
    print(f"Starting API server for environment: {settings.env}")
    print(f"  Host: {host}:{port}")
    print(f"  DB: {settings.resolved_db_path}")
    uvicorn.run(
        "market.api.app:create_app",
        host=host,
        port=port,
        reload=args.reload,
        factory=True,
    )
    return 0


def cmd_scheduler(args: argparse.Namespace) -> int:
    """Start the daily data & analysis scheduler."""
    from market.scheduler import DailyScheduler
    from market.scheduler_tasks import register_default_tasks

    print(f"Starting scheduler for environment: {settings.env}")
    scheduler = DailyScheduler()
    register_default_tasks(scheduler)

    if args.scheduler_action == "list":
        for task in scheduler.tasks:
            print(
                f"  {task.task_id}: {task.name} "
                f"[{task.schedule}] enabled={task.enabled} "
                f"last={task.last_status.value}",
            )
        print(f"Total: {len(scheduler.tasks)} tasks")
        return 0

    if args.scheduler_action == "run":
        executions = scheduler.run_all_due()
        for ex in executions:
            print(
                f"  {ex.task_id}: {ex.status.value} "
                f"({ex.duration_seconds:.1f}s)",
            )
        print(f"Executed: {len(executions)} tasks")
        return 0

    print("Usage: market scheduler [list|run]")
    return 0


def cmd_export_parquet(args: argparse.Namespace) -> int:
    """Export DB to parquet archive (standalone, no scheduler needed)."""
    from market.data.export_to_parquet import export_all

    print(f"Exporting DB to parquet for environment: {settings.env}")
    print(f"  DB: {settings.resolved_db_path}")
    print(f"  Target: {settings.parquet_archive_path}/archive/tables/")
    results = export_all()
    total = sum(results.values())
    print(f"Exported: {len(results)} tables, {total:,} rows")
    return 0


def cmd_model(args: argparse.Namespace) -> int:
    """Manage model registry and champion promotion."""
    from market.mlops.registry import ModelRegistry

    registry = ModelRegistry()

    if args.model_action == "list":
        models = registry.list_models()
        if not models:
            print("No models registered.")
            return 0
        for m in models:
            aliases = ", ".join(m.aliases) if m.aliases else "—"
            print(f"  {m.model_id}: {m.model_type} v{m.version} [{aliases}]")
        print(f"Total: {len(models)} models")
        return 0

    if args.model_action == "champion":
        champ = registry.champion
        if champ is None:
            print("No champion model set.")
            return 0
        print(f"Champion: {champ.model_id} ({champ.model_type} v{champ.version})")
        print(f"  Metrics: {champ.metrics}")
        return 0

    if args.model_action == "promote":
        model = registry.get(args.model_id)
        if model is None:
            print(f"Model not found: {args.model_id}")
            return 1
        success = registry.promote(args.model_id)
        if success:
            updated = registry.get(args.model_id)
            if updated is not None:
                print(f"Promoted {args.model_id} → {updated.aliases}")
            else:
                print(f"Promoted {args.model_id}")
        else:
            print(f"Promotion failed for {args.model_id}")
            return 1
        return 0

    if args.model_action == "rollback":
        new_champ = registry.rollback()
        if new_champ is None:
            print("No champion to rollback from.")
            return 1
        print(f"Rolled back to: {new_champ.model_id}")
        return 0

    print("Usage: market model [list|champion|promote|rollback]")
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
    api_p.add_argument("--host", default="127.0.0.1", help="Bind host")
    api_p.add_argument("--port", type=int, default=8000, help="Bind port")
    api_p.add_argument("--reload", action="store_true", help="Auto-reload on changes")
    api_p.set_defaults(func=cmd_api)

    scheduler_p = sub.add_parser("scheduler", help="Start daily scheduler")
    scheduler_p.add_argument(
        "scheduler_action",
        nargs="?",
        default="list",
        choices=["list", "run"],
    )
    scheduler_p.set_defaults(func=cmd_scheduler)

    export_p = sub.add_parser("export-parquet", help="Export DB to parquet archive")
    export_p.set_defaults(func=cmd_export_parquet)

    model_p = sub.add_parser("model", help="Manage model registry")
    model_p.add_argument(
        "model_action",
        nargs="?",
        default="list",
        choices=["list", "champion", "promote", "rollback"],
    )
    model_p.add_argument("--model-id", default="", help="Model ID for promote")
    model_p.set_defaults(func=cmd_model)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
