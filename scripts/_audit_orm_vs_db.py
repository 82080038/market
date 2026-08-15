"""Audit ORM vs DB schema for all tables."""
import logging, sys
from pathlib import Path
from collections import defaultdict

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import psycopg2
from sqlalchemy import inspect as sqla_inspect

from market.db.models import Base
from market.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Get ORM columns
orm_tables: dict[str, set[str]] = {}
for cls in Base.__subclasses__():
    if hasattr(cls, "__tablename__"):
        tbl = cls.__tablename__
        cols = {c.name for c in cls.__table__.columns}
        orm_tables[tbl] = cols

# Also check subclasses of subclasses
for cls in list(Base.__subclasses__()):
    for sub in cls.__subclasses__():
        if hasattr(sub, "__tablename__"):
            tbl = sub.__tablename__
            cols = {c.name for c in sub.__table__.columns}
            orm_tables[tbl] = cols

conn = psycopg2.connect(settings.database_url)
cur = conn.cursor()

# Get DB columns for each ORM table
mismatches = []
for tbl_name, orm_cols in sorted(orm_tables.items()):
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s ORDER BY ordinal_position
    """, (tbl_name,))
    db_cols = {r[0] for r in cur.fetchall()}
    if not db_cols:
        logger.warning("Table %s not found in DB", tbl_name)
        continue

    in_orm_not_db = orm_cols - db_cols
    in_db_not_orm = db_cols - orm_cols

    if in_orm_not_db:
        mismatches.append((tbl_name, "ORM has but DB doesn't", in_orm_not_db))
        logger.error("MISMATCH %s: ORM has but DB doesn't: %s", tbl_name, in_orm_not_db)
    if in_db_not_orm:
        mismatches.append((tbl_name, "DB has but ORM doesn't", in_db_not_orm))
        logger.warning("MISMATCH %s: DB has but ORM doesn't: %s", tbl_name, in_db_not_orm)

conn.close()

if not mismatches:
    print("\n✅ All ORM models match DB schema")
else:
    print(f"\n❌ Found {len(mismatches)} mismatches:")
    for tbl, direction, cols in mismatches:
        print(f"  {tbl}: {direction}: {cols}")
