"""Deterministic escalation layer that sits on top of the agent's answer.

Sensitive categories ALWAYS escalate, regardless of how confident the model is
or whether an answer exists — this is the "escalate rather than guess" guarantee
from the spec, enforced in code rather than left to the model.
"""

from __future__ import annotations

from dataclasses import dataclass

# Sensitive categories → trigger keywords. Order matters (first match wins).
SENSITIVE_CATEGORIES: dict[str, list[str]] = {
    "health": [
        "fever", "sick", "temperature", "vomit", "throw up", "threw up", "rash",
        "cough", "flu", "covid", "contagious", "diarrhea", "pink eye", "lice", "ill",
    ],
    "medication": [
        "medication", "medicine", "dose", "dosage", "tylenol", "ibuprofen",
        "antibiotic", "inhaler", "prescription",
    ],
    "allergy": ["allergy", "allergic", "peanut", "nut allergy", "dairy", "gluten", "anaphyla"],
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

# Below this confidence, a non-sensitive answer is treated as a low-confidence gap.
CONFIDENCE_THRESHOLD = 0.35


def classify_sensitive(text: str) -> str | None:
    t = text.lower()
    for category, keywords in SENSITIVE_CATEGORIES.items():
        if any(kw in t for kw in keywords):
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
