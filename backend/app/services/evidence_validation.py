"""Conservative local claim checks. Passing is not a semantic truth guarantee.

Unsupported content fails closed; users can still author their own draft edits.
Numbers must match cited evidence exactly, and experience claims must be supported
within one cited passage to avoid inventing relationships by combining sources.
"""
import re
import unicodedata
from pydantic import BaseModel

WORD = re.compile(r"[^\W_]+(?:[+#.-][^\W_]+)*", re.UNICODE)
NUMBER = re.compile(r"(?<!\w)\d+(?:[.,]\d+)*(?:%|\+)?")
GRAMMAR = set("a an the and or of to in on at for from with by as is are was were be been being i my me we our your it its this that these those have has had do does did can will would am background includes include including skills skill experience education summary contact languages language degree company role title location start end date present current year years month months worked work working responsible responsibility responsibilities professional career application dear hiring team sincerely regards interested interest applying opportunity position contribute contribution".split())
GRAMMAR -= {"experience", "year", "years", "month", "months", "worked", "work", "working",
            "responsible", "responsibility", "responsibilities", "degree", "professional"}


def normalize(text):
    return unicodedata.normalize("NFKC", str(text)).casefold()


def terms(text):
    return set(WORD.findall(normalize(text))) - GRAMMAR


def supported_claim(text, passages, *, single_passage=False):
    passages = [str(p) for p in passages if p and str(p).strip()]
    if not passages:
        return False
    claim = terms(text)
    evidence = set().union(*(terms(p) for p in passages))
    if not claim or not claim <= evidence:
        return False
    if not set(NUMBER.findall(normalize(text))) <= set(NUMBER.findall(normalize("\n".join(passages)))):
        return False
    # Each citation must contribute content; an authentic but unrelated quote
    # cannot be used as decoration for an otherwise unsupported claim.
    if any(not claim.intersection(terms(p)) for p in passages):
        return False
    # Do not turn an explicit absence into a positive experience claim.
    negation = {"no", "not", "never", "without"}
    if any(terms(p) & negation for p in passages) and not claim & negation:
        return False
    if single_passage or re.search(r"\b(worked|led|built|managed|developed|engineer|manager|employer|company|experience)\b", normalize(text)):
        if not any(claim <= terms(p) for p in passages):
            return False
    return True


def value_text(value):
    if isinstance(value, BaseModel):
        value = value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        return " ".join(value_text(v) for v in value.values() if v is not None)
    if isinstance(value, list):
        return " ".join(value_text(v) for v in value)
    return str(value)
