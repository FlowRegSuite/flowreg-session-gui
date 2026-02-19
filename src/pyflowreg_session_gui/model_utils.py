from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

MISSING = object()


@dataclass(frozen=True)
class ModelFieldSpec:
    name: str
    annotation: Any
    default: Any = MISSING
    required: bool = False


def _is_pydantic_undefined(value: Any) -> bool:
    if value is Ellipsis:
        return True
    type_name = type(value).__name__
    return type_name in {"PydanticUndefinedType", "UndefinedType"}


def _field_annotation(field: Any) -> Any:
    for attr in ("annotation", "outer_type_", "type_"):
        if hasattr(field, attr):
            return getattr(field, attr)
    return str


def _field_default(field: Any) -> Any:
    default = getattr(field, "default", MISSING)
    if default is not MISSING and not _is_pydantic_undefined(default):
        return default
    default_factory = getattr(field, "default_factory", None)
    if callable(default_factory):
        try:
            return default_factory()
        except Exception:
            return MISSING
    return MISSING


def _field_required(field: Any) -> bool:
    if hasattr(field, "is_required"):
        try:
            return bool(field.is_required())
        except TypeError:
            pass
    if hasattr(field, "required"):
        return bool(getattr(field, "required"))
    return False


def iter_model_fields(model_cls: type[Any]) -> list[ModelFieldSpec]:
    raw_fields: dict[str, Any] | None = None
    if hasattr(model_cls, "model_fields"):
        raw_fields = getattr(model_cls, "model_fields")
    elif hasattr(model_cls, "__fields__"):
        raw_fields = getattr(model_cls, "__fields__")

    if raw_fields is None:
        raise TypeError("SessionConfig does not expose model_fields or __fields__")

    field_specs: list[ModelFieldSpec] = []
    for name, field in raw_fields.items():
        annotation = _field_annotation(field)
        required = _field_required(field)
        default = _field_default(field)
        if required:
            default = MISSING
        field_specs.append(
            ModelFieldSpec(name=name, annotation=annotation, default=default, required=required)
        )
    return field_specs


def model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return dict(model.model_dump(mode="python"))
    if hasattr(model, "dict"):
        return dict(model.dict())
    if hasattr(model, "__dict__"):
        return dict(vars(model))
    raise TypeError(f"Unsupported model type: {type(model)!r}")


def build_model(model_cls: type[Any], values: dict[str, Any]) -> Any:
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(values)
    return model_cls(**values)


def deep_copy_model(model: Any) -> Any:
    if hasattr(model, "model_copy"):
        return model.model_copy(deep=True)
    if hasattr(model, "copy"):
        try:
            return model.copy(deep=True)
        except TypeError:
            return model.copy()
    return copy.deepcopy(model)
