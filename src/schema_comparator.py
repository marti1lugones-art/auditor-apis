"""
schema_comparator.py — Compara dos schemas y clasifica las diferencias.

Tipos de cambio (change_type):
  "non_breaking"   — campo nuevo en current que no estaba en baseline.
                     Quien ya consumía la API no se rompe.

  "breaking"       — campo desapareció, o tipo cambió entre dos tipos concretos
                     distintos (ej: string → number). Esto rompe a los consumidores.

  "type_uncertain" — tipo cambió entre null y un concreto, o viceversa
                     (ej: null → string, o string → null). Suele indicar un campo
                     opcional que a veces trae dato y a veces no. No se clasifica
                     como breaking automáticamente; requiere revisión manual.

La comparación es recursiva: entra en objetos anidados y en el schema de
ítems de arrays. El path usa notación de puntos para objetos ("address.city")
y corchetes para items de array ("items[].id").
"""

from dataclasses import dataclass
from typing import Any

from schema_extractor import get_schema_type


@dataclass
class SchemaChange:
    change_type:   str         # "non_breaking" | "breaking" | "type_uncertain"
    field_path:    str         # ej: "name.common", "items[].population"
    description:   str         # mensaje legible
    baseline_type: str | None  # None si el campo es nuevo (non_breaking)
    current_type:  str | None  # None si el campo desapareció (breaking)


# ── Función pública principal ─────────────────────────────────────────────────

def compare_schemas(
    baseline: Any,
    current:  Any,
    path:     str = "",
) -> list[SchemaChange]:
    """
    Compara dos schemas y devuelve la lista de diferencias clasificadas.
    Recursiva: entra en objetos anidados y en ítems de arrays.
    """
    changes: list[SchemaChange] = []

    b_type = get_schema_type(baseline)
    c_type = get_schema_type(current)

    # ── El tipo raíz de este nivel cambió ─────────────────────────────────────
    if b_type != c_type:
        changes.append(_make_type_change(path or "(raíz)", baseline, current))
        # No tiene sentido recursear si la estructura cambió completamente
        return changes

    # ── Ambos son objetos: comparar campo a campo ─────────────────────────────
    if b_type == "object":
        b_fields = baseline.get("fields", {}) if isinstance(baseline, dict) else {}
        c_fields = current.get("fields",  {}) if isinstance(current,  dict) else {}

        # Campos en baseline: detectar desapariciones o cambios de tipo
        for field, b_schema in b_fields.items():
            field_path = f"{path}.{field}" if path else field
            if field not in c_fields:
                changes.append(SchemaChange(
                    change_type   = "breaking",
                    field_path    = field_path,
                    description   = f"Campo '{field_path}' desapareció de la respuesta",
                    baseline_type = get_schema_type(b_schema),
                    current_type  = None,
                ))
            else:
                # Recursión: puede haber cambios dentro del campo
                changes.extend(compare_schemas(b_schema, c_fields[field], field_path))

        # Campos nuevos en current
        for field, c_schema in c_fields.items():
            if field not in b_fields:
                field_path = f"{path}.{field}" if path else field
                changes.append(SchemaChange(
                    change_type   = "non_breaking",
                    field_path    = field_path,
                    description   = f"Campo nuevo '{field_path}' en la respuesta",
                    baseline_type = None,
                    current_type  = get_schema_type(c_schema),
                ))

    # ── Ambos son arrays: comparar schema de ítems ────────────────────────────
    elif b_type == "array":
        b_items = baseline.get("items", "unknown") if isinstance(baseline, dict) else "unknown"
        c_items = current.get("items",  "unknown") if isinstance(current,  dict) else "unknown"
        array_path = f"{path}[]" if path else "[]"
        changes.extend(compare_schemas(b_items, c_items, array_path))

    # Primitivos iguales → sin cambio (los distintos se capturan al inicio)

    return changes


# ── Helper interno ────────────────────────────────────────────────────────────

def _make_type_change(path: str, baseline: Any, current: Any) -> SchemaChange:
    """
    Clasifica un cambio de tipo entre baseline y current.

    null ↔ concreto → "type_uncertain" (probable campo opcional)
    concreto A → concreto B → "breaking"
    """
    b_type = get_schema_type(baseline)
    c_type = get_schema_type(current)

    if b_type == "null" or c_type == "null":
        concreto = c_type if b_type == "null" else b_type
        return SchemaChange(
            change_type   = "type_uncertain",
            field_path    = path,
            description   = (
                f"'{path}' cambió entre null y {concreto} — "
                f"posible campo opcional"
            ),
            baseline_type = b_type,
            current_type  = c_type,
        )

    return SchemaChange(
        change_type   = "breaking",
        field_path    = path,
        description   = f"'{path}' cambió de tipo: {b_type} → {c_type}",
        baseline_type = b_type,
        current_type  = c_type,
    )
