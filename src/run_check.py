"""
run_check.py — Corre UNA pasada de chequeos sobre todos los endpoints del config.

Por cada endpoint:
  1. HTTP check (uptime + latencia)           — Fase 1
  2. Detección de cambios de schema           — Fase 2
  3. Evaluación de reglas definidas en config — Fase 3

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
    save_rule_violation,
)
from rules import RuleViolation, evaluate_rules
from schema_comparator import SchemaChange, compare_schemas
from schema_extractor import extract_schema

LINE_W = 68


# ── Formatters ────────────────────────────────────────────────────────────────

def _fmt_check(result: CheckResult) -> str:
    """Línea de uptime / latencia (Fase 1)."""
    if result.is_up:
        lat = f"{result.latency_ms:6.0f}ms"
        row = f"✓  {result.status_code:>3}  {lat}  {result.endpoint_name}"
    else:
        err = (result.error or "error")[:42]
        row = f"✗   —      —ms  {result.endpoint_name}  ← {err}"
    if result.expected_status is not None:
        row += f"  [esp: {result.expected_status}]"
    return f"  {row}"


_CHANGE_ICONS = {
    "breaking":      "💥 BREAKING",
    "non_breaking":  "✚ nuevo",
    "type_uncertain":"⚠ opcional?",
}


def _fmt_schema_lines(schema_status: str, changes: list[SchemaChange]) -> list[str]:
    """Líneas de schema (Fase 2) bajo el check de uptime."""
    prefix = " " * 6
    if schema_status == "no_json":
        return [f"{prefix}schema: sin JSON en la respuesta"]
    if schema_status == "baseline":
        return [f"{prefix}schema: baseline guardado (primera vez)"]
    if schema_status == "sin_cambios":
        return [f"{prefix}schema: sin cambios"]
    # Hay cambios
    n_b  = sum(1 for c in changes if c.change_type == "breaking")
    n_nb = sum(1 for c in changes if c.change_type == "non_breaking")
    n_u  = sum(1 for c in changes if c.change_type == "type_uncertain")
    parts = []
    if n_b:  parts.append(f"{n_b} breaking")
    if n_u:  parts.append(f"{n_u} opcional?")
    if n_nb: parts.append(f"{n_nb} nuevo(s)")
    lines = [f"{prefix}schema: {' · '.join(parts)}"]
    for c in changes:
        icon = _CHANGE_ICONS.get(c.change_type, c.change_type)
        lines.append(f"{prefix}  {icon}  {c.field_path} — {c.description}")
    return lines


def _fmt_rules_lines(violations: list[RuleViolation], n_rules: int) -> list[str]:
    """Líneas de reglas (Fase 3) bajo el schema. Vacío si no hay reglas configuradas."""
    prefix = " " * 6
    if n_rules == 0:
        return []
    if not violations:
        return [f"{prefix}reglas: ✓ {n_rules} regla(s) OK"]
    lines = []
    for i, v in enumerate(violations):
        label = "reglas:" if i == 0 else "       "
        lines.append(f"{prefix}{label} ❌ {v.rule_type} — {v.descripcion}")
    return lines


# ── Procesadores ──────────────────────────────────────────────────────────────

def _process_schema(conn, check_id: int, result: CheckResult) -> tuple[str, list[SchemaChange]]:
    """Fase 2: guarda baseline o compara. Devuelve (estado, cambios)."""
    if result.response_body is None:
        return "no_json", []
    current_schema = extract_schema(result.response_body)
    baseline = get_baseline_schema(conn, result.endpoint_name)
    if baseline is None:
        save_baseline_schema(conn, result.endpoint_name, current_schema,
                             result.checked_at.isoformat())
        return "baseline", []
    changes = compare_schemas(baseline, current_schema)
    for change in changes:
        save_schema_change(conn, check_id, result.endpoint_name,
                           result.checked_at.isoformat(), change)
    return ("cambios" if changes else "sin_cambios"), changes


def _process_rules(conn, check_id: int, result: CheckResult,
                   endpoint_config) -> list[RuleViolation]:
    """Fase 3: evalúa reglas y guarda violaciones. Devuelve lista de violaciones."""
    violations = evaluate_rules(endpoint_config, result)
    for v in violations:
        save_rule_violation(conn, check_id, result.endpoint_name,
                            result.checked_at.isoformat(), v)
    return violations


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

    # Acumuladores para el resumen
    results:          list[CheckResult]          = []
    schema_statuses:  list[tuple[str, list]]     = []
    all_violations:   list[RuleViolation]        = []
    eps_con_viols:    set[str]                   = set()

    for ep in endpoints:
        print(f"  → {ep.name[:55]}", end="\r", flush=True)

        # ── Fase 1: uptime + latencia ──────────────────────────────────────
        result = check_endpoint(
            name=ep.name, method=ep.method, url=ep.url,
            timeout=timeout, expected_status=ep.expected_status,
        )
        check_id = save_check(conn, result)
        results.append(result)

        # ── Fase 2: schema ─────────────────────────────────────────────────
        schema_status, schema_changes = _process_schema(conn, check_id, result)
        schema_statuses.append((schema_status, schema_changes))

        # ── Fase 3: reglas ─────────────────────────────────────────────────
        violations = _process_rules(conn, check_id, result, ep)
        all_violations.extend(violations)
        if violations:
            eps_con_viols.add(ep.name)

        # ── Consola ────────────────────────────────────────────────────────
        print(f"{_fmt_check(result):<{LINE_W}}")
        for line in _fmt_schema_lines(schema_status, schema_changes):
            print(line)
        for line in _fmt_rules_lines(violations, len(ep.rules)):
            print(line)

    # ── Resumen ───────────────────────────────────────────────────────────────
    n_total   = len(results)
    n_up      = sum(1 for r in results if r.is_up)
    n_down    = n_total - n_up
    latencias = [r.latency_ms for r in results if r.latency_ms is not None]
    avg_lat   = sum(latencias) / len(latencias) if latencias else None

    # Schema
    n_baseline    = sum(1 for s, _ in schema_statuses if s == "baseline")
    n_sc          = sum(1 for s, _ in schema_statuses if s == "sin_cambios")
    all_sc_changes = [c for _, cs in schema_statuses for c in cs]
    n_breaking    = sum(1 for c in all_sc_changes if c.change_type == "breaking")
    n_uncertain   = sum(1 for c in all_sc_changes if c.change_type == "type_uncertain")
    n_new_fields  = sum(1 for c in all_sc_changes if c.change_type == "non_breaking")

    # Reglas
    n_viols        = len(all_violations)
    n_eps_viols    = len(eps_con_viols)
    n_breaking_r   = sum(1 for v in all_violations if v.rule_type == "status_esperado")
    n_latencia_r   = sum(1 for v in all_violations if v.rule_type == "latencia_maxima")
    n_campo_r      = sum(1 for v in all_violations if v.rule_type == "campo_requerido")
    n_formato_r    = sum(1 for v in all_violations if v.rule_type == "formato_campo")

    print(f"\n{'─' * LINE_W}")

    # Uptime
    uptime_str = f"  {n_up}/{n_total} up"
    if n_down:    uptime_str += f"  ·  {n_down} caído(s)"
    if avg_lat:   uptime_str += f"  ·  latencia promedio: {avg_lat:.0f}ms"
    print(uptime_str)

    # Schema
    sc_parts = []
    if n_baseline:   sc_parts.append(f"{n_baseline} baseline(s) nuevo(s)")
    if n_sc:         sc_parts.append(f"{n_sc} sin cambios")
    if n_breaking:   sc_parts.append(f"💥 {n_breaking} breaking")
    if n_uncertain:  sc_parts.append(f"⚠ {n_uncertain} opcional?")
    if n_new_fields: sc_parts.append(f"✚ {n_new_fields} campo(s) nuevo(s)")
    if sc_parts:
        print(f"  schema: {' · '.join(sc_parts)}")

    # Reglas
    if n_viols == 0:
        endpoints_con_reglas = sum(1 for ep in endpoints if ep.rules)
        if endpoints_con_reglas:
            print(f"  reglas: ✓ sin violaciones ({endpoints_con_reglas} endpoint(s) evaluados)")
    else:
        detail_parts = []
        if n_breaking_r: detail_parts.append(f"{n_breaking_r} status")
        if n_latencia_r: detail_parts.append(f"{n_latencia_r} latencia")
        if n_campo_r:    detail_parts.append(f"{n_campo_r} campo")
        if n_formato_r:  detail_parts.append(f"{n_formato_r} formato")
        detail = f" ({', '.join(detail_parts)})" if detail_parts else ""
        print(f"  reglas: ❌ {n_viols} violación(es) en {n_eps_viols} endpoint(s){detail}")

    print(f"  Guardado en: {db_path.resolve()}")
    print(f"{'═' * LINE_W}\n")

    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="API Auditor — uptime, latencia, schema y reglas"
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--db", default=str(DB_PATH))
    args = parser.parse_args()
    run_all_checks(config_path=args.config, db_path=Path(args.db))


if __name__ == "__main__":
    main()
