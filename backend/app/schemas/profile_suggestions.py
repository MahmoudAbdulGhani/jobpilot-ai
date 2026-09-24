import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
    computed_field,
)

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
    MAX_SKILLS,
    REMOTE_PREFERENCES,
    ROLE_MAX_LENGTH,
    SalaryPreference,
    SKILL_GROUP_MAX_LENGTH,
    SKILL_MAX_LENGTH,
    WORK_AUTHORIZATIONS,
)
from app.schemas.profile import CandidateProfileResponse, CandidateProfileUpdate

SuggestionField = Literal[
    "headline", "location", "target_roles", "skills", "experience", "education",
    "languages", "remote_preference", "work_authorization", "salary_preference",
]
ALL_SUGGESTION_FIELDS = frozenset(SuggestionField.__args__)


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


class TargetRoleSuggestion(_SuggestionShape):
    field: Literal["target_roles"]
    value: str = Field(min_length=1, max_length=ROLE_MAX_LENGTH)


class SkillsSuggestion(_SuggestionShape):
    field: Literal["skills"]
    value: list[Annotated[str, StringConstraints(min_length=1, max_length=SKILL_MAX_LENGTH)]] = Field(max_length=MAX_SKILLS)


class GroqSkillsSuggestion(_SuggestionShape):
    """Groq's wire skills contract stays an individual bounded string so the
    shared OpenAI skills fix never changes Groq's serialized schema or request
    budget; the domain conversion wraps it into the list the service applies."""

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


class RemotePreferenceSuggestion(_SuggestionShape):
    field: Literal["remote_preference"]
    value: REMOTE_PREFERENCES


class WorkAuthorizationSuggestion(_SuggestionShape):
    field: Literal["work_authorization"]
    value: WORK_AUTHORIZATIONS


class SalaryPreferenceSuggestion(_SuggestionShape):
    field: Literal["salary_preference"]
    value: SalaryPreference


# Untagged union on purpose: pydantic emits ``anyOf`` in the provider JSON
# schema (the SDK's strict converter and compatible Responses endpoints handle
# ``anyOf``, not ``oneOf``/``discriminator``). The disjoint ``field`` literals
# make the parse deterministic while the schema now constrains each field's
# ``value`` to the shape the production validator accepts.
ProfileSuggestion = Union[
    HeadlineSuggestion,
    LocationSuggestion,
    TargetRoleSuggestion,
    SkillsSuggestion,
    ExperienceSuggestion,
    EducationSuggestion,
    LanguageSuggestion,
    RemotePreferenceSuggestion,
    WorkAuthorizationSuggestion,
    SalaryPreferenceSuggestion,
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
    for branch in ("HeadlineSuggestion", "LocationSuggestion", "TargetRoleSuggestion", "SkillsSuggestion",
                   "GroqSkillsSuggestion"):
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
    not_found: list[SuggestionField] = Field(default_factory=list, max_length=len(ALL_SUGGESTION_FIELDS))
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


_SKILL_SEPARATORS = re.compile(r"[,;•·|]+")


def _normalize_skills(entries: list[str]) -> list[str]:
    """Deterministically normalize CV skills into the profile representation.

    Profile skills are an ordered ``list[str]`` with each entry bounded at
    ``SKILL_MAX_LENGTH`` and at most ``MAX_SKILLS`` entries. The provider may
    emit an array of individual skills or grouped strings; comma-,
    semicolon-, or bullet-separated groups split into individual entries.
    Pieces still over the bound split at the last whitespace within it so no
    characters are lost. Entries are deduplicated case-insensitively (first
    occurrence wins) and capped at ``MAX_SKILLS``, matching
    ``CandidateProfileUpdate``.
    """
    pieces: list[str] = []
    for entry in entries:
        for chunk in _SKILL_SEPARATORS.split(entry):
            chunk = chunk.strip()
            if chunk:
                pieces.append(chunk)
    bounded: list[str] = []
    for piece in pieces:
        while len(piece) > SKILL_MAX_LENGTH:
            cut = piece.rfind(" ", 0, SKILL_MAX_LENGTH)
            if cut > 0:
                bounded.append(piece[:cut])
                piece = piece[cut:].strip()
            else:
                bounded.append(piece[:SKILL_MAX_LENGTH])
                piece = piece[SKILL_MAX_LENGTH:]
        if piece:
            bounded.append(piece)
    seen: set[str] = set()
    result: list[str] = []
    for skill in bounded:
        if len(result) >= MAX_SKILLS:
            break
        key = skill.casefold()
        if key not in seen:
            seen.add(key)
            result.append(skill)
    return result


_WIRE_TEXT_FIELDS = frozenset({"headline", "location", "target_roles"})
_WIRE_BUCKET_FOR_FIELD = {
    "headline": "text", "location": "text", "target_roles": "text", "skills": "skills",
    "experience": "experience", "education": "education", "languages": "language",
    "remote_preference": "remote_preference", "work_authorization": "work_authorization",
    "salary_preference": "salary",
}


class ProviderWireValue(BaseModel):
    """Deterministic single-bucket wire value for one suggestion field.

    OpenAI strict structured outputs forbid ``anyOf``/``oneOf`` unions except
    for nullability, so every bucket is a nullable, strictly-required field.
    Exactly one bucket must be filled and must match the suggestion's ``field``
    (enforced by ``ProviderWireSuggestion``); each bucket retains the exact
    typed shape the application contract requires, and the domain conversion
    below revalidates the same bounds locally.
    """

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=LOCATION_MAX_LENGTH)
    experience: ProviderExperienceEntry | None = None
    education: EducationEntry | None = None
    language: LanguageEntry | None = None
    remote_preference: REMOTE_PREFERENCES | None = None
    work_authorization: WORK_AUTHORIZATIONS | None = None
    salary: SalaryPreference | None = None
    skills: list[Annotated[str, StringConstraints(min_length=1, max_length=SKILL_GROUP_MAX_LENGTH)]] | None = None


class ProviderWireSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    field: SuggestionField
    evidence: list[Evidence] = Field(min_length=1, max_length=10)
    value: ProviderWireValue

    @model_validator(mode="after")
    def require_value_bucket_matching_field(self):
        filled = {name for name in ProviderWireValue.model_fields
                  if getattr(self.value, name) is not None}
        expected = _WIRE_BUCKET_FOR_FIELD[self.field]
        if filled != {expected}:
            raise ValueError(f"suggestion value must set exactly the '{expected}' field")
        return self


class ProviderWireSuggestionOutput(ProviderSuggestionOutput):
    suggestions: list[ProviderWireSuggestion] = Field(max_length=50)
    not_found: list[SuggestionField] = Field(max_length=len(ALL_SUGGESTION_FIELDS))

    @model_validator(mode="after")
    def account_for_every_profile_field(self):
        suggested = {item.field for item in self.suggestions}
        absent = set(self.not_found)
        if len(absent) != len(self.not_found):
            raise ValueError("not_found fields must be unique")
        if suggested & absent:
            raise ValueError("a field cannot be suggested and not_found")
        if suggested | absent != ALL_SUGGESTION_FIELDS:
            raise ValueError("every profile field must be suggested or not_found")
        return self

    def _to_domain_suggestion(self, item: ProviderWireSuggestion) -> ProfileSuggestion:
        value = item.value
        if item.field in _WIRE_TEXT_FIELDS:
            cls = {
                "headline": HeadlineSuggestion,
                "location": LocationSuggestion,
                "target_roles": TargetRoleSuggestion,
            }[item.field]
            return cls(id=item.id, field=item.field, value=value.text, evidence=item.evidence)
        if item.field == "skills":
            return SkillsSuggestion(
                id=item.id, field=item.field, value=_normalize_skills(value.skills),
                evidence=item.evidence)
        if item.field == "experience":
            return ExperienceSuggestion(
                id=item.id, field=item.field, value=value.experience.to_domain(),
                evidence=item.evidence)
        if item.field == "education":
            return EducationSuggestion(
                id=item.id, field=item.field, value=value.education, evidence=item.evidence)
        if item.field == "languages":
            return LanguageSuggestion(
                id=item.id, field=item.field, value=value.language, evidence=item.evidence)
        if item.field == "remote_preference":
            return RemotePreferenceSuggestion(
                id=item.id, field=item.field, value=value.remote_preference,
                evidence=item.evidence)
        if item.field == "work_authorization":
            return WorkAuthorizationSuggestion(
                id=item.id, field=item.field, value=value.work_authorization,
                evidence=item.evidence)
        return SalaryPreferenceSuggestion(
            id=item.id, field=item.field, value=value.salary, evidence=item.evidence)

    def to_domain(self) -> ProviderSuggestionOutput:
        return ProviderSuggestionOutput(
            suggestions=[self._to_domain_suggestion(item) for item in self.suggestions],
            not_found=self.not_found, partial=self.partial, message=self.message,
        )

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        # The SDK loads the text-format schema via model_json_schema(), so the
        # wire payload (and the evaluation request plan, which estimates from
        # the same call) is the compact strict form below. Parsing of the
        # returned content always goes through this class's own pydantic
        # validation.
        return _strict_wire_schema(
            _compact_wire_schema(super().model_json_schema(*args, **kwargs)))


def _strict_wire_schema(schema):
    """Make the compact schema deterministic strict-schema compatible.

    OpenAI strict structured outputs reject object ``anyOf`` unions; every
    object must set ``additionalProperties: false`` and list all of its
    properties in ``required`` (nullable fields stay ``anyOf`` with ``null``,
    the only union form strict mode permits). ``_compact_wire_schema`` already
    removed defaults/titles, so the flat shape below is fully strict: the ten
    suggestion branches collapse into a single ``ProviderWireSuggestion``
    whose ``value`` uses nullable buckets.
    """
    def visit(node):
        if isinstance(node, dict):
            result = {}
            for key, value in node.items():
                if key in {"properties", "$defs", "definitions", "patternProperties"}:
                    result[key] = {name: visit(spec) for name, spec in value.items()}
                else:
                    result[key] = visit(value)
            if "properties" in result:
                result["additionalProperties"] = False
                result["required"] = list(result["properties"])
            return result
        if isinstance(node, list):
            return [visit(item) for item in node]
        return node
    return visit(schema)


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


class GroqProfileOutput(BaseModel):
    """Groq profile wire contract: absent required keys cannot become defaults."""
    model_config = ConfigDict(extra="forbid")
    suggestions: list[Union[
        HeadlineSuggestion, LocationSuggestion, GroqSkillsSuggestion,
        ProviderExperienceSuggestion, EducationSuggestion, LanguageSuggestion,
    ]] = Field(max_length=50)
    # Accepted only for shared offline domain fixtures, then removed from this
    # provider's serialized schema to preserve its evaluated 8k-TPM contract.
    not_found: list[SuggestionField] = Field(default_factory=list, exclude=True)
    partial: bool
    message: str | None = Field(max_length=500)

    def to_domain(self) -> ProviderSuggestionOutput:
        return ProviderSuggestionOutput(
            suggestions=[
                ExperienceSuggestion(id=item.id, field=item.field,
                                     value=item.value.to_domain(), evidence=item.evidence)
                if isinstance(item, ProviderExperienceSuggestion)
                else SkillsSuggestion(id=item.id, field=item.field,
                                      value=[item.value], evidence=item.evidence)
                if isinstance(item, GroqSkillsSuggestion)
                else item
                for item in self.suggestions
            ],
            not_found=(self.not_found or sorted(
                ALL_SUGGESTION_FIELDS - {item.field for item in self.suggestions}
            )),
            partial=self.partial, message=self.message,
        )

    @model_validator(mode="after")
    def require_all_wire_fields(self):
        errors = []

        def visit(value, path=()):
            if isinstance(value, BaseModel):
                for name in type(value).model_fields:
                    if isinstance(value, GroqProfileOutput) and name == "not_found":
                        continue
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
        schema = super().model_json_schema(*args, **kwargs)
        schema["properties"].pop("not_found", None)
        schema["required"] = [name for name in schema.get("required", []) if name != "not_found"]
        return _groq_profile_schema(_compact_wire_schema(schema))


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
    failure_field: str | None = None
    failure_diagnostic: dict[str, Any] | None = None
    applied_at: datetime | None
    apply_result: dict[str, Any] | None
    profile: CandidateProfileResponse | None = None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def field_statuses(self) -> dict[str, str]:
        result = {field: "needs_review" for field in sorted(ALL_SUGGESTION_FIELDS)}
        for item in self.suggestions or []:
            field = item.get("field")
            if field in result:
                if item.get("status") != "not_found":
                    result[field] = "suggested"
                elif result[field] != "suggested":
                    result[field] = "not_found"
        return result


class ReviewSuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selections: list[ProfileSuggestion] = Field(default_factory=list, max_length=50)
    manual_fields: CandidateProfileUpdate | None = None

    @model_validator(mode="after")
    def require_changes(self):
        if not self.selections and not (self.manual_fields and self.manual_fields.model_fields_set):
            raise ValueError("Select at least one suggestion or edit a manual field.")
        return self


class ApplySuggestionRequest(ReviewSuggestionRequest):
    reviewed_profile_revision: str | None = Field(default=None, min_length=1, max_length=64)


class SuggestionReviewResponse(BaseModel):
    current_profile: CandidateProfileResponse | None
    proposed_profile: CandidateProfileUpdate
    reviewed_profile_revision: str
    changed_fields: list[SuggestionField]
