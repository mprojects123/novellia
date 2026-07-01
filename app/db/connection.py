"""
Postgres connection management

One connection pool per process, created once at startup and reused
across requests. Raw SQL is more transparent at this scale
"""

import os
import time
import logging
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

_pool = None


def init_pool():
    """Create the connection pool, retrying briefly while Postgres boots."""
    global _pool
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://novellia:novellia@localhost:5432/novellia",
    )

    last_err = None
    for _ in range(20):
        try:
            _pool = pool.SimpleConnectionPool(minconn=1, maxconn=10, dsn=database_url)
            logger.info("Postgres connection pool initialized")
            return
        except psycopg2.OperationalError as e:
            last_err = e
            time.sleep(1)
    raise RuntimeError(f"Could not connect to Postgres: {last_err}")


@contextmanager
def get_cursor(commit: bool = False):
    """
    Borrow a connection, yield a cursor, return the connection when done.
    Use commit=True for INSERT/UPDATE/DELETE.
    """
    conn = _pool.getconn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        _pool.putconn(conn)


def run_schema(schema_path: str):
    """Execute schema.sql to create tables if they don't exist."""
    with open(schema_path) as f:
        schema_sql = f.read()
    with get_cursor(commit=True) as cur:
        cur.execute(schema_sql)
    logger.info("Schema applied")
