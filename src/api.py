"""
api.py — Backend FastAPI del dashboard de auditoría de APIs.

Sirve los datos de las 4 tablas SQLite al frontend, y corre el scheduler
de chequeos en background mientras la API está activa.

Un solo proceso: API + monitoreo continuo.

Arrancar:
    uvicorn src.api:app --reload --port 8000
"""

import sqlite3
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent))

from config import Config, load_config
from database import DB_PATH
from run_check import run_all_checks

# Config en la raíz del proyecto, independiente del directorio de trabajo
CONFIG_PATH = str(Path(__file__).parent.parent / "config.yaml")


# ── Lifespan: scheduler en background ────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Arranca el BackgroundScheduler al iniciar la API y lo detiene al cerrar.
    La primera pasada es inmediata; las siguientes siguen el intervalo del config.
    """
    config = load_config(CONFIG_PATH)
    app.state.config = config          # cacheado para todas las requests
    interval = config.settings.check_interval_minutes

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_all_checks,
        trigger="interval",
        minutes=interval,
        next_run_time=datetime.now(),  # primera pasada inmediata
        kwargs={"config_path": CONFIG_PATH, "db_path": DB_PATH},
        id="check_all",
        name="Pasada completa de chequeos",
    )
    scheduler.start()
    print(f"\n[API] Scheduler iniciado — cada {interval:.0f} minuto(s)")
    print(f"[API] Primera pasada en curso...\n")

    yield

    scheduler.shutdown(wait=False)
    print("\n[API] Scheduler detenido.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="API Auditor — Dashboard Backend",
    description=(
        "Sirve datos de monitoreo al dashboard. "
        "Lee las tablas checks, schemas, schema_changes y rule_violations. "
        "El scheduler de chequeos corre en background mientras la API está activa."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # restringir a dominios específicos en producción
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Helpers de DB ─────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    """Abre una conexión read-only por request."""
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def _latest_check(conn: sqlite3.Connection, endpoint_name: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM checks WHERE endpoint_name=? ORDER BY id DESC LIMIT 1",
        (endpoint_name,),
    ).fetchone()
    return dict(row) if row else None


def _active_violations(conn: sqlite3.Connection, check_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT rule_type, descripcion, campo, formato, valor_esperado, valor_actual "
        "FROM rule_violations WHERE check_id=?",
        (check_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _active_breaking(conn: sqlite3.Connection, check_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT field_path, description, baseline_type, current_type "
        "FROM schema_changes WHERE check_id=? AND change_type='breaking'",
        (check_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _estado(check: dict | None, violations: list, breaking: list) -> str:
    """
    Estado calculado del endpoint basado en su último chequeo.

    down      → is_up=False (no conectó)
    breaking  → breaking changes activos en el último check
    violacion → violaciones de reglas activas (sin breaking changes)
    ok        → todo en orden
    sin_datos → nunca chequeado
    """
    if check is None:         return "sin_datos"
    if not check["is_up"]:    return "down"
    if breaking:              return "breaking"
    if violations:            return "violacion"
    return "ok"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", summary="Estado del servidor")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": "0.1.0"}


@app.get(
    "/api/endpoints",
    summary="Estado actual de todos los endpoints monitoreados",
)
def list_endpoints(request: Request) -> list[dict[str, Any]]:
    """
    Lista de endpoints configurados con su estado actual:
    último chequeo, violaciones activas y breaking changes activos.

    "Activo" = detectado en el último check de ese endpoint.
    """
    config: Config = request.app.state.config
    conn = _conn()
    try:
        result = []
        for ep in config.endpoints:
            latest     = _latest_check(conn, ep.name)
            violations = _active_violations(conn, latest["id"]) if latest else []
            breaking   = _active_breaking(conn,   latest["id"]) if latest else []

            result.append({
                "nombre":          ep.name,
                "method":          ep.method,
                "url":             ep.url,
                "expected_status": ep.expected_status,
                "estado":          _estado(latest, violations, breaking),
                "ultimo_chequeo": {
                    "timestamp":   latest["checked_at"],
                    "is_up":       bool(latest["is_up"]),
                    "status_code": latest["status_code"],
                    "latencia_ms": latest["latency_ms"],
                    "error":       latest["error"],
                } if latest else None,
                "violaciones_activas":     violations,
                "breaking_changes_activos": breaking,
            })
        return result
    finally:
        conn.close()


@app.get(
    "/api/endpoints/{nombre}/history",
    summary="Histórico de chequeos de un endpoint",
)
def endpoint_history(
    nombre: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000, description="Máximo de registros"),
) -> dict[str, Any]:
    """
    Histórico de chequeos para un endpoint, ordenado del más reciente al más antiguo.

    `nombre` debe coincidir exactamente con el nombre en config.yaml.
    En URLs, los espacios se encodean como %20 (FastAPI los decodea automáticamente).
    """
    config: Config = request.app.state.config
    nombres_config = {ep.name for ep in config.endpoints}

    if nombre not in nombres_config:
        raise HTTPException(
            status_code=404,
            detail=f"Endpoint '{nombre}' no existe en la configuración actual",
        )

    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id, checked_at, is_up, status_code, latency_ms, error "
            "FROM checks WHERE endpoint_name=? ORDER BY id DESC LIMIT ?",
            (nombre, limit),
        ).fetchall()

        return {
            "nombre": nombre,
            "total":  len(rows),
            "checks": [
                {
                    "id":          r["id"],
                    "timestamp":   r["checked_at"],
                    "is_up":       bool(r["is_up"]),
                    "status_code": r["status_code"],
                    "latencia_ms": r["latency_ms"],
                    "error":       r["error"],
                }
                for r in rows
            ],
        }
    finally:
        conn.close()


@app.get(
    "/api/incidents",
    summary="Violaciones de reglas y breaking changes (más recientes primero)",
)
def list_incidents(
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    """
    Lista combinada de violaciones de reglas y breaking changes de schema,
    ordenada por fecha descendente.

    tipo = "violacion_regla" | "breaking_change"
    """
    conn = _conn()
    try:
        violations = conn.execute(
            "SELECT 'violacion_regla' AS tipo, endpoint_name, detected_at, check_id, "
            "rule_type, descripcion, campo, formato, valor_esperado, valor_actual "
            "FROM rule_violations ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

        breakings = conn.execute(
            "SELECT 'breaking_change' AS tipo, endpoint_name, detected_at, check_id, "
            "null AS rule_type, description AS descripcion, field_path AS campo, "
            "null AS formato, baseline_type AS valor_esperado, current_type AS valor_actual "
            "FROM schema_changes WHERE change_type='breaking' ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

        combined = [dict(r) for r in violations] + [dict(r) for r in breakings]
        combined.sort(key=lambda r: r["detected_at"], reverse=True)

        return combined[:limit]
    finally:
        conn.close()


@app.get(
    "/api/summary",
    summary="Números globales para las tarjetas del dashboard",
)
def summary(request: Request) -> dict[str, Any]:
    """
    Totales actuales basados en el ÚLTIMO check de cada endpoint.
    "Activo" no es el total histórico: es lo que ocurrió en la última pasada.
    """
    config: Config = request.app.state.config
    conn = _conn()
    try:
        up = down = sin_datos = 0
        total_violations = 0
        total_breaking   = 0

        for ep in config.endpoints:
            latest = _latest_check(conn, ep.name)
            if latest is None:
                sin_datos += 1
                continue

            if latest["is_up"]:
                up += 1
            else:
                down += 1

            total_violations += conn.execute(
                "SELECT COUNT(*) FROM rule_violations WHERE check_id=?",
                (latest["id"],),
            ).fetchone()[0]

            total_breaking += conn.execute(
                "SELECT COUNT(*) FROM schema_changes "
                "WHERE check_id=? AND change_type='breaking'",
                (latest["id"],),
            ).fetchone()[0]

        return {
            "total_endpoints":          len(config.endpoints),
            "endpoints_up":             up,
            "endpoints_down":           down,
            "endpoints_sin_datos":      sin_datos,
            "violaciones_activas":      total_violations,
            "breaking_changes_activos": total_breaking,
        }
    finally:
        conn.close()
