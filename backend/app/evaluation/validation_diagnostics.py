"""Allowlisted validation metadata, never exception text or input values."""
from typing import get_args

from openai.types.responses import Response
from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorType

from app.schemas.application_packs import PackProviderOutput, GroqPackOutput
from app.schemas.job_fit import ProviderJobFitOutput
from app.schemas.profile_suggestions import ProviderSuggestionOutput, ProviderWireSuggestionOutput, GroqProfileOutput


def _schema_names():
    fields, models = set(), set()

    def visit(node):
        if isinstance(node, dict):
            fields.update(node.get("properties", {}))
            models.update(node.get("$defs", {}))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    for model in (Response, ProviderSuggestionOutput, ProviderWireSuggestionOutput, GroqProfileOutput, ProviderJobFitOutput, PackProviderOutput, GroqPackOutput):
        models.add(model.__name__)
        visit(BaseModel.model_json_schema.__func__(model))
    return fields, models


_FIELDS, _MODELS = _schema_names()
_ERROR_TYPES = frozenset(get_args(ErrorType))


def validation_diagnostics(error):
    # Wrappers include ProviderFailure and APIResponseValidationError. Bound
    # traversal even if an exception chain is cyclic.
    for _ in range(8):
        if isinstance(error, ValidationError):
            break
        error = getattr(error, "__cause__", None)
    else:
        return {}
    details = error.errors(include_input=False, include_context=False, include_url=False)
    entries = []
    for detail in details[:20]:
        location = detail.get("loc", ())
        safe_location = [
            part if (type(part) is int and 0 <= part <= 10000) or (
                isinstance(part, str) and len(part) <= 80 and part in (_FIELDS | _MODELS)
            ) else "<redacted>"
            for part in location[:8]
        ]
        entries.append({
            "type": detail["type"] if detail["type"] in _ERROR_TYPES else "unknown",
            "location": safe_location,
            "location_truncated": len(location) > 8,
        })
    return {"validation": {
        "model": error.title if error.title in _MODELS else "unknown",
        "errors": entries,
        "errors_truncated": len(details) > 20,
    }}
