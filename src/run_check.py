"""
run_check.py — Corre UNA pasada de chequeos sobre todos los endpoints del config.

Uso:
    python src/run_check.py
    python src/run_check.py --config otro_config.yaml
    python src/run_check.py --db otra_base.db
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Permite correr como `python src/run_check.py` desde la raíz del proyecto
sys.path.insert(0, str(Path(__file__).parent))

from checker import CheckResult, check_endpoint
from config import load_config
from database import DB_PATH, init_db, save_check

LINE_W = 65


def _format_row(result: CheckResult) -> str:
    """Formatea una línea de resultado para la consola."""
    name = result.endpoint_name

    if result.is_up:
        lat   = f"{result.latency_ms:6.0f}ms"
        code  = str(result.status_code)
        icon  = "✓"
        right = f"{icon}  {code:>3}  {lat}  {name}"
    else:
        icon  = "✗"
        err   = (result.error or "error desconocido")[:45]
        right = f"{icon}   —      —ms  {name}  ← {err}"

    # Mostrar expected_status si está definido
    if result.expected_status is not None:
        right += f"  [esp: {result.expected_status}]"

    return f"  {right}"


def run_all_checks(config_path: str = "config.yaml", db_path: Path = DB_PATH) -> None:
    # ── 1. Cargar config ──────────────────────────────────────────────────────
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌  Error de configuración: {exc}", file=sys.stderr)
        sys.exit(1)

    # ── 2. Inicializar DB ─────────────────────────────────────────────────────
    conn = init_db(db_path)

    endpoints = config.endpoints
    timeout   = config.settings.timeout_seconds
    now_str   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print(f"\n{'═' * LINE_W}")
    print(f"  API Auditor — {now_str}")
    print(f"  {len(endpoints)} endpoint(s) · timeout: {timeout:.0f}s")
    print(f"{'─' * LINE_W}\n")

    # ── 3. Chequear cada endpoint ─────────────────────────────────────────────
    results: list[CheckResult] = []

    for ep in endpoints:
        # Mostrar que estamos chequeando (sin newline, se sobreescribe)
        label = ep.name[:50]
        print(f"  → {label}", end="\r", flush=True)

        result = check_endpoint(
            name=ep.name,
            method=ep.method,
            url=ep.url,
            timeout=timeout,
            expected_status=ep.expected_status,
        )

        save_check(conn, result)
        results.append(result)

        # Sobreescribir la línea con el resultado final
        print(f"{_format_row(result):<{LINE_W}}")

    # ── 4. Resumen ────────────────────────────────────────────────────────────
    n_total = len(results)
    n_up    = sum(1 for r in results if r.is_up)
    n_down  = n_total - n_up

    latencias = [r.latency_ms for r in results if r.latency_ms is not None]
    avg_lat   = sum(latencias) / len(latencias) if latencias else None

    # Contar cuántos tienen expected_status definido (para info)
    n_con_esp = sum(1 for r in results if r.expected_status is not None)

    print(f"\n{'─' * LINE_W}")

    status_str = f"  {n_up}/{n_total} up"
    if n_down:
        status_str += f"  ·  {n_down} caído(s)"
    if avg_lat is not None:
        status_str += f"  ·  latencia promedio: {avg_lat:.0f}ms"
    print(status_str)

    if n_con_esp:
        print(f"  {n_con_esp} endpoint(s) con expected_status definido")

    print(f"  Guardado en: {db_path.resolve()}")
    print(f"{'═' * LINE_W}\n")

    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="API Auditor — pasada manual de chequeos de uptime y latencia"
    )
    parser.add_argument(
        "--config", default="config.yaml",
        help="Ruta al archivo de configuración YAML (default: config.yaml)",
    )
    parser.add_argument(
        "--db", default=str(DB_PATH),
        help=f"Ruta a la base de datos SQLite (default: {DB_PATH})",
    )
    args = parser.parse_args()

    run_all_checks(
        config_path=args.config,
        db_path=Path(args.db),
    )


if __name__ == "__main__":
    main()
