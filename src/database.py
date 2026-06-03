"""
database.py — Persistencia en SQLite.

Un único archivo (auditor.db) en la raíz del proyecto.
Sin ORM; sqlite3 de stdlib es suficiente para estas necesidades.
"""

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from checker import CheckResult

# Ruta por defecto: raíz del proyecto
DB_PATH = Path(__file__).parent.parent / "auditor.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS checks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint_name   TEXT    NOT NULL,
    method          TEXT    NOT NULL,
    url             TEXT    NOT NULL,
    checked_at      TEXT    NOT NULL,    -- ISO 8601 con timezone
    is_up           INTEGER NOT NULL,    -- 1 = up, 0 = down
    status_code     INTEGER,             -- NULL si no conectó
    latency_ms      REAL,               -- NULL si no conectó
    error           TEXT,               -- NULL si no hubo error
    expected_status INTEGER             -- NULL si no se especificó en config
)
"""


def init_db(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    """
    Abre (o crea) la base de datos y garantiza que la tabla existe.
    Devuelve la conexión para reutilizarla.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_TABLE)
    conn.commit()
    return conn


def save_check(conn: sqlite3.Connection, result: "CheckResult") -> None:
    """Inserta un CheckResult en la tabla checks."""
    conn.execute(
        """
        INSERT INTO checks
            (endpoint_name, method, url, checked_at,
             is_up, status_code, latency_ms, error, expected_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.endpoint_name,
            result.method,
            result.url,
            result.checked_at.isoformat(),
            int(result.is_up),
            result.status_code,
            result.latency_ms,
            result.error,
            result.expected_status,
        ),
    )
    conn.commit()


def get_latest_checks(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    """Devuelve los últimos `limit` chequeos como lista de dicts."""
    cur = conn.execute(
        """
        SELECT id, endpoint_name, method, url, checked_at,
               is_up, status_code, latency_ms, error, expected_status
        FROM checks
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
