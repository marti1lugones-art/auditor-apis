"""
run_scheduler.py — Corre el pipeline de chequeos automáticamente cada X minutos.

Hace la primera pasada de forma inmediata al arrancar, luego repite con el
intervalo definido en config.yaml (settings.check_interval_minutes).

Usa exactamente la misma lógica que run_check.py: llama run_all_checks()
directamente, sin duplicar código.

Uso:
    python src/run_scheduler.py
    python src/run_scheduler.py --config otro_config.yaml
    python src/run_scheduler.py --db otra_base.db

Detener: Ctrl+C — el scheduler cierra limpio.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

sys.path.insert(0, str(Path(__file__).parent))

from config import load_config
from database import DB_PATH
from run_check import run_all_checks  # reuso directo, sin duplicar lógica

LINE_W = 58


def main() -> None:
    parser = argparse.ArgumentParser(
        description="API Auditor — scheduler continuo de chequeos"
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--db", default=str(DB_PATH))
    args = parser.parse_args()

    config_path = args.config
    db_path     = Path(args.db)

    # Cargar config solo para leer el intervalo
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌  Error de configuración: {exc}", file=sys.stderr)
        sys.exit(1)

    interval = config.settings.check_interval_minutes

    print(f"\n{'═' * LINE_W}")
    print(f"  API Auditor — Scheduler")
    print(f"  Intervalo   : cada {interval:.0f} minuto(s)")
    print(f"  Config      : {config_path}")
    print(f"  Base de datos: {db_path.resolve()}")
    print(f"  Presioná Ctrl+C para detener")
    print(f"{'═' * LINE_W}")

    pass_count = 0

    def job() -> None:
        nonlocal pass_count
        pass_count += 1
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        label = "(inmediata)" if pass_count == 1 else ""
        print(f"\n[{now}] Pasada #{pass_count} {label}".rstrip())
        run_all_checks(config_path=config_path, db_path=db_path)

    scheduler = BlockingScheduler()
    scheduler.add_job(
        job,
        trigger="interval",
        minutes=interval,
        next_run_time=datetime.now(),   # primera pasada inmediata, sin esperar el intervalo
        id="check_all",
        name="Pasada completa de chequeos",
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown(wait=False)
        print(f"\n{'─' * LINE_W}")
        print(f"  Scheduler detenido. {pass_count} pasada(s) ejecutadas. ✓")
        print(f"{'─' * LINE_W}\n")


if __name__ == "__main__":
    main()
