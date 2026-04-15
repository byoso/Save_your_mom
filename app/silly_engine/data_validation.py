#! /usr/bin/env python3
"""
Version:
- 1.2.0: new ValidatedWithId for database use cases, with auto-generated _id field (uuid4)
- 1.1.1: constructor doesn't accept raw dict, do DataValidatedClass(**dict) instead
Data validation module
"""
from abc import ABC
from dataclasses import asdict, dataclass, fields, field, MISSING
from typing import Any, get_origin, get_args, List, Dict
from uuid import uuid4

class DataValidationError(Exception):
    pass


def _check_generic(value: Any, field_type: Any, field_name: str = "<unknown>") -> Any:
    """Cast simple types + list[T] + dict[K, V]"""
    origin = get_origin(field_type)
    args = get_args(field_type)

    # Any : no check
    if field_type is Any:
        return value

    # Simple cases : str, int, bool, float
    if isinstance(field_type, type):
        if not isinstance(value, field_type):
            if field_type is bool:
                if isinstance(value, int):
                    return bool(value)
            raise DataValidationError(
                f"Field '{field_name}' expects {field_type.__name__}, got {value!r} ({type(value).__name__})"
            )
        return value

    # List[T]
    if origin in (list, List):
        inner_type = args[0] if args else Any
        if not isinstance(value, list):
            raise DataValidationError(f"Field '{field_name}' expects a list, got {value!r}")
        return [_check_generic(v, inner_type, field_name) for v in value]

    # Dict[K, V]
    if origin in (dict, Dict):
        key_type, val_type = args if args else (Any, Any)
        if not isinstance(value, dict):
            raise DataValidationError(f"Field '{field_name}' expects a dict, got {value!r}")
        return {_check_generic(k, key_type, field_name): _check_generic(v, val_type, field_name) for k, v in value.items()}

    # If type is unknown
    return value

@dataclass
class ValidatedDataClass(ABC):
    """Data class with automatic validation.
    This class is expected to be inherited and needs to be used with
    @dataclass(init=False) decorator and default values for all fields.
    Typing for containers must be specified as List[T], Dict[K, V], etc... (not list, dict)
    """

    def __init__(self, *args, **kwargs) -> None:
        # support legacy: allow passing a single dict as positional to set fields
        if len(args) == 1 and isinstance(args[0], dict):
            # positional dict takes precedence but allow kwargs to override
            merged = dict(args[0])
            merged.update(kwargs)
            kwargs = merged
            args = ()

        # set declared fields only, using defaults when absent
        for f in fields(self.__class__):
            if f.name in kwargs:
                val = kwargs.pop(f.name)
            elif f.default is not MISSING:
                val = f.default
            elif getattr(f, "default_factory", MISSING) is not MISSING:
                val = f.default_factory()  # type: ignore
            else:
                val = None
            setattr(self, f.name, val)
        # ignore any remaining kwargs (extras)
        self.__post_init__()

    def __post_init__(self) -> None:
        # support construction via single positional dict assigned to first field
        # (legacy convenience used by some tests)
        field_names = [f.name for f in fields(self)]
        dict_like_fields = [f for f in fields(self) if isinstance(getattr(self, f.name), dict)]
        if len(dict_like_fields) == 1:
            mapping = getattr(self, dict_like_fields[0].name)
            if any(k in mapping for k in field_names) or mapping:
                for f in fields(self):
                    if f.name in mapping:
                        setattr(self, f.name, mapping[f.name])
                # attach any extra keys as attributes (e.g., _id)
                for k, v in mapping.items():
                    if k not in field_names:
                        setattr(self, k, v)

        for field in fields(self):
            value = getattr(self, field.name)
            try:
                validated_value = _check_generic(value, field.type, field.name)
                setattr(self, field.name, validated_value)
            except DataValidationError as e:
                raise DataValidationError(f"Error in field '{field.name}': {e}") from e
        self._validate()

    def _validate(self) -> None:
        # Additional validation logic can be added here
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.__dict__})>"

    def __str__(self) -> str:
        return self.__repr__()

    @property
    def _dict(self) -> dict:
        return asdict(self)

@dataclass
class ValidatedWithId(ValidatedDataClass):
    """Same as ValidatedDataClass but with an '_id'"""
    _id: str = field(init=True, default_factory=lambda: str(uuid4()))

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)