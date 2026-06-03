"""
config.py — Lee y valida config.yaml.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class EndpointConfig:
    name: str
    method: str
    url: str
    expected_status: int | None = None  # None = sin expectativa explícita


@dataclass
class Settings:
    timeout_seconds: float = 10.0


@dataclass
class Config:
    settings: Settings
    endpoints: list[EndpointConfig]


def load_config(path: str | Path = "config.yaml") -> Config:
    """
    Carga y valida config.yaml.

    Raises:
        FileNotFoundError: si el archivo no existe.
        ValueError: si faltan campos obligatorios.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo de configuración: {path.resolve()}"
        )

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not raw:
        raise ValueError("config.yaml está vacío")

    # ── Settings ──────────────────────────────────────────────────────────────
    raw_settings = raw.get("settings", {})
    settings = Settings(
        timeout_seconds=float(raw_settings.get("timeout_seconds", 10)),
    )

    # ── Endpoints ─────────────────────────────────────────────────────────────
    raw_endpoints = raw.get("endpoints", [])
    if not raw_endpoints:
        raise ValueError("config.yaml no tiene ningún endpoint definido")

    endpoints: list[EndpointConfig] = []
    for i, ep in enumerate(raw_endpoints, 1):
        if not ep.get("name"):
            raise ValueError(f"Endpoint #{i}: falta el campo 'name'")
        if not ep.get("url"):
            raise ValueError(f"Endpoint #{i} ({ep.get('name', '?')}): falta el campo 'url'")

        expected = ep.get("expected_status")
        if expected is not None:
            try:
                expected = int(expected)
            except (TypeError, ValueError):
                raise ValueError(
                    f"Endpoint '{ep['name']}': expected_status debe ser un entero, "
                    f"recibido: {expected!r}"
                )

        endpoints.append(EndpointConfig(
            name=ep["name"],
            method=ep.get("method", "GET").upper().strip(),
            url=ep["url"].strip(),
            expected_status=expected,
        ))

    return Config(settings=settings, endpoints=endpoints)
