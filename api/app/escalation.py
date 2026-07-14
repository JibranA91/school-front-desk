"""Deterministic escalation layer that sits on top of the agent's answer.

Sensitive categories ALWAYS escalate, regardless of how confident the model is
or whether an answer exists — this is the "escalate rather than guess" guarantee
from the spec, enforced in code rather than left to the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Sensitive categories → trigger keywords. Order matters (first match wins).
SENSITIVE_CATEGORIES: dict[str, list[str]] = {
    "health": [
        "fever", "sick", "temperature", "vomit", "throw up", "threw up", "rash",
        "cough", "flu", "covid", "contagious", "diarrhea", "pink eye", "lice",
        "ill", "illness",
    ],
    "medication": [
        "medication", "medicine", "dose", "dosage", "tylenol", "ibuprofen",
        "antibiotic", "inhaler", "prescription",
    ],
    "allergy": [
        "allergy", "allergies", "allergic", "peanut", "nut allergy", "dairy",
        "gluten", "anaphyla",
    ],
    "safety": [
        "injury", "injured", "hurt", "fell", "fall", "accident", "bleeding",
        "emergency", "choking", "bruise", "concussion",
    ],
    "billing_dispute": [
        "refund", "overcharge", "overcharged", "charged twice", "billing error",
        "dispute", "waive", "can't pay", "cant pay", "payment plan",
    ],
    "custody": [
        "custody", "court order", "restraining", "legal", "divorce",
        "not allowed to pick", "pickup authorization", "authorized to pick",
    ],
}

# Keywords match at a word boundary and may extend to the rest of the word, so a
# base form also catches its inflections ("fever"→"feverish", "cough"→"coughing",
# "ill"→…). A few SHORT keywords are prefixes of unrelated common words, so they
# match as WHOLE WORDS only — otherwise "ill" fires on "will", "lice" on
# "licensed", "fell" on "fellow", "flu" on "fluid", "fall" on "waterfall". This
# is why substring matching mis-escalated "what will be for lunch tomorrow?".
_WHOLE_WORD_ONLY = {"ill", "flu", "lice", "fell", "fall"}

# Below this confidence, a non-sensitive answer is treated as a low-confidence gap.
CONFIDENCE_THRESHOLD = 0.35


def _keyword_pattern(kw: str) -> str:
    body = re.escape(kw)
    # Whole-word for the ambiguous short ones; word-prefix for everything else.
    return rf"\b{body}\b" if kw in _WHOLE_WORD_ONLY else rf"\b{body}\w*"


# Compile one regex per category (dict preserves order → first match still wins).
_CATEGORY_PATTERNS: dict[str, re.Pattern[str]] = {
    category: re.compile("|".join(_keyword_pattern(kw) for kw in keywords), re.IGNORECASE)
    for category, keywords in SENSITIVE_CATEGORIES.items()
}


def classify_sensitive(text: str) -> str | None:
    for category, pattern in _CATEGORY_PATTERNS.items():
        if pattern.search(text):
            return category
    return None


@dataclass
class Decision:
    needs_escalation: bool
    status: str  # "answered" | "escalated" | "lowconf"
    category: str | None
    reason: str | None


def decide(text: str, confidence: float, citations: list[str]) -> Decision:
    sensitive = classify_sensitive(text)
    if sensitive is not None:
        return Decision(True, "escalated", sensitive, f"sensitive:{sensitive}")
    if not citations:
        return Decision(True, "escalated", None, "knowledge-gap")
    if confidence < CONFIDENCE_THRESHOLD:
        return Decision(True, "lowconf", None, "low-confidence")
    return Decision(False, "answered", None, None)
