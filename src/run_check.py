"""
run_check.py — Corre UNA pasada de chequeos sobre todos los endpoints del config.

Por cada endpoint:
  1. HTTP check (uptime + latencia) — Fase 1
  2. Si respondió con JSON: detectar cambios de schema — Fase 2
     · Primera vez: guardar baseline
     · Siguientes:  comparar contra baseline y guardar cambios

Uso:
    python src/run_check.py
    python src/run_check.py --config otro_config.yaml
    python src/run_check.py --db otra_base.db
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from checker import CheckResult, check_endpoint
from config import load_config
from database import (
    DB_PATH, init_db, save_check,
    get_baseline_schema, save_baseline_schema, save_schema_change,
)
from schema_comparator import SchemaChange, compare_schemas
from schema_extractor import extract_schema

LINE_W = 68


# ── Formatters ────────────────────────────────────────────────────────────────

def _fmt_check(result: CheckResult) -> str:
    """Línea de uptime (Fase 1)."""
    if result.is_up:
        lat  = f"{result.latency_ms:6.0f}ms"
        row  = f"✓  {result.status_code:>3}  {lat}  {result.endpoint_name}"
    else:
        err  = (result.error or "error")[:42]
        row  = f"✗   —      —ms  {result.endpoint_name}  ← {err}"
    if result.expected_status is not None:
        row += f"  [esp: {result.expected_status}]"
    return f"  {row}"


_CHANGE_ICONS = {
    "breaking":      "💥 BREAKING",
    "non_breaking":  "✚ nuevo",
    "type_uncertain":"⚠ opcional?",
}


def _fmt_schema_lines(schema_status: str, changes: list[SchemaChange]) -> list[str]:
    """
    Líneas de schema para mostrar debajo del check de uptime.
    schema_status: "baseline" | "no_json" | "sin_cambios" | "cambios"
    """
    prefix = " " * 6  # alineado debajo del nombre del endpoint

    if schema_status == "no_json":
        return [f"{prefix}schema: sin JSON en la respuesta"]
    if schema_status == "baseline":
        return [f"{prefix}schema: baseline guardado (primera vez)"]
    if schema_status == "sin_cambios":
        return [f"{prefix}schema: sin cambios"]

    # Hay cambios
    lines = []
    n_b  = sum(1 for c in changes if c.change_type == "breaking")
    n_nb = sum(1 for c in changes if c.change_type == "non_breaking")
    n_u  = sum(1 for c in changes if c.change_type == "type_uncertain")

    parts = []
    if n_b:   parts.append(f"{n_b} breaking")
    if n_u:   parts.append(f"{n_u} opcional?")
    if n_nb:  parts.append(f"{n_nb} nuevo(s)")
    lines.append(f"{prefix}schema: {' · '.join(parts)}")

    for c in changes:
        icon = _CHANGE_ICONS.get(c.change_type, c.change_type)
        lines.append(f"{prefix}  {icon}  {c.field_path} — {c.description}")

    return lines


# ── Lógica de schema ──────────────────────────────────────────────────────────

def _process_schema(
    conn,
    check_id: int,
    result: CheckResult,
) -> tuple[str, list[SchemaChange]]:
    """
    Procesa el schema de una respuesta JSON:
      - Si es la primera vez: guarda baseline y devuelve ("baseline", [])
      - Si ya hay baseline: compara y guarda cambios, devuelve ("cambios" | "sin_cambios", [...])
      - Si no hay JSON: devuelve ("no_json", [])
    """
    if result.response_body is None:
        return "no_json", []

    current_schema = extract_schema(result.response_body)
    baseline = get_baseline_schema(conn, result.endpoint_name)

    if baseline is None:
        # Primera vez: guardar como baseline
        save_baseline_schema(
            conn,
            result.endpoint_name,
            current_schema,
            result.checked_at.isoformat(),
        )
        return "baseline", []

    # Comparar contra el baseline existente
    changes = compare_schemas(baseline, current_schema)

    for change in changes:
        save_schema_change(
            conn,
            check_id,
            result.endpoint_name,
            result.checked_at.isoformat(),
            change,
        )

    return ("cambios" if changes else "sin_cambios"), changes


# ── Main ──────────────────────────────────────────────────────────────────────

def run_all_checks(config_path: str = "config.yaml", db_path: Path = DB_PATH) -> None:
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌  Error de configuración: {exc}", file=sys.stderr)
        sys.exit(1)

    conn      = init_db(db_path)
    endpoints = config.endpoints
    timeout   = config.settings.timeout_seconds
    now_str   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print(f"\n{'═' * LINE_W}")
    print(f"  API Auditor — {now_str}")
    print(f"  {len(endpoints)} endpoint(s) · timeout: {timeout:.0f}s")
    print(f"{'─' * LINE_W}\n")

    results:        list[CheckResult]       = []
    schema_statuses: list[tuple[str, list]] = []

    for ep in endpoints:
        print(f"  → {ep.name[:55]}", end="\r", flush=True)

        # ── Fase 1: uptime + latencia ──────────────────────────────────────
        result = check_endpoint(
            name=ep.name, method=ep.method, url=ep.url,
            timeout=timeout, expected_status=ep.expected_status,
        )
        check_id = save_check(conn, result)
        results.append(result)

        # ── Fase 2: detección de schema ────────────────────────────────────
        schema_status, changes = _process_schema(conn, check_id, result)
        schema_statuses.append((schema_status, changes))

        # ── Consola ────────────────────────────────────────────────────────
        print(f"{_fmt_check(result):<{LINE_W}}")
        for line in _fmt_schema_lines(schema_status, changes):
            print(line)

    # ── Resumen ───────────────────────────────────────────────────────────────
    n_total  = len(results)
    n_up     = sum(1 for r in results if r.is_up)
    n_down   = n_total - n_up
    latencias = [r.latency_ms for r in results if r.latency_ms is not None]
    avg_lat  = sum(latencias) / len(latencias) if latencias else None

    # Conteos de schema
    n_baseline   = sum(1 for s, _ in schema_statuses if s == "baseline")
    n_sin_cambios = sum(1 for s, _ in schema_statuses if s == "sin_cambios")
    all_changes  = [c for _, cs in schema_statuses for c in cs]
    n_breaking   = sum(1 for c in all_changes if c.change_type == "breaking")
    n_uncertain  = sum(1 for c in all_changes if c.change_type == "type_uncertain")
    n_new_fields = sum(1 for c in all_changes if c.change_type == "non_breaking")

    print(f"\n{'─' * LINE_W}")

    uptime_str = f"  {n_up}/{n_total} up"
    if n_down:      uptime_str += f"  ·  {n_down} caído(s)"
    if avg_lat:     uptime_str += f"  ·  latencia promedio: {avg_lat:.0f}ms"
    print(uptime_str)

    schema_parts = []
    if n_baseline:    schema_parts.append(f"{n_baseline} baseline(s) nuevo(s)")
    if n_sin_cambios: schema_parts.append(f"{n_sin_cambios} sin cambios")
    if n_breaking:    schema_parts.append(f"💥 {n_breaking} breaking change(s)")
    if n_uncertain:   schema_parts.append(f"⚠ {n_uncertain} opcional?")
    if n_new_fields:  schema_parts.append(f"✚ {n_new_fields} campo(s) nuevo(s)")
    if schema_parts:
        print(f"  schema: {' · '.join(schema_parts)}")

    print(f"  Guardado en: {db_path.resolve()}")
    print(f"{'═' * LINE_W}\n")

    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="API Auditor — pasada de chequeos de uptime, latencia y schema"
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--db", default=str(DB_PATH))
    args = parser.parse_args()
    run_all_checks(config_path=args.config, db_path=Path(args.db))


if __name__ == "__main__":
    main()
