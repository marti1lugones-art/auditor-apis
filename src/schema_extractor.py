"""
schema_extractor.py — Extrae el schema de una respuesta JSON.

El schema captura la estructura de los datos: qué campos existen y de qué
tipo son. Se serializa a JSON para guardarlo en SQLite como baseline.

Tipos primitivos : "string" | "number" | "boolean" | "null"
Tipos estructurados: {"type": "object", "fields": {...}}
                     {"type": "array",  "items":  <schema>}
Especiales       : "mixed"   — mismo campo tiene tipos distintos según el elemento
                   "unknown" — array vacío o profundidad máxima alcanzada

── Heurística para arrays ────────────────────────────────────────────────────
Se samplea los primeros ARRAY_SAMPLE_SIZE elementos y se combinan sus schemas:
un campo presente en CUALQUIERA de los elementos cuenta como parte del schema.

Limitación conocida: campos que solo aparecen a partir del elemento N+1
(con N > ARRAY_SAMPLE_SIZE) no quedan en el baseline. Para la mayoría de APIs
REST bien diseñadas (campos consistentes) esto es suficiente. Si la API tiene
estructuras muy variables por elemento, aumentar ARRAY_SAMPLE_SIZE.

── Tratamiento de null ───────────────────────────────────────────────────────
Al combinar schemas de varios elementos, si un campo es null en un elemento
pero tiene un tipo concreto en otro, se usa el tipo concreto. Esto evita que
campos opcionales queden marcados como "null" solo por aparecer vacíos en el
primer elemento.
"""

from typing import Any

ARRAY_SAMPLE_SIZE = 3   # cuántos elementos samplear en arrays
MAX_DEPTH         = 6   # profundidad máxima de recursión (evita bucles en estructuras circulares)


# ── Función pública principal ─────────────────────────────────────────────────

def extract_schema(data: Any, depth: int = 0) -> Any:
    """
    Extrae el schema recursivo de un valor JSON.
    Devuelve un string para primitivos o un dict para estructuras.
    """
    # Primitivos — bool ANTES de int/float porque bool es subclase de int en Python
    if data is None:                    return "null"
    if isinstance(data, bool):          return "boolean"
    if isinstance(data, (int, float)):  return "number"
    if isinstance(data, str):           return "string"

    if depth >= MAX_DEPTH:
        return "unknown"

    if isinstance(data, list):
        if not data:
            return {"type": "array", "items": "unknown"}

        # Samplear los primeros N elementos y combinar sus schemas
        sample = data[:ARRAY_SAMPLE_SIZE]
        schemas = [extract_schema(item, depth + 1) for item in sample]
        merged = schemas[0]
        for s in schemas[1:]:
            merged = _merge(merged, s)
        return {"type": "array", "items": merged}

    if isinstance(data, dict):
        return {
            "type": "object",
            "fields": {
                key: extract_schema(val, depth + 1)
                for key, val in data.items()
            },
        }

    return "unknown"


def get_schema_type(schema: Any) -> str:
    """
    Devuelve el nombre del tipo de un schema como string.
    Útil para comparar sin necesidad de isinstance checks externos.
    """
    if isinstance(schema, str):
        return schema
    if isinstance(schema, dict):
        return schema.get("type", "unknown")
    return "unknown"


# ── Merge interno ─────────────────────────────────────────────────────────────

def _merge(a: Any, b: Any) -> Any:
    """
    Combina dos schemas del mismo campo provenientes de distintos elementos
    de un array.

    Reglas:
    - Ambos object  → unir campos; los presentes en cualquiera cuentan
    - Ambos array   → fusionar schema de ítems recursivamente
    - Tipos iguales → devolver tal cual
    - null + concreto → usar el concreto (campo opcional, a veces llega null)
    - Dos concretos distintos → "mixed" (datos inconsistentes en el array)
    """
    a_type = get_schema_type(a)
    b_type = get_schema_type(b)

    # ── Ambos objetos → unir campos ───────────────────────────────────────────
    if a_type == "object" and b_type == "object":
        a_fields = a.get("fields", {}) if isinstance(a, dict) else {}
        b_fields = b.get("fields", {}) if isinstance(b, dict) else {}
        all_keys = set(a_fields) | set(b_fields)
        merged_fields: dict[str, Any] = {}
        for key in all_keys:
            if key in a_fields and key in b_fields:
                merged_fields[key] = _merge(a_fields[key], b_fields[key])
            elif key in a_fields:
                merged_fields[key] = a_fields[key]
            else:
                merged_fields[key] = b_fields[key]
        return {"type": "object", "fields": merged_fields}

    # ── Ambos arrays → fusionar ítems ─────────────────────────────────────────
    if a_type == "array" and b_type == "array":
        a_items = a.get("items", "unknown") if isinstance(a, dict) else "unknown"
        b_items = b.get("items", "unknown") if isinstance(b, dict) else "unknown"
        return {"type": "array", "items": _merge(a_items, b_items)}

    # ── Mismo tipo primitivo ──────────────────────────────────────────────────
    if a == b:
        return a

    # ── null + concreto → usar el concreto (campo opcional) ───────────────────
    if a == "null":
        return b
    if b == "null":
        return a

    # ── Dos tipos concretos distintos → inconsistencia en los datos ───────────
    return "mixed"
