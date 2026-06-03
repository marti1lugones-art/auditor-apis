"""
checker.py — Ejecuta un chequeo HTTP y mide latencia.

Definición de is_up:
    True  → el servidor respondió (cualquier código HTTP, incluso 4xx/5xx)
    False → no se pudo conectar (timeout, DNS fail, connection refused, etc.)

Un 404 es is_up=True porque el servidor *está* respondiendo.
El campo status_code da el detalle sobre lo que respondió.
"""

import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx


@dataclass
class CheckResult:
    endpoint_name:   str
    method:          str
    url:             str
    checked_at:      datetime
    is_up:           bool
    status_code:     int | None    # None si no hubo conexión
    latency_ms:      float | None  # None si no hubo conexión
    error:           str | None    # None si todo bien
    expected_status: int | None    # copiado de la config, None si no se especificó


def check_endpoint(
    name: str,
    method: str,
    url: str,
    timeout: float = 10.0,
    expected_status: int | None = None,
) -> CheckResult:
    """
    Realiza una request HTTP contra `url` y devuelve el resultado.

    Nunca lanza excepción — si algo falla, devuelve is_up=False con el
    mensaje de error en el campo `error`.
    """
    checked_at = datetime.now(timezone.utc)

    try:
        t0 = time.perf_counter()
        response = httpx.request(
            method,
            url,
            timeout=timeout,
            follow_redirects=True,
        )
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        return CheckResult(
            endpoint_name=name,
            method=method,
            url=url,
            checked_at=checked_at,
            is_up=True,
            status_code=response.status_code,
            latency_ms=latency_ms,
            error=None,
            expected_status=expected_status,
        )

    except httpx.TimeoutException:
        return CheckResult(
            endpoint_name=name,
            method=method,
            url=url,
            checked_at=checked_at,
            is_up=False,
            status_code=None,
            latency_ms=None,
            error=f"Timeout después de {timeout:.0f}s",
            expected_status=expected_status,
        )

    except httpx.ConnectError as exc:
        return CheckResult(
            endpoint_name=name,
            method=method,
            url=url,
            checked_at=checked_at,
            is_up=False,
            status_code=None,
            latency_ms=None,
            error=f"Error de conexión: {exc}",
            expected_status=expected_status,
        )

    except Exception as exc:
        # Red caída, DNS, SSL, protocolo inesperado, etc.
        # Registrar como caído con detalle explícito.
        return CheckResult(
            endpoint_name=name,
            method=method,
            url=url,
            checked_at=checked_at,
            is_up=False,
            status_code=None,
            latency_ms=None,
            error=f"{type(exc).__name__}: {exc}",
            expected_status=expected_status,
        )
