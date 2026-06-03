"""
rules.py — Evaluación de reglas definidas en config.yaml.

Tipos de regla (Fase 3 del MVP):
  status_esperado  — el código HTTP debe ser valor
  latencia_maxima  — el tiempo de respuesta no supera ms
  campo_requerido  — un campo existe y no es null en la respuesta
  formato_campo    — los valores de un campo cumplen un formato

Para reglas de campo sobre arrays:
  Si el root de la respuesta es una lista, el path se aplica a CADA elemento.
  La violación informa cuántos elementos fallaron de cuántos totales:
      "campo 'email' ausente en 2 de 10 elementos"
  Esto da la magnitud real del problema, no solo "falló".

Resolución de paths:
  Se usan rutas con puntos para navegar objetos anidados.
      "name.common" → body["name"]["common"]
  Si el root es una lista, la ruta se aplica a cada elemento automáticamente.
"""

from dataclasses import dataclass
from typing import Any

from checker import CheckResult
from config import EndpointConfig


# ── Formatos soportados ───────────────────────────────────────────────────────
# Cada validador recibe el valor del campo y devuelve True si es válido.

VALID_FORMATS: dict[str, Any] = {
    "email": lambda v: (
        isinstance(v, str)
        and "@" in v
        and "." in v.split("@", 1)[-1]
        and len(v.split("@", 1)[-1].split(".")[-1]) >= 2
    ),
    "no_vacio": lambda v: (
        v is not None and str(v).strip() != ""
    ),
    "es_numero": lambda v: (
        isinstance(v, (int, float)) and not isinstance(v, bool)
    ),
}


# ── Resultado de una regla ────────────────────────────────────────────────────

@dataclass
class RuleViolation:
    rule_type:      str         # "status_esperado" | "latencia_maxima" | ...
    campo:          str | None  # None para status_esperado / latencia_maxima
    formato:        str | None  # solo para formato_campo
    descripcion:    str         # mensaje legible con detalle
    valor_esperado: str
    valor_actual:   str


# ── Función pública principal ─────────────────────────────────────────────────

def evaluate_rules(
    endpoint: EndpointConfig,
    result: CheckResult,
) -> list[RuleViolation]:
    """
    Evalúa todas las reglas declaradas en el endpoint contra el CheckResult.
    Nunca lanza excepción: reglas mal configuradas se ignoran silenciosamente
    (la validación ya ocurrió en config.py al cargar el YAML).
    """
    violations: list[RuleViolation] = []
    for rule in endpoint.rules:
        rtype = rule.get("type")
        if rtype == "status_esperado":
            violations.extend(_check_status(rule, result))
        elif rtype == "latencia_maxima":
            violations.extend(_check_latencia(rule, result))
        elif rtype == "campo_requerido":
            violations.extend(_check_campo_requerido(rule, result))
        elif rtype == "formato_campo":
            violations.extend(_check_formato_campo(rule, result))
    return violations


# ── Evaluadores individuales ──────────────────────────────────────────────────

def _check_status(rule: dict, result: CheckResult) -> list[RuleViolation]:
    valor  = int(rule["valor"])
    actual = result.status_code
    if actual == valor:
        return []
    return [RuleViolation(
        rule_type      = "status_esperado",
        campo          = None,
        formato        = None,
        descripcion    = f"status HTTP {actual}, se esperaba {valor}",
        valor_esperado = str(valor),
        valor_actual   = str(actual) if actual is not None else "—",
    )]


def _check_latencia(rule: dict, result: CheckResult) -> list[RuleViolation]:
    ms_max = float(rule["ms"])
    actual = result.latency_ms
    if actual is not None and actual <= ms_max:
        return []
    actual_str = f"{actual:.0f}ms" if actual is not None else "sin respuesta"
    return [RuleViolation(
        rule_type      = "latencia_maxima",
        campo          = None,
        formato        = None,
        descripcion    = f"latencia {actual_str}, máximo permitido {ms_max:.0f}ms",
        valor_esperado = f"≤{ms_max:.0f}ms",
        valor_actual   = actual_str,
    )]


def _check_campo_requerido(rule: dict, result: CheckResult) -> list[RuleViolation]:
    campo = rule["campo"]
    body  = result.response_body
    if body is None:
        return []

    entries = _collect(body, campo)  # lista de (found, value)
    if not entries:
        return []   # array vacío u otro tipo no manejado → sin violación

    total   = len(entries)
    missing = sum(1 for found, val in entries if not found or val is None)

    if missing == 0:
        return []

    if total == 1:
        desc = f"campo '{campo}' ausente en la respuesta"
        actual_str = "ausente"
    else:
        desc = f"campo '{campo}' ausente en {missing} de {total} elementos"
        actual_str = f"ausente en {missing}/{total}"

    return [RuleViolation(
        rule_type      = "campo_requerido",
        campo          = campo,
        formato        = None,
        descripcion    = desc,
        valor_esperado = f"campo '{campo}' presente",
        valor_actual   = actual_str,
    )]


def _check_formato_campo(rule: dict, result: CheckResult) -> list[RuleViolation]:
    campo     = rule["campo"]
    formato   = rule["formato"]
    body      = result.response_body
    validator = VALID_FORMATS.get(formato)

    if body is None or validator is None:
        return []

    entries = _collect(body, campo)
    if not entries:
        return []

    total = len(entries)

    # Solo evaluamos valores que existen y no son null
    evaluables = [(found, val) for found, val in entries if found and val is not None]
    if not evaluables:
        return []

    invalidos = [val for _, val in evaluables if not validator(val)]
    n_inv     = len(invalidos)

    if n_inv == 0:
        return []

    if total == 1:
        bad_val = str(invalidos[0])[:60]
        desc    = f"campo '{campo}' con formato '{formato}' inválido: {bad_val!r}"
        actual  = bad_val
    else:
        desc   = f"campo '{campo}' con formato '{formato}' inválido en {n_inv} de {total} elementos"
        actual = f"{n_inv}/{total} inválidos"

    return [RuleViolation(
        rule_type      = "formato_campo",
        campo          = campo,
        formato        = formato,
        descripcion    = desc,
        valor_esperado = f"formato {formato}",
        valor_actual   = actual,
    )]


# ── Resolución de paths ───────────────────────────────────────────────────────

def _collect(body: Any, path: str) -> list[tuple[bool, Any]]:
    """
    Recolecta tuplas (found, value) para el path dado.

    Si root es una lista → aplica el path a cada elemento dict.
    Si root es un dict   → aplica el path una vez.
    Retorna [] para otros tipos (no hay nada que evaluar).

    Esto es lo que permite reportar "X de N elementos" en arrays:
    cada elemento aporta una tupla, y contamos cuántas fallaron.
    """
    if isinstance(body, list):
        return [_get_value(item, path) for item in body if isinstance(item, dict)]
    if isinstance(body, dict):
        return [_get_value(body, path)]
    return []


def _get_value(obj: dict, path: str) -> tuple[bool, Any]:
    """
    Navega un dict usando un path separado por puntos.
    Devuelve (found=True, value) si el path existe, (False, None) si no.

    "name.common" sobre {"name": {"common": "Argentina"}} → (True, "Argentina")
    "name.missing" sobre {"name": {"common": "Argentina"}} → (False, None)
    """
    current: Any = obj
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current
