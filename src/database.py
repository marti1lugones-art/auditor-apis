"""
database.py — Persistencia en SQLite.

Un único archivo (auditor.db) en la raíz del proyecto.
Sin ORM; sqlite3 de stdlib es suficiente para estas necesidades.

Tablas:
  checks          — registro de cada chequeo (uptime + latencia)
  schemas         — schema de referencia (baseline) por endpoint
  schema_changes  — diferencias detectadas respecto al baseline
"""

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from checker import CheckResult
    from schema_comparator import SchemaChange
    from rules import RuleViolation

DB_PATH = Path(__file__).parent.parent / "auditor.db"

# ── DDL ───────────────────────────────────────────────────────────────────────

_CREATE_CHECKS = """
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

_CREATE_SCHEMAS = """
CREATE TABLE IF NOT EXISTS schemas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint_name TEXT NOT NULL UNIQUE,  -- una sola baseline por endpoint
    schema_json   TEXT NOT NULL,         -- schema serializado a JSON
    captured_at   TEXT NOT NULL          -- ISO 8601
)
"""

_CREATE_SCHEMA_CHANGES = """
CREATE TABLE IF NOT EXISTS schema_changes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id        INTEGER NOT NULL,    -- FK → checks.id
    endpoint_name   TEXT    NOT NULL,
    detected_at     TEXT    NOT NULL,    -- ISO 8601
    change_type     TEXT    NOT NULL,    -- "non_breaking" | "breaking" | "type_uncertain"
    field_path      TEXT    NOT NULL,    -- ej: "name.common", "items[].id"
    description     TEXT    NOT NULL,
    baseline_type   TEXT,               -- NULL si el campo es nuevo
    current_type    TEXT                -- NULL si el campo desapareció
)
"""

_CREATE_RULE_VIOLATIONS = """
CREATE TABLE IF NOT EXISTS rule_violations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id        INTEGER NOT NULL,    -- FK → checks.id
    endpoint_name   TEXT    NOT NULL,
    detected_at     TEXT    NOT NULL,    -- ISO 8601
    rule_type       TEXT    NOT NULL,    -- "status_esperado" | "latencia_maxima" | ...
    campo           TEXT,               -- NULL para status_esperado / latencia_maxima
    formato         TEXT,               -- solo para formato_campo
    descripcion     TEXT    NOT NULL,
    valor_esperado  TEXT    NOT NULL,
    valor_actual    TEXT    NOT NULL
)
"""


# ── Init ──────────────────────────────────────────────────────────────────────

def init_db(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    """Abre (o crea) la base de datos y garantiza que las tablas existen."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_CHECKS)
    conn.execute(_CREATE_SCHEMAS)
    conn.execute(_CREATE_SCHEMA_CHANGES)
    conn.execute(_CREATE_RULE_VIOLATIONS)
    conn.commit()
    return conn


# ── Checks ────────────────────────────────────────────────────────────────────

def save_check(conn: sqlite3.Connection, result: "CheckResult") -> int:
    """Inserta un CheckResult en la tabla checks y devuelve el nuevo id."""
    cur = conn.execute(
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
    return cur.lastrowid


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


# ── Schemas (baseline) ────────────────────────────────────────────────────────

def get_baseline_schema(conn: sqlite3.Connection, endpoint_name: str) -> dict | list | None:
    """
    Devuelve el schema baseline de un endpoint, o None si no existe todavía.
    """
    row = conn.execute(
        "SELECT schema_json FROM schemas WHERE endpoint_name = ?",
        (endpoint_name,),
    ).fetchone()
    return json.loads(row[0]) if row else None


def save_baseline_schema(
    conn: sqlite3.Connection,
    endpoint_name: str,
    schema: dict | list,
    captured_at: str,
) -> None:
    """Guarda el schema como baseline. Solo se llama la primera vez que se ve el endpoint."""
    conn.execute(
        """
        INSERT INTO schemas (endpoint_name, schema_json, captured_at)
        VALUES (?, ?, ?)
        """,
        (endpoint_name, json.dumps(schema, ensure_ascii=False), captured_at),
    )
    conn.commit()


# ── Schema changes ────────────────────────────────────────────────────────────

def save_schema_change(
    conn: sqlite3.Connection,
    check_id: int,
    endpoint_name: str,
    detected_at: str,
    change: "SchemaChange",
) -> None:
    """Guarda una diferencia detectada entre el schema actual y el baseline."""
    conn.execute(
        """
        INSERT INTO schema_changes
            (check_id, endpoint_name, detected_at, change_type,
             field_path, description, baseline_type, current_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            check_id,
            endpoint_name,
            detected_at,
            change.change_type,
            change.field_path,
            change.description,
            change.baseline_type,
            change.current_type,
        ),
    )
    conn.commit()


# ── Rule violations ───────────────────────────────────────────────────────────

def save_rule_violation(
    conn: sqlite3.Connection,
    check_id: int,
    endpoint_name: str,
    detected_at: str,
    violation: "RuleViolation",
) -> None:
    """Guarda una violación de regla asociada a un check."""
    conn.execute(
        """
        INSERT INTO rule_violations
            (check_id, endpoint_name, detected_at, rule_type,
             campo, formato, descripcion, valor_esperado, valor_actual)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            check_id,
            endpoint_name,
            detected_at,
            violation.rule_type,
            violation.campo,
            violation.formato,
            violation.descripcion,
            violation.valor_esperado,
            violation.valor_actual,
        ),
    )
    conn.commit()
