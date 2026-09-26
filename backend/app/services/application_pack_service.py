"""Owner-scoped immutable source snapshots and append-only document revisions."""
import copy
import hashlib
from itertools import combinations
import json
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError
from sqlalchemy import func, select, update

from app.models import ApplicationPack, ApplicationPackOperation, ApplicationPackVersion, CandidateProfile, Resume, ResumeExtraction, SavedJob
from app.schemas.application_packs import (
    HEADINGS,
    PackGenerate,
    PackList,
    PackOptions,
    PackOperation,
    PackProviderOutput,
    PackResponse,
    PackVersionList,
    PackVersionResponse,
    ProviderBlock,
)
from app.schemas.profile import CandidateProfileUpdate
from app.services import ai_usage
from app.services.ai_provider import ProviderFailure, OpenAIResponsesProvider, DeterministicTestProvider, PACK_PROMPT_VERSION
from app.services.profile_suggestion_service import SuggestionError, provider_configuration as shared_provider_configuration

PROMPT_VERSION = PACK_PROMPT_VERSION
MAX_VERSIONS = 100


class PackError(Exception):
    def __init__(self, status_code, message):
        self.status_code, self.message = status_code, message
        super().__init__(message)


class UnsupportedPackClaim(PackError):
    """A parsed draft sentence failed the local source-to-claim check."""


def pack_failure_message(error: ProviderFailure) -> str:
    """Only provider failure categories, never upstream text, reach saved packs."""
    messages = {
        "output_limit": "The AI response reached the pack output limit before both documents were complete. No draft was saved.",
        "timeout": "The AI provider timed out before both documents were complete. No draft was saved.",
        "rate_limit": "The AI provider is rate limited. Try again later; no draft was saved.",
        "billing": "The AI provider account cannot process this request. Check provider billing settings.",
        "authentication": "The AI provider credential was rejected. Check the deployment secret.",
        "model_unavailable": "The configured AI model is unavailable for application packs.",
        "invalid_request": "The AI provider rejected the pack request. No draft was saved.",
        "request_contract_invalid": "The AI provider rejected the pack response schema. No draft was saved.",
        "structured_output_invalid": "The AI provider did not return a complete structured pack. No draft was saved.",
    }
    return messages.get(error.category, "The AI provider could not produce a complete supported draft. No draft was saved.")


def pack_provider_configuration(settings):
    # Reuse enablement, credential and guarded-test gates; never fall back to
    # the profile/fit provider when pack credentials are absent.
    return shared_provider_configuration(settings.model_copy(update={
        "JOBPILOT_AI_PROVIDER": settings.JOBPILOT_PACK_PROVIDER,
        "JOBPILOT_AI_MODEL": settings.JOBPILOT_PACK_MODEL,
    }))


def pack_provider_for(settings):
    name, model, key = pack_provider_configuration(settings)
    if name == "deterministic-test":
        return DeterministicTestProvider()
    return OpenAIResponsesProvider(
        api_key=key, model=model, timeout=settings.JOBPILOT_PACK_TIMEOUT_SECONDS,
        max_output_tokens=settings.JOBPILOT_PACK_MAX_OUTPUT_TOKENS,
        pack_reasoning_effort=settings.JOBPILOT_PACK_REASONING_EFFORT,
    )


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def owned_job(db, owner_id, job_id, lock=False):
    query = select(SavedJob).where(SavedJob.id == job_id, SavedJob.owner_id ==
                                   owner_id).execution_options(populate_existing=True)
    job = db.scalar(query.with_for_update() if lock else query)
    if job is None:
        raise PackError(404, "Job not found")
    return job


def capture(db, owner_id, job_id, resume_id, lock=False):
    job = owned_job(db, owner_id, job_id, lock)
    query = select(Resume).where(Resume.id == resume_id, Resume.owner_id ==
                                 owner_id).execution_options(populate_existing=True)
    resume = db.scalar(query.with_for_update() if lock else query)
    if resume is None:
        raise PackError(404, "Resume not found")
    query = select(CandidateProfile).where(
        CandidateProfile.owner_id == owner_id).execution_options(populate_existing=True)
    profile = db.scalar(query.with_for_update() if lock else query)
    query = select(ResumeExtraction).where(ResumeExtraction.resume_id ==
                                           resume.id).execution_options(populate_existing=True)
    extraction = db.scalar(query.with_for_update() if lock else query)
    if not (job.description or "").strip():
        raise PackError(
            409, "Save a job description before generating an application pack.")
    if profile is None:
        raise PackError(
            409, "Save your candidate profile before generating an application pack.")
    values = CandidateProfileUpdate.model_validate({name: getattr(
        profile, name) for name in CandidateProfileUpdate.model_fields}).model_dump(mode="json")
    if not any(value for value in values.values()):
        raise PackError(
            409, "Add candidate facts to your saved profile first.")
    if extraction is None or extraction.status != "succeeded" or extraction.reviewed_at is None or not (extraction.draft_text or "").strip():
        raise PackError(
            409, "Select a CV with nonempty confirmed text from the resume library.")
    facts = []
    # Keep each experience/project context intact; no silent truncation of notes.
    for path, value in values.items():
        for index, item in enumerate(value if isinstance(value, list) else [value]):
            if not item:
                continue
            facts.append({"id": f"fact-{len(facts) + 1}", "path": f"{path}[{index}]" if isinstance(value, list) else path,
                          "value": json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, dict) else str(item)})
    from app.services.job_application_skill_service import list_current
    selected = list_current(db, owner_id, job_id)
    application_skills = [{"id": str(item.id), "skill": item.skill, "importance": item.importance,
                           "job_quote": item.job_quote, "analysis_id": str(item.analysis_id)} for item in selected]
    application_skill_facts = [{"id": f"fact-{len(facts) + index + 1}", "path": f"application_skills[{index}]",
                                "value": item["skill"]} for index, item in enumerate(application_skills)]
    snapshot = {
        "job": {"id": str(job.id), "title": job.title, "company": job.company, "location": job.location, "description": job.description},
        "profile_id": str(profile.id), "profile": values, "profile_facts": facts,
        "application_skills": application_skills, "application_skill_facts": application_skill_facts,
        "resume_id": str(resume.id), "extraction_id": str(extraction.id), "cv_text": extraction.draft_text,
        "resume_name": resume.display_name, "reviewed_at": extraction.reviewed_at.isoformat(),
        "job_updated_at": job.updated_at.isoformat(), "profile_updated_at": profile.updated_at.isoformat(),
    }
    return snapshot


def source_hash(snapshot):
    # Display names and timestamps/notes/archive are not candidate facts.
    values = {key: snapshot[key] for key in ("job", "profile_id", "profile", "resume_id", "extraction_id", "cv_text")}
    if snapshot.get("application_skills"):
        values["application_skills"] = snapshot["application_skills"]
    return digest(values)


def outdated(db, pack):
    try:
        return source_hash(capture(db, pack.owner_id, pack.job_id, pack.resume_id)) != pack.source_hash
    except PackError:
        return True


def get_owned(db, owner_id, job_id, pack_id, lock=False):
    owned_job(db, owner_id, job_id)
    query = select(ApplicationPack).where(ApplicationPack.id == pack_id, ApplicationPack.owner_id ==
                                          owner_id, ApplicationPack.job_id == job_id).execution_options(populate_existing=True)
    pack = db.scalar(query.with_for_update() if lock else query)
    if pack is None:
        raise PackError(404, "Application pack not found")
    return pack


def version_for(db, pack, number):
    version = db.scalar(select(ApplicationPackVersion).where(ApplicationPackVersion.pack_id ==
                        pack.id, ApplicationPackVersion.number == number).execution_options(populate_existing=True))
    if version is None:
        raise PackError(404, "Application pack version not found")
    return version


def response(db, pack, version=None):
    status, message = pack.status, pack.outcome_message
    if status == "generating" and pack.deadline < datetime.now(timezone.utc):
        status, message = "failed", "Generation expired. Generate a new pack to retry."
    return PackResponse(
        id=pack.id, job_id=pack.job_id, resume_id=pack.resume_id, status=status, current_version=pack.current_version,
        version=PackVersionResponse.model_validate(version or version_for(
            db, pack, pack.current_version)) if pack.current_version else None,
        review_notes=pack.review_notes, source_snapshot=pack.source_snapshot, is_outdated=outdated(
            db, pack),
        provider=pack.provider, model=pack.model, outcome_message=message, created_at=pack.created_at,
    )


def canonical_structural_labels(output: PackProviderOutput, snapshot):
    """Canonicalize only known labels; never guess from length or factual prose.

    Work on a copy so raw provider evidence remains available for diagnostics.
    Revalidate after removing a redundant label: headings alone are not a document.
    """
    payload = output.model_dump(mode="json")
    for block in payload["cv"]["blocks"]:
        if block["kind"] == "paragraph" and block["text"] == "Contact" and not block["evidence"]:
            block["kind"] = "heading"
    letter = payload["cover_letter"]["blocks"]
    title = snapshot.get("job", {}).get("title")
    if isinstance(title, str) and title and any(
        block["kind"] == "heading" and block["text"] == "Cover letter" for block in letter
    ):
        # Exact saved-job context only, redundant with the document heading.
        # No prefix matching, whitespace folding, inferred titles or appended claims.
        payload["cover_letter"]["blocks"] = [block for block in letter if not (
            block["kind"] == "paragraph" and not block["evidence"]
            and block["text"] == "Application for " + title
        )]
    return PackProviderOutput.model_validate(payload)


_QUOTE_DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-"})
_QUOTE_MARKS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def _quote_char(char: str) -> str:
    return unicodedata.normalize("NFKC", char).casefold().translate(_QUOTE_DASHES).translate(_QUOTE_MARKS)


def _claim_typography(text: str) -> str:
    return text.translate(_QUOTE_DASHES).translate(_QUOTE_MARKS)


def _bullet_content(text: str) -> str:
    return re.sub(r"^[\s\u2022\u25e6\u25cf\u25aa*\-]+", "", text).strip()


def canonical_cv_quotes(output, snapshot):
    """Recover an exact CV span from a uniquely matching formatted citation.

    Only whitespace and common typographic dash/quote variants may differ.
    The returned citation is always a contiguous excerpt of the reviewed CV.
    Ambiguous matches and changed words remain invalid for the strict validator.
    """
    payload = PackProviderOutput.model_validate(output).model_dump(mode="json")
    source = snapshot["cv_text"]
    compact, positions = [], []
    for index, char in enumerate(source):
        for normalized_char in _quote_char(char):
            if not normalized_char.isspace():
                compact.append(normalized_char)
                positions.append(index)
    compact_source = "".join(compact)
    corrected = 0
    for name in ("cv", "cover_letter"):
        for block in payload[name]["blocks"]:
            for evidence in block["evidence"]:
                quote = evidence["cv_quote"]
                if quote is None or quote in source:
                    continue
                trimmed = quote.strip()
                if trimmed in source:
                    evidence["cv_quote"] = trimmed
                    corrected += 1
                    continue
                key = "".join(_quote_char(char) for char in quote if not char.isspace())
                if len(key) < 8:
                    continue
                start = compact_source.find(key)
                if start < 0 or compact_source.find(key, start + 1) >= 0:
                    continue
                original = source[positions[start]:positions[start + len(key) - 1] + 1]
                if len(original) > 4_000:
                    continue
                evidence["cv_quote"] = original
                corrected += 1
    if corrected:
        payload["review_notes"] = [*payload["review_notes"][:19],
            f"{corrected} CV citation(s) were matched to exact passages in the confirmed text after formatting differences. Review the cited source before approval."]
    return PackProviderOutput.model_validate(payload)


def validate_generated(output, snapshot):
    output = canonical_structural_labels(PackProviderOutput.model_validate(output), snapshot)
    facts = {fact["id"]: fact["value"] for fact in [*snapshot["profile_facts"], *snapshot.get("application_skill_facts", [])]}
    for document in (output.cv, output.cover_letter):
        for block in document.blocks:
            _validate_block(block, facts, snapshot["cv_text"], snapshot)
    return output


def _validate_block(block: ProviderBlock, facts: dict[str, str], cv_text: str, snapshot=None):
    from app.services.evidence_validation import supported_claim

    candidate_title = block.kind == "heading" and block.text not in HEADINGS
    if candidate_title and (len(block.evidence) != 1 or block.evidence[0].cv_quote != block.text
                            or len(block.text) > 100):
        raise PackError(502, "The generated document included an unsupported heading. Retry generation.")
    job = (snapshot or {}).get("job", {})
    framing = {
        ("letter-context", "subheading"): f"Application for {job.get('title')} at {job.get('company')}",
        ("letter-greeting", "paragraph"): "Dear Hiring Team,",
        ("letter-closing", "paragraph"): "I would welcome the opportunity to discuss this application.",
        ("letter-signoff", "paragraph"): "Sincerely,",
    }
    if snapshot and not block.evidence and framing.get((block.id, block.kind)) == block.text:
        return
    if block.kind != "heading" and not block.evidence:
        raise PackError(502, "A generated claim was missing source evidence. Retry generation.")
    for evidence in block.evidence:
        if not evidence.fact_id and not (evidence.cv_quote or "").strip():
            raise PackError(502, "The generated document included empty evidence.")
        if evidence.fact_id and evidence.fact_id not in facts:
            raise PackError(502, "The generated document referenced an unknown profile fact.")
        if evidence.cv_quote is not None and (not evidence.cv_quote.strip() or evidence.cv_quote not in cv_text):
            raise PackError(502, "The generated document included an unsupported CV passage.")
    if block.kind != "heading" or candidate_title:
        passages = [passage for evidence in block.evidence
                    for passage in (facts.get(evidence.fact_id), evidence.cv_quote) if passage]
        relationship_claim = candidate_title or block.kind == "subheading" or bool(re.search(
            r"\b(?:use|used|using|applied|integrated|created|designed|implemented|architected|deployed|maintained|delivered)\b",
            block.text, re.I))
        if not supported_claim(_claim_typography(block.text), [_claim_typography(p) for p in passages],
                               single_passage=relationship_claim):
            raise UnsupportedPackClaim(502, "The draft contains a claim not supported by its cited evidence. Review the source and try again.")


def _readable_cv_passage(block: ProviderBlock, document_name: str, facts: dict[str, str], cv_text: str):
    """Use one short cited CV passage; never join independent sources."""
    from app.services.evidence_validation import supported_claim, terms

    if len(block.evidence) != 1:
        return None
    reference = block.evidence[0]
    quote = reference.cv_quote
    if reference.fact_id or not quote or quote not in cv_text or len(quote) > 400:
        return None
    claim_terms, source_terms = terms(_claim_typography(block.text)), terms(_claim_typography(quote))
    overlap = claim_terms & source_terms
    if not overlap:
        return None
    if source_terms & {"no", "not", "never", "without"} and not claim_terms & {"no", "not", "never", "without"}:
        return None
    wording = re.sub(r"\s+", " ", quote).strip()
    wording = re.sub(r"^(?:[•*]\s*|-\s+)", "", wording)
    if not wording or len(wording) > 400:
        return None
    if document_name == "cover_letter" and re.match(
            r"^(?:built|developed|implemented|integrated|designed|created|managed|led|wrote)\b", wording, re.I):
        wording = "I " + wording[0].lower() + wording[1:]
    if document_name == "cover_letter" and wording[-1] not in ".!?":
        wording += "."
    if not supported_claim(_claim_typography(wording), [_claim_typography(quote)]):
        return None
    candidate = block.model_copy(update={"text": wording})
    _validate_block(candidate, facts, cv_text)
    return candidate


def _remove_empty_sections(blocks: list[ProviderBlock], title: str) -> list[ProviderBlock]:
    kept = []
    for index, block in enumerate(blocks):
        if block.kind != "heading":
            kept.append(block)
            continue
        next_heading = next((offset for offset in range(index + 1, len(blocks))
                             if blocks[offset].kind == "heading"), len(blocks))
        if block.text == title or any(next_block.kind != "heading"
                                      for next_block in blocks[index + 1:next_heading]):
            kept.append(block)
    return kept


def _supported_sentences(block: ProviderBlock, facts: dict[str, str], snapshot) -> list[ProviderBlock]:
    """Retain individually supported sentences with only their useful citations."""
    if block.kind != "paragraph":
        return []
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", block.text.strip())
    if len(sentences) < 2:
        return []
    kept = []
    for index, sentence in enumerate(sentences):
        for count in range(1, min(3, len(block.evidence)) + 1):
            for references in combinations(block.evidence, count):
                candidate = block.model_copy(update={
                    "id": f"{block.id[:56]}-s{index + 1}",
                    "text": sentence,
                    "evidence": list(references),
                })
                try:
                    _validate_block(candidate, facts, snapshot["cv_text"], snapshot)
                except PackError:
                    continue
                kept.append(candidate)
                break
            else:
                continue
            break
    return kept


def _verified_cover_letter(snapshot, facts: dict[str, str]) -> list[ProviderBlock]:
    """Build distinct, relevant paragraphs from individual saved facts."""
    from app.services.evidence_validation import terms

    blocks = [ProviderBlock(id="verified-letter-title", kind="heading", text="Cover letter", evidence=[])]
    job_terms = terms(snapshot.get("job", {}).get("description") or "")

    def add(text: str, references: list[dict]):
        try:
            block = ProviderBlock.model_validate({
                "id": f"verified-letter-{len(blocks)}", "kind": "paragraph",
                "text": text, "evidence": references,
            })
            _validate_block(block, facts, snapshot["cv_text"], snapshot)
        except (PackError, ValidationError):
            return
        blocks.append(block)

    profile = snapshot["profile_facts"]
    application_facts = snapshot.get("application_skill_facts", [])
    selections = snapshot.get("application_skills", [])
    app_ranked = sorted(enumerate(application_facts), key=lambda entry: (
        0 if entry[0] < len(selections) and selections[entry[0]].get("importance") == "required" else 1,
        entry[0]))
    skill_facts = [fact for _, fact in app_ranked]
    skill_facts += [fact for fact in profile if fact["path"].startswith("skills[")]
    selected, seen = [], set()
    for fact in skill_facts:
        skill = fact["value"].strip()
        if skill.casefold() in seen or not terms(skill) & job_terms:
            continue
        selected.append(fact)
        seen.add(skill.casefold())
        if len(selected) == 3:
            break

    headline = next((fact for fact in profile if fact["path"] == "headline"), None)
    if headline:
        value = headline["value"].strip().rstrip(".")
        add(f"I am a {value}.", [{"fact_id": headline["id"], "cv_quote": None}])
    if selected:
        add("I bring " + ", ".join(fact["value"] for fact in selected) + " to this role.",
            [{"fact_id": fact["id"], "cv_quote": None} for fact in selected])

    examples = []
    for fact in profile:
        if not fact["path"].startswith("experience["):
            continue
        try:
            entry = json.loads(fact["value"])
        except (TypeError, ValueError):
            continue
        if not isinstance(entry, dict):
            continue
        for line in str(entry.get("notes") or "").splitlines():
            wording = re.sub(r"^[\s•*\-]+", "", line).strip()
            if not re.match(r"^(?:built|developed|implemented|integrated|designed|created|managed|led|wrote|applied|deployed|completed)\b", wording, re.I):
                continue
            if not 20 <= len(wording) <= 280:
                continue
            overlap = len(terms(wording) & job_terms)
            if overlap:
                examples.append((overlap, fact["id"], wording))
    used = set()
    for _, fact_id, wording in sorted(examples, reverse=True):
        if wording.casefold() in used:
            continue
        sentence = "I " + wording[0].lower() + wording[1:]
        if sentence[-1] not in ".!?":
            sentence += "."
        before = len(blocks)
        add(sentence, [{"fact_id": fact_id, "cv_quote": None}])
        if len(blocks) > before:
            used.add(wording.casefold())
        if len(blocks) >= 5:
            break
    return blocks


def salvage_generated(output, snapshot):
    """Keep supported statements and safe single-source rewrites; omit the rest."""
    normalized = canonical_structural_labels(canonical_cv_quotes(output, snapshot), snapshot)
    facts = {fact["id"]: fact["value"] for fact in [*snapshot["profile_facts"], *snapshot.get("application_skill_facts", [])]}
    payload = normalized.model_dump(mode="json")
    omitted = {"cv": 0, "cover_letter": 0}
    replaced = {"cv": 0, "cover_letter": 0}
    rebuilt_letter = False
    short_letter = False
    for name, title in (("cv", "Curriculum vitae"), ("cover_letter", "Cover letter")):
        retained = []
        for block in getattr(normalized, name).blocks:
            if block.kind == "bullet":
                cleaned = _bullet_content(block.text)
                if not cleaned:
                    omitted[name] += 1
                    continue
                block = block.model_copy(update={"text": cleaned})
            try:
                _validate_block(block, facts, snapshot["cv_text"], snapshot)
                retained.append(block)
            except PackError as error:
                sentences = (_supported_sentences(block, facts, snapshot)
                             if isinstance(error, UnsupportedPackClaim) else [])
                if sentences:
                    retained.extend(sentences)
                    omitted[name] += len(re.split(r"(?<=[.!?])\s+(?=[A-Z])", block.text.strip())) - len(sentences)
                    continue
                try:
                    repaired = (_readable_cv_passage(block, name, facts, snapshot["cv_text"])
                                if isinstance(error, UnsupportedPackClaim) else None)
                except PackError:
                    repaired = None
                if repaired:
                    retained.append(repaired)
                    replaced[name] += 1
                else:
                    omitted[name] += 1
        retained = _remove_empty_sections(retained, title)
        body_count = sum(block.kind != "heading" for block in retained)
        if name == "cover_letter" and body_count < 4:
            alternative = _verified_cover_letter(snapshot, facts)
            alternative_count = sum(block.kind != "heading" for block in alternative)
            if alternative_count > body_count:
                retained = alternative
                body_count = alternative_count
                rebuilt_letter = True
        if body_count < 2:
            document = "CV" if name == "cv" else "cover letter"
            raise PackError(502, f"The AI draft did not retain enough supported {document} content. No documents were saved.")
        if name == "cover_letter" and body_count < 4:
            short_letter = True
        payload[name]["blocks"] = [block.model_dump(mode="json") for block in retained]
    if any(omitted.values()) or any(replaced.values()):
        payload["review_notes"] = [*payload["review_notes"][:19],
            f"Evidence review: {replaced['cv']} CV and {replaced['cover_letter']} cover-letter statement(s) were rewritten from one exact CV passage; "
            f"{omitted['cv']} CV and {omitted['cover_letter']} cover-letter statement(s) were omitted because their claims or citations could not be verified. Review both documents before approval."]
    if rebuilt_letter:
        payload["review_notes"] = [*payload["review_notes"][:19],
            "The cover letter was rebuilt from individual saved facts because too little AI wording passed evidence review. Check its relevance and accuracy before approval."]
    if short_letter:
        payload["review_notes"] = [*payload["review_notes"][:19],
            "The confirmed sources support a shorter cover letter. Review it before approval; add more verified facts to your profile and CV if you want a fuller letter."]
    return PackProviderOutput.model_validate(payload)


def include_confirmed_job_skills(output, snapshot):
    """Ensure job-relevant saved skills appear in both reviewed documents."""
    payload = output.model_dump(mode="json")
    job_text = (snapshot.get("job", {}).get("description") or "").casefold()
    def mentions(text, skill):
        return bool(re.search(r"(?<![\w+#.-])" + re.escape(skill.casefold()) + r"(?![\w+#.-])", text))
    profile_relevant = [fact for fact in snapshot["profile_facts"]
                        if fact["path"].startswith("skills[") and mentions(job_text, fact["value"])]
    application_facts = snapshot.get("application_skill_facts", [])
    selections = snapshot.get("application_skills", [])
    prioritized_application_facts = sorted(
        enumerate(application_facts),
        key=lambda entry: (0 if entry[0] < len(selections) and selections[entry[0]].get("importance") == "required" else 1,
                           entry[0]))
    relevant = [*profile_relevant, *application_facts]
    added = 0
    for name in ("cv", "cover_letter"):
        blocks = payload[name]["blocks"]
        if name == "cv":
            section = next((index for index, block in enumerate(blocks)
                            if block["kind"] == "heading" and block["text"] == "Skills"), None)
            next_section = next((index for index in range(section + 1, len(blocks))
                                 if blocks[index]["kind"] == "heading"), len(blocks)) if section is not None else 0
            body = " ".join(block["text"].casefold() for block in blocks[(section + 1 if section is not None else 0):next_section])
            candidates = relevant
        else:
            body = " ".join(block["text"].casefold() for block in blocks if block["kind"] != "heading")
            candidates = [*(fact for _, fact in prioritized_application_facts[:2]), *profile_relevant[:2]]
        missing = [fact for fact in candidates if not mentions(body, fact["value"])]
        if missing and name == "cv" and not any(block["kind"] == "heading" and block["text"] == "Skills" for block in blocks):
            if len(blocks) >= 99:
                raise PackError(502, "The generated CV is too long to include confirmed skills. Try a shorter confirmed CV.")
            heading_id = "confirmed-skills-heading"
            existing_ids = {block["id"] for block in blocks}
            while heading_id in existing_ids:
                heading_id += "-1"
            blocks.append({"id": heading_id, "kind": "heading", "text": "Skills", "evidence": []})
        for offset in range(0, len(missing), 10):
            group = missing[offset:offset + 10]
            if len(blocks) >= 100:
                raise PackError(502, "The generated CV is too long to include confirmed skills. Try a shorter confirmed CV.")
            block_id = f"confirmed-skills-{offset // 10 + 1}"
            existing_ids = {block["id"] for block in blocks}
            while block_id in existing_ids:
                block_id += "-1"
            addition = {"id": block_id, "kind": "bullet" if name == "cv" else "paragraph",
                        "text": ("" if name == "cv" else "I bring ") + ", ".join(fact["value"] for fact in group) + ("" if name == "cv" else " to this role."),
                        "evidence": [{"fact_id": fact["id"], "cv_quote": None} for fact in group]}
            if name == "cv":
                section = next((index for index, block in enumerate(blocks)
                                if block["kind"] == "heading" and block["text"] == "Skills"), len(blocks) - 1)
                after = next((index for index in range(section + 1, len(blocks))
                              if blocks[index]["kind"] == "heading"), len(blocks))
                blocks.insert(after, addition)
            else:
                body_indices = [index for index, block in enumerate(blocks) if block["kind"] != "heading"]
                before_closing = body_indices[-1] if len(body_indices) > 1 else len(blocks)
                blocks.insert(before_closing, addition)
            added += 1
    if added:
        payload["review_notes"] = [*payload["review_notes"][:19],
            "Job-relevant saved profile skills omitted by the AI were included as sourced statements. Confirm each skill before approval."]
    return PackProviderOutput.model_validate(payload)


def _cv_identity(snapshot):
    """Use only exact spans from the reviewed CV for identity and contact."""
    source = snapshot["cv_text"]
    header_lines = source.splitlines()[:8]
    name = None
    for raw_line in header_lines[:5]:
        line = re.sub(r"^\s*---\s*Page\s+\d+\s*---\s*", "", raw_line).strip()
        candidate = re.match(r"^([^\d@|•]{4,80}?)(?:\s{3,}|$)", line)
        if candidate:
            words = candidate.group(1).strip().split()
            if (2 <= len(words) <= 5 and all(word[0].isupper() for word in words)
                    and not set(word.casefold() for word in words) & {"skills", "summary", "engineer", "developer", "experience"}):
                name = candidate.group(1).strip()
                break
    header = "\n".join(header_lines)
    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", header)
    phone_match = re.search(r"\+\d{1,3}(?:[\s.-]*\d){7,12}", header)
    return name, email_match.group(0) if email_match else None, phone_match.group(0) if phone_match else None


def _organize_cv(blocks: list[dict], snapshot) -> list[dict]:
    """Give supported experience a role label; keep unassigned bullets neutral."""
    experience = []
    for fact in snapshot["profile_facts"]:
        if not fact["path"].startswith("experience["):
            continue
        try:
            value = json.loads(fact["value"])
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict) and value.get("title") and value.get("organization"):
            experience.append((fact, value))

    def source_key(value):
        return re.sub(r"\W+", "", value.casefold())

    ordered, highlights = [], []
    section, active_role, project_quote, project_label, project_emitted = "", None, None, None, False
    for block in blocks:
        if block["kind"] == "heading":
            section, active_role, project_quote, project_label, project_emitted = block["text"], None, None, None, False
            ordered.append(block)
            continue
        if section == "Experience" and block["kind"] == "subheading":
            # Recreate the role label from the exact fact associated with each bullet.
            continue
        if section == "Projects" and block["kind"] == "subheading":
            project_label, project_emitted = block, False
            project_quote = next((ref.get("cv_quote") for ref in block["evidence"] if ref.get("cv_quote")), None)
            continue
        if block["kind"] != "bullet" or section not in {"Experience", "Projects"}:
            ordered.append(block)
            continue
        if section == "Experience":
            role = next(((fact, value) for fact, value in experience if any(
                ref.get("fact_id") == fact["id"] for ref in block["evidence"])), None)
            if role is None:
                role = next(((fact, value) for fact, value in experience
                             if source_key(block["text"]) and source_key(block["text"]) in source_key(value.get("notes") or "")), None)
            if role is None:
                highlights.append(block)
                continue
            fact, value = role
            if active_role != fact["id"]:
                label = f"{value['title']} — {value['organization']}"
                if value.get("period"):
                    label += f" · {value['period']}"
                ordered.append({"id": f"verified-role-{fact['id']}-{len(ordered)}", "kind": "subheading",
                                "text": label, "evidence": [{"fact_id": fact["id"], "cv_quote": None}]})
                active_role = fact["id"]
            ordered.append(block)
        else:
            bullet_quote = next((ref.get("cv_quote") for ref in block["evidence"] if ref.get("cv_quote")), None)
            source = snapshot["cv_text"]
            if (project_quote and bullet_quote and 0 <= source.find(bullet_quote) - source.find(project_quote) <= 600
                    and source.find(project_quote) >= 0):
                if project_label and not project_emitted:
                    ordered.append(project_label)
                    project_emitted = True
                ordered.append(block)
            else:
                highlights.append(block)

    retained = _remove_empty_sections([ProviderBlock.model_validate(block) for block in ordered], ordered[0]["text"])
    ordered = [block.model_dump(mode="json") for block in retained]
    if highlights:
        insert_at = next((index for index, block in enumerate(ordered)
                          if block["kind"] == "heading" and block["text"] in {"Education", "Languages"}), len(ordered))
        ordered[insert_at:insert_at] = [
            {"id": "verified-highlights", "kind": "heading", "text": "Relevant highlights", "evidence": []},
            *highlights,
        ]
    section_order = {name: index for index, name in enumerate((
        "Contact", "Summary", "Skills", "Experience", "Projects", "Relevant highlights",
        "Education", "Languages", "Additional information"))}
    prefix, sections = [], []
    current = None
    for block in ordered:
        if block["kind"] == "heading" and block["text"] in section_order:
            current = [block]
            sections.append(current)
        elif current is None:
            prefix.append(block)
        else:
            current.append(block)
    sections.sort(key=lambda section: section_order[section[0]["text"]])
    return [*prefix, *(block for section in sections for block in section)]


def finish_documents(output, snapshot):
    """Add reviewed identity and a deterministic formal letter frame."""
    payload = output.model_dump(mode="json")
    facts = {fact["id"]: fact["value"] for fact in [*snapshot["profile_facts"], *snapshot.get("application_skill_facts", [])]}
    name, email, phone = _cv_identity(snapshot)

    def make(block_id, kind, text, quotes=()):
        references = [{"fact_id": None, "cv_quote": quote} for quote in quotes]
        block = ProviderBlock.model_validate({"id": block_id, "kind": kind, "text": text, "evidence": references})
        _validate_block(block, facts, snapshot["cv_text"], snapshot)
        return block.model_dump(mode="json")

    cv = payload["cv"]["blocks"]
    if name and cv and cv[0]["kind"] == "heading" and cv[0]["text"] == "Curriculum vitae":
        cv[0] = make("verified-cv-name", "heading", name, [name])
        cv[:] = [block for index, block in enumerate(cv) if index == 0 or block["text"] != name]
    contact_parts = [part for part in (email, phone) if part]
    if contact_parts and not any(all(part in block["text"] for part in contact_parts) for block in cv):
        cv.insert(1 if cv and cv[0]["kind"] == "heading" else 0,
                  make("verified-cv-contact", "paragraph", " | ".join(contact_parts), contact_parts))
    payload["cv"]["blocks"] = _organize_cv(cv, snapshot)

    letter_body = [block for block in payload["cover_letter"]["blocks"]
                   if block["kind"] != "heading" and block["id"] not in {
                       "letter-context", "letter-greeting", "letter-closing", "letter-signoff", "letter-signature"}]
    letter = [make("formal-letter-title", "heading", "Cover letter")]
    if name:
        letter.append(make("verified-letter-name", "paragraph", name, [name]))
    if contact_parts:
        letter.append(make("verified-letter-contact", "paragraph", " | ".join(contact_parts), contact_parts))
    job = snapshot["job"]
    letter.append(make("letter-context", "subheading", f"Application for {job['title']} at {job['company']}"))
    letter.append(make("letter-greeting", "paragraph", "Dear Hiring Team,"))
    letter.extend(letter_body)
    letter.append(make("letter-closing", "paragraph", "I would welcome the opportunity to discuss this application."))
    letter.append(make("letter-signoff", "paragraph", "Sincerely,"))
    if name:
        letter.append(make("letter-signature", "paragraph", name, [name]))
    payload["cover_letter"]["blocks"] = letter
    return PackProviderOutput.model_validate(payload)


def store_generated(document):
    return {"blocks": [{**block.model_dump(mode="json"), "origin": "ai"} for block in document.blocks]}


def generate(db, owner_id, job_id, body, settings):
    from app.services.privacy_service import require_consent
    require_consent(db, owner_id, "ai_application_packs")
    snapshot = capture(db, owner_id, job_id, body.resume_id)
    hashed = source_hash(snapshot)
    # Serialize duplicate requests and shared AI usage before recording a claim.
    from app.models import User
    db.scalar(select(User.id).where(User.id == owner_id).with_for_update())
    existing = db.scalar(select(ApplicationPack).where(
        ApplicationPack.owner_id == owner_id, ApplicationPack.idempotency_key == body.idempotency_key))
    if existing:
        if existing.job_id != job_id or existing.source_hash != hashed:
            raise PackError(
                409, "This request key was used with different sources. Start a new generation.")
        return existing
    try:
        provider = pack_provider_for(settings)
    except SuggestionError as error:
        raise PackError(error.status_code, error.message) from None
    request_source = {
        "job": snapshot["job"], "profile_facts": snapshot["profile_facts"],
        "application_skill_facts": snapshot["application_skill_facts"], "cv_text": snapshot["cv_text"]}
    if len(json.dumps(request_source, ensure_ascii=False)) > settings.JOBPILOT_AI_MAX_INPUT_CHARS:
        raise PackError(
            413, "The job, profile and CV text exceed the AI input limit. Use a shorter confirmed CV.")
    try:
        token = ai_usage.reserve(db, owner_id, settings.model_copy(update={
            "JOBPILOT_AI_TIMEOUT_SECONDS": settings.JOBPILOT_PACK_TIMEOUT_SECONDS,
        }), feature="pack")
    except ai_usage.AIUsageError as error:
        raise PackError(error.status_code, error.message) from None
    now = datetime.now(timezone.utc)
    db.execute(update(ApplicationPack).where(ApplicationPack.owner_id == owner_id, ApplicationPack.status == "generating",
               ApplicationPack.deadline < now).values(status="failed", outcome_message="Generation expired. Generate a new pack to retry."))
    pack_id = uuid.uuid4()
    pack = ApplicationPack(id=pack_id, owner_id=owner_id, job_id=job_id, profile_id=uuid.UUID(snapshot["profile_id"]),
                           resume_id=body.resume_id, extraction_id=uuid.UUID(
                               snapshot["extraction_id"]),
                           source_snapshot=snapshot, source_hash=hashed, idempotency_key=body.idempotency_key,
                           status="generating", current_version=0, generated=None, review_notes=[], provider=provider.name,
                           model=provider.model, prompt_version=PROMPT_VERSION, deadline=now + timedelta(seconds=settings.JOBPILOT_PACK_TIMEOUT_SECONDS + 10))
    db.add(pack)
    db.commit()
    try:
        ai_usage.dispatch_guard(db, owner_id)
        require_consent(db, owner_id, "ai_application_packs")
    except Exception:
        pack.status = "failed"
        pack.outcome_message = "Dispatch cancelled before provider request; consent or account access changed."
        ai_usage.release(db, owner_id, token)
        db.commit()
        raise
    try:
        result = ai_usage.bounded_call(lambda: provider.create_pack(
            request_source), settings.JOBPILOT_PACK_TIMEOUT_SECONDS)
        output = validate_generated(salvage_generated(result, snapshot), snapshot)
        output = validate_generated(finish_documents(include_confirmed_job_skills(output, snapshot), snapshot), snapshot)
        failure = None
    except PackError as error:
        output, failure = None, error.message
    except ProviderFailure as error:
        output, failure = None, pack_failure_message(error)
    except Exception:
        output, failure = None, "The AI provider could not produce a complete supported draft. Retry generation."
    try:
        pack = get_owned(db, owner_id, job_id, pack_id, lock=True)
    except PackError:
        ai_usage.release(db, owner_id, token)
        db.commit()
        raise PackError(404, "Application pack no longer exists") from None
    ai_usage.release(db, owner_id, token)
    if pack.status != "generating" or pack.deadline < datetime.now(timezone.utc):
        db.commit()
        raise PackError(
            409, "Generation expired. Generate a new pack to retry.")
    if failure:
        pack.status, pack.outcome_message = "failed", failure
    else:
        pack.generated = output.model_dump(mode="json")
        pack.review_notes = [
            "Human review is required: valid references do not prove a claim is correct. Compare contacts, projects and dates with the captured CV.", *output.review_notes]
        pack.status, pack.current_version = "ready", 1
        db.add(ApplicationPackVersion(pack_id=pack.id, number=1, cv=store_generated(
            output.cv), cover_letter=store_generated(output.cover_letter)))
    db.commit()
    return get_owned(db, owner_id, job_id, pack_id)


def edited_document(incoming, previous):
    originals = {block["id"]: block for block in previous["blocks"]}
    blocks = []
    for block in incoming.blocks:
        old = originals.get(block.id)
        if old and old["kind"] == block.kind and old["text"] == block.text:
            blocks.append(copy.deepcopy(old))
        else:
            blocks.append(
                {**block.model_dump(), "origin": "user", "evidence": []})
    return {"blocks": blocks}


def edit_or_approve(db, owner_id, job_id, pack_id, body, approve=False):
    # Source rows are locked before the pack to serialize approval with source
    # edits/deletions; this uses the same order as generation capture.
    pack = get_owned(db, owner_id, job_id, pack_id)
    if approve:
        snap = capture(db, owner_id, job_id, pack.resume_id, lock=True)
    pack = get_owned(db, owner_id, job_id, pack_id, lock=True)
    payload_hash = digest(
        {"action": "approve" if approve else "save", **body.model_dump(mode="json")})
    prior = db.scalar(select(ApplicationPackOperation).where(
        ApplicationPackOperation.pack_id == pack.id, ApplicationPackOperation.key == body.idempotency_key))
    if prior:
        if prior.request_hash != payload_hash:
            raise PackError(
                409, "This request key was already used for different edits or approval.")
        return pack, version_for(db, pack, prior.version_number)
    if pack.status != "ready" or pack.current_version != body.expected_version:
        raise PackError(
            409, "This draft changed in another request. Reload it before saving or approving.")
    current = version_for(db, pack, pack.current_version)
    if approve:
        if current.approved_at is None:
            if source_hash(snap) != pack.source_hash:
                raise PackError(
                    409, "The source content changed. Generate a fresh pack before approval.")
            current.approved_at = datetime.now(timezone.utc)
    else:
        cv = edited_document(body.cv, current.cv)
        letter = edited_document(body.cover_letter, current.cover_letter)
        if cv != current.cv or letter != current.cover_letter:
            if pack.current_version >= MAX_VERSIONS:
                raise PackError(
                    409, "This pack reached its 100-version limit. Generate a new pack.")
            pack.current_version += 1
            current = ApplicationPackVersion(
                pack_id=pack.id, number=pack.current_version, cv=cv, cover_letter=letter)
            db.add(current)
    db.add(ApplicationPackOperation(pack_id=pack.id, key=body.idempotency_key,
           request_hash=payload_hash, version_number=current.number))
    db.commit()
    return pack, current


def improve_pack(db, owner_id, job_id, pack_id, *, report_id, target_version,
                 checks, readiness_score, body, settings):
    """Closed-loop improvement: a readiness report produces one new draft version.

    Only an approved version that is still current can be improved. The new
    version is never approved automatically: the owner reviews it and approves
    it through the existing per-version approval gate. Prior versions and their
    reports stay immutable. Generation reuses the same evidence contract as
    pack creation, so no claim can appear without valid source evidence.
    """
    from app.services.privacy_service import require_consent
    require_consent(db, owner_id, "ai_application_packs")
    pack = get_owned(db, owner_id, job_id, pack_id)
    if pack.status != "ready":
        raise PackError(409, "This pack is not ready to improve.")
    # Same lock ordering as approval: source rows first, then the pack.
    snap = capture(db, owner_id, job_id, pack.resume_id, lock=True)
    pack = get_owned(db, owner_id, job_id, pack_id, lock=True)
    payload_hash = digest({
        "action": "improve", "report_id": str(report_id), "target_version": target_version,
        "checks": checks, **body.model_dump(mode="json")})
    prior = db.scalar(select(ApplicationPackOperation).where(
        ApplicationPackOperation.pack_id == pack.id,
        ApplicationPackOperation.key == body.idempotency_key))
    if prior:
        if prior.request_hash != payload_hash:
            raise PackError(
                409, "This request key was already used for different edits or approval.")
        version = version_for(db, pack, prior.version_number)
        return pack, version, version.review_notes or []
    current = version_for(db, pack, target_version)
    if pack.current_version != target_version:
        raise PackError(
            409, "The approved draft is no longer current. Reload before improving.")
    if current.approved_at is None:
        raise PackError(
            409, "Approve the pack version before improving from its report.")
    if source_hash(snap) != pack.source_hash:
        raise PackError(
            409, "The source content changed. Approve a fresh pack before improving.")
    if pack.current_version >= MAX_VERSIONS:
        raise PackError(
            409, "This pack reached its 100-version limit. Generate a new pack.")
    try:
        provider = pack_provider_for(settings)
    except SuggestionError as error:
        raise PackError(error.status_code, error.message) from None
    revision = {
        "job": snap["job"],
        "cv": current.cv or {"blocks": []},
        "cover_letter": current.cover_letter or {"blocks": []},
        "checks": checks,
        "readiness_score": readiness_score,
    }
    try:
        token = ai_usage.reserve(db, owner_id, settings.model_copy(update={
            "JOBPILOT_AI_TIMEOUT_SECONDS": settings.JOBPILOT_PACK_TIMEOUT_SECONDS,
        }), feature="pack")
    except ai_usage.AIUsageError as error:
        raise PackError(error.status_code, error.message) from None
    try:
        ai_usage.dispatch_guard(db, owner_id)
        require_consent(db, owner_id, "ai_application_packs")
    except Exception:
        ai_usage.release(db, owner_id, token)
        db.commit()
        raise
    try:
        result = ai_usage.bounded_call(lambda: provider.improve_pack(revision), settings.JOBPILOT_PACK_TIMEOUT_SECONDS)
        output = validate_generated(salvage_generated(result, snap), snap)
        failure = None
    except PackError as error:
        output, failure = None, error.message
    except ProviderFailure as error:
        output, failure = None, pack_failure_message(error)
    except Exception:
        output, failure = None, "The AI provider could not produce a supported improved draft. Retry."
    ai_usage.release(db, owner_id, token)
    if failure:
        db.commit()
        raise PackError(502, failure)
    pack.current_version += 1
    notes = [
        "Human review is required: valid references do not prove a claim is correct. "
        "Compare the improved draft with the captured CV.", *output.review_notes]
    improved = ApplicationPackVersion(pack_id=pack.id, number=pack.current_version,
                                      cv=store_generated(output.cv),
                                      cover_letter=store_generated(output.cover_letter),
                                      review_notes=notes)
    db.add(improved)
    db.add(ApplicationPackOperation(pack_id=pack.id, key=body.idempotency_key,
           request_hash=payload_hash, version_number=improved.number))
    db.commit()
    return pack, improved, notes


def options(db, owner_id, job_id, settings):
    owned_job(db, owner_id, job_id)
    model = settings.JOBPILOT_PACK_MODEL
    try:
        provider, model, _ = pack_provider_configuration(settings)
        available = True
    except SuggestionError:
        provider, available = "unknown", False
    reason = None if available else "AI generation is unavailable in this environment."
    profile = db.scalar(select(CandidateProfile).where(
        CandidateProfile.owner_id == owner_id).execution_options(populate_existing=True))
    has_profile = profile is not None and any(
        getattr(profile, name) for name in CandidateProfileUpdate.model_fields)
    description = db.scalar(select(SavedJob.description).where(
        SavedJob.id == job_id, SavedJob.owner_id == owner_id)) or ""
    has_description = bool((description or "").strip())
    rows = db.execute(select(Resume, ResumeExtraction).outerjoin(
        ResumeExtraction, ResumeExtraction.resume_id == Resume.id).where(Resume.owner_id == owner_id)).all()
    resumes = []
    for resume, extraction in rows:
        if extraction and extraction.status == "succeeded" and extraction.reviewed_at and (extraction.draft_text or "").strip():
            resumes.append({"id": str(resume.id), "display_name": resume.display_name,
                           "reviewed_at": extraction.reviewed_at.isoformat()})
    return {"provider": provider, "model": model, "available": available, "reason": reason, "resumes": resumes, "has_profile": has_profile, "has_description": has_description}


def list_versions(db, owner_id, job_id, pack_id, page, page_size):
    get_owned(db, owner_id, job_id, pack_id)
    query = select(ApplicationPackVersion).where(
        ApplicationPackVersion.pack_id == pack_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(ApplicationPackVersion.number.desc(
    ), ApplicationPackVersion.id.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [PackVersionResponse.model_validate(item) for item in items], "total": total, "page": page, "page_size": page_size}


def get_download_version(db, owner_id, job_id, pack_id, version_number):
    pack = get_owned(db, owner_id, job_id, pack_id)
    version = version_for(db, pack, version_number)
    if version.approved_at is None:
        raise PackError(409, "Approve this pack version before downloading.")
    return pack, version


def delete_pack(db, owner_id, job_id, pack_id):
    pack = get_owned(db, owner_id, job_id, pack_id)
    db.delete(pack)
    db.commit()


def list_packs(db, owner_id, job_id, page, page_size):
    owned_job(db, owner_id, job_id)
    query = select(ApplicationPack).where(
        ApplicationPack.owner_id == owner_id, ApplicationPack.job_id == job_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(ApplicationPack.created_at.desc(
    ), ApplicationPack.id.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [response(db, pack) for pack in items], "total": total, "page": page, "page_size": page_size}
