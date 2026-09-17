import uuid
from datetime import datetime
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.schemas.profile import (
    ENTRY_TITLE_MAX_LENGTH,
    ORGANIZATION_MAX_LENGTH,
    PERIOD_MAX_LENGTH,
    ENTRY_NOTES_MAX_LENGTH,
    EducationEntry,
    HEADLINE_MAX_LENGTH,
    LOCATION_MAX_LENGTH,
    LanguageEntry,
    ExperienceEntry,
    SKILL_MAX_LENGTH,
)

SuggestionField = Literal["headline", "location", "skills", "experience", "education", "languages"]


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote: str = Field(min_length=1, max_length=1000)


class _SuggestionShape(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    evidence: list[Evidence] = Field(min_length=1, max_length=10)


class HeadlineSuggestion(_SuggestionShape):
    field: Literal["headline"]
    value: str = Field(min_length=1, max_length=HEADLINE_MAX_LENGTH)


class LocationSuggestion(_SuggestionShape):
    field: Literal["location"]
    value: str = Field(min_length=1, max_length=LOCATION_MAX_LENGTH)


class SkillsSuggestion(_SuggestionShape):
    field: Literal["skills"]
    value: str = Field(min_length=1, max_length=SKILL_MAX_LENGTH)


class ExperienceSuggestion(_SuggestionShape):
    field: Literal["experience"]
    value: ExperienceEntry


class EducationSuggestion(_SuggestionShape):
    field: Literal["education"]
    value: EducationEntry


class LanguageSuggestion(_SuggestionShape):
    field: Literal["languages"]
    value: LanguageEntry


# Untagged union on purpose: pydantic emits ``anyOf`` in the provider JSON
# schema (the SDK's strict converter and compatible Responses endpoints handle
# ``anyOf``, not ``oneOf``/``discriminator``). The disjoint ``field`` literals
# make the parse deterministic while the schema now constrains each field's
# ``value`` to the shape the production validator accepts.
ProfileSuggestion = Union[
    HeadlineSuggestion,
    LocationSuggestion,
    SkillsSuggestion,
    ExperienceSuggestion,
    EducationSuggestion,
    LanguageSuggestion,
]


def _compact_wire_schema(schema):
    """Compact schema metadata with the existing local-only constraints below.

    Evidence list and quote bounds must remain on the wire; do not remove them
    to meet a budget. Local validation always rechecks returned evidence.

    Keeps the typed structure (value ``$ref``s, field enums, ``required``
    keys, ``additionalProperties``, evidence shape, max-length bounds on the
    string value fields). The wire contract is weaker than local validation:
    omitted constraints below can cause schema-compliant output to fail parsing.
    - ``title`` / ``default`` / ``description`` (informative only),
    - the per-suggestion ``id`` length/pattern keys (the production parse still
      enforces them through the ``_SuggestionShape`` Field constraints),
    - ``suggestions.maxItems`` (the token cap does not guarantee this bound;
      enforced at application parse),
    - string-value ``minLength`` bounds (local parse re-validates the returned content against those same
      Field constraints; the wire schema keeps ``maxLength`` on values and
      ``type: string`` everywhere so the provider still sees a typed contract).
    """
    def visit(node):
        if isinstance(node, dict):
            # These maps contain user field/model names, not schema keywords.
            # In particular ExperienceEntry.properties.title is a real field.
            trimmed = {key: ({name: visit(spec) for name, spec in value.items()}
                             if key in {"properties", "$defs", "definitions", "patternProperties"}
                             else visit(value)) for key, value in node.items()
                       if key not in {"title", "default", "description"}}
            id_spec = trimmed.get("properties", {}).get("id")
            if isinstance(id_spec, dict) and len(id_spec) > 1:
                trimmed["properties"]["id"] = {
                    key: value for key, value in id_spec.items()
                    if key not in {"minLength", "maxLength", "pattern"}}
            return trimmed
        if isinstance(node, list):
            return [visit(item) for item in node]
        return node

    compacted = visit(schema)
    sug = compacted.get("properties", {}).get("suggestions")
    if isinstance(sug, dict):
        sug.pop("maxItems", None)
    # String value fields retain maxLength (provider guidance for bounded
    # content); minLength is local-parse only (keeps the wire schema smaller
    # while never weakening the application contract).
    for branch in ("HeadlineSuggestion", "LocationSuggestion", "SkillsSuggestion"):
        val = (compacted.get("$defs", {}).get(branch, {})
               .get("properties", {}).get("value"))
        if isinstance(val, dict):
            val.pop("minLength", None)
    # Entry string fields follow the same rule, except ProviderExperienceEntry.job_title:
    # it stays fully typed (minLength 1) on the wire so the previously restored
    # title requirement is explicit. The other entry strings are max-bounded on
    # the wire and min-bounded at application parse, reducing the serialized request size.
    for entry, props in (("ProviderExperienceEntry", ("organization",)),
                         ("EducationEntry", ("school",)),
                         ("LanguageEntry", ("name",))):
        node = (compacted.get("$defs", {}).get(entry, {})
                .get("properties", {}))
        for prop in props:
            spec = node.get(prop)
            if isinstance(spec, dict):
                spec.pop("minLength", None)
    return compacted


class ProviderSuggestionOutput(BaseModel):
    """Validated suggestions using domain field names for storage and public APIs."""

    model_config = ConfigDict(extra="forbid")
    suggestions: list[ProfileSuggestion] = Field(max_length=50)
    partial: bool = False
    message: str | None = Field(default=None, max_length=500)


class ProviderExperienceEntry(BaseModel):
    # Unverified compatibility workaround: retained evidence does not establish
    # that the property name title caused the provider's HTTP 400.
    model_config = ConfigDict(extra="forbid")

    job_title: str = Field(min_length=1, max_length=ENTRY_TITLE_MAX_LENGTH)
    organization: str = Field(min_length=1, max_length=ORGANIZATION_MAX_LENGTH)
    period: str | None = Field(default=None, max_length=PERIOD_MAX_LENGTH)
    notes: str | None = Field(default=None, max_length=ENTRY_NOTES_MAX_LENGTH)

    def to_domain(self) -> ExperienceEntry:
        return ExperienceEntry(title=self.job_title, organization=self.organization,
                               period=self.period, notes=self.notes)


class ProviderExperienceSuggestion(_SuggestionShape):
    field: Literal["experience"]
    value: ProviderExperienceEntry


class ProviderWireSuggestionOutput(ProviderSuggestionOutput):
    suggestions: list[Union[
        HeadlineSuggestion, LocationSuggestion, SkillsSuggestion,
        ProviderExperienceSuggestion, EducationSuggestion, LanguageSuggestion,
    ]] = Field(max_length=50)

    def to_domain(self) -> ProviderSuggestionOutput:
        return ProviderSuggestionOutput(
            suggestions=[
                ExperienceSuggestion(id=item.id, field=item.field,
                                     value=item.value.to_domain(), evidence=item.evidence)
                if isinstance(item, ProviderExperienceSuggestion) else item
                for item in self.suggestions
            ],
            partial=self.partial, message=self.message,
        )

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        # The SDK loads the text-format schema via model_json_schema(), so the
        # wire payload (and the evaluation request plan, which estimates from
        # the same call) is the compact form below; parsing of the returned
        # content always goes through this class's own pydantic validation.
        return _compact_wire_schema(super().model_json_schema(*args, **kwargs))


def _groq_profile_schema(schema):
    """Shorten reference labels and share identical evidence arrays, losing no constraints."""
    from copy import deepcopy
    schema = deepcopy(schema)
    definitions = schema.get("$defs", {})
    evidence_arrays = [node["properties"]["evidence"] for node in definitions.values()
                       if "evidence" in node.get("properties", {})]
    if evidence_arrays:
        if any(value != evidence_arrays[0] for value in evidence_arrays):
            raise ValueError("Cannot share evidence arrays with different constraints")
        for node in definitions.values():
            if "evidence" in node.get("properties", {}):
                node["properties"]["evidence"] = {"$ref": "#/$defs/EvidenceList"}
        definitions["EvidenceList"] = evidence_arrays[0]
    names = {name: f"d{index}" for index, name in enumerate(definitions)}

    def visit(node):
        if isinstance(node, dict):
            result = {}
            for key, value in node.items():
                if key == "$ref" and value.startswith("#/$defs/"):
                    result[key] = "#/$defs/" + names[value.removeprefix("#/$defs/")]
                elif key == "$defs":
                    result[key] = {names[name]: visit(spec) for name, spec in value.items()}
                else:
                    result[key] = visit(value)
            return result
        if isinstance(node, list):
            return [visit(item) for item in node]
        return node
    return visit(schema)


class GroqProfileOutput(ProviderWireSuggestionOutput):
    """Groq profile wire contract: absent required keys cannot become defaults."""
    partial: bool
    message: str | None = Field(max_length=500)

    @model_validator(mode="after")
    def require_all_wire_fields(self):
        errors = []

        def visit(value, path=()):
            if isinstance(value, BaseModel):
                for name in type(value).model_fields:
                    if name not in value.model_fields_set:
                        errors.append({"type": "missing", "loc": path + (name,), "input": None})
                    else:
                        visit(getattr(value, name), path + (name,))
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    visit(item, path + (index,))
        visit(self)
        if errors:
            raise ValidationError.from_exception_data(type(self).__name__, errors)
        return self

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        return _groq_profile_schema(super().model_json_schema(*args, **kwargs))


class SuggestionSetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    resume_id: uuid.UUID
    source_hash: str
    source_reviewed_at: datetime
    profile_revision: str
    status: str
    suggestions: list[dict[str, Any]] | None
    provider: str
    model: str
    prompt_version: str
    outcome_message: str | None
    applied_at: datetime | None
    apply_result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class ApplySuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selections: list[ProfileSuggestion] = Field(min_length=1, max_length=50)
