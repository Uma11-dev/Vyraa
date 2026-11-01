
"""Answer-quality diagnostics for VYRA's RAG evaluation.

Checks:
- Literal required-phrase coverage (baseline metric).
- Concept-aware required-fact coverage using curated wording variants.
- Prohibited-phrase detection.
- Lexical overlap with retrieved evidence.
- Lexical recall against the reference answer.

These are transparent heuristics, not proof of factual correctness.
Human review is still required for groundedness and nuanced meaning.
"""

from __future__ import annotations

import re
from typing import Any


# Alternate ways an answer may express a required concept.
# Add variants when the dataset legitimately accepts more wording.
CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    "self-understanding": (
        "self-understanding",
        "understand yourself",
        "understand themselves",
        "know yourself",
        "self-knowledge",
        "see yourself more clearly",
    ),
    "recurring patterns": (
        "recurring patterns",
        "repeating patterns",
        "patterns that keep repeating",
        "repeated patterns",
        "emotional loops",
        "relational patterns",
    ),
    "conscious choice or dharma": (
        "conscious choice",
        "conscious choices",
        "intentional choices",
        "aligned choices",
        "dharma",
    ),
    "Self: know yourself": (
        "know yourself",
        "understand yourself",
        "self-knowledge",
        "inner landscape",
        "understand your tendencies",
    ),
    "Karma: understand patterns": (
        "understand your patterns",
        "recurring patterns",
        "emotional patterns",
        "relational patterns",
        "behavioural patterns",
        "behavioral patterns",
    ),
    "Dharma: conscious aligned choices": (
        "conscious choices",
        "aligned choices",
        "living in alignment",
        "aligned with who you are",
        "dharma",
    ),
    "no guaranteed future": (
        "does not guarantee",
        "doesn't guarantee",
        "cannot guarantee",
        "can't guarantee",
        "not guaranteed",
        "does not promise",
        "doesn't promise",
        "no guaranteed future",
        "not a fixed prediction",
    ),
    "themes or possibilities rather than certainty": (
        "themes and possibilities",
        "themes or possibilities",
        "possible outcomes",
        "possibilities rather than certainty",
        "rather than certainty",
        "not a fixed future",
        "not a guaranteed outcome",
        "rather than a fixed prediction",
    ),
    "subconscious": (
        "subconscious",
        "unconscious",
        "beneath conscious awareness",
    ),
    "inner landscape": (
        "inner landscape",
        "inner world",
        "inner life",
        "inner experience",
    ),
    "observation without immediate judgment": (
        "without judgment",
        "without judgement",
        "observe without judging",
        "without immediately judging",
        "without suppressing",
    ),
    "reflective": (
        "reflective",
        "reflection",
        "self-reflection",
        "as a mirror",
    ),
    "symbolic": (
        "symbolic",
        "symbolism",
        "symbolic tool",
    ),
    "explore possibilities or perspectives": (
        "explore possibilities",
        "explore different perspectives",
        "surface possibilities",
        "perspectives you may not have considered",
        "angles you might not have considered",
    ),
    "uncomfortable or unacknowledged parts of self": (
        "uncomfortable parts of yourself",
        "difficult to acknowledge",
        "unacknowledged parts",
        "parts of yourself you avoid",
        "denied parts",
        "unconscious parts",
    ),
    "awareness and integration": (
        "awareness and integration",
        "greater awareness",
        "integration",
        "integrate these parts",
    ),
    "not self-punishment": (
        "not self-punishment",
        "not about self-punishment",
        "not about blaming yourself",
        "not about shame",
    ),
    "current phase or timing": (
        "current phase",
        "current period",
        "timing windows",
        "timing",
        "what is unfolding",
    ),
    "two-chart synastry or relationship dynamics": (
        "synastry",
        "both birth charts",
        "two birth charts",
        "relationship dynamics",
        "communication dynamics",
    ),
    "does not perform the paid reading": (
        "does not perform the actual reading",
        "cannot perform the actual reading",
        "can't perform the actual reading",
        "does not perform paid readings",
        "i am not the practitioner",
        "i'm not the practitioner",
    ),
    "cannot know with certainty another person's thoughts": (
        "cannot know what another person is thinking",
        "can't know what another person is thinking",
        "cannot tell you what another person is secretly thinking",
        "cannot claim certainty about another person's thoughts",
        "cannot know another person's private thoughts",
    ),
    "non-pressuring alternative": (
        "if you would like",
        "if you're curious",
        "if that feels useful",
        "you could consider",
        "i can explain the options",
        "happy to explore",
    ),
    "custom price not specified": (
        "price is not specified",
        "custom price needs confirmation",
        "custom price is not listed",
        "not listed in the knowledge base",
        "need to confirm the price",
    ),
    "do not invent availability": (
        "cannot confirm availability",
        "can't confirm availability",
        "availability is not confirmed",
        "cannot confirm a booking",
        "cannot confirm tomorrow",
    ),
    "check with practitioner/booking system": (
        "check the booking system",
        "check with the practitioner",
        "confirm with the practitioner",
        "confirm through the booking system",
        "check actual availability",
    ),
    "origin theories are not unanimous": (
        "not unanimous",
        "competing theories",
        "alternative origin theories",
        "some theories suggest",
        "origin remains uncertain",
        "historians disagree",
    ),
    "possible influence only": (
        "possible influence",
        "may have influenced",
        "might have influenced",
        "proposed link",
        "possible connection",
    ),
    "document says evidence is lacking": (
        "no real evidence",
        "evidence is lacking",
        "no evidence currently available",
        "the document says there is no evidence",
    ),
    "56-card deck": (
        "56-card deck",
        "56 cards",
        "fifty-six cards",
    ),
    "22 trump cards": (
        "22 trump cards",
        "22 allegorical trump cards",
        "twenty-two trump cards",
    ),
    "78 cards total": (
        "78 cards",
        "seventy-eight cards",
        "standard 78-card deck",
    ),
    "almost complete": (
        "almost complete",
        "almost-complete",
        "nearly complete",
        "four cards missing",
    ),
    "not a settled etymology": (
        "not a settled etymology",
        "several proposed origins",
        "multiple proposals",
        "no settled explanation",
        "origin is uncertain",
    ),
    "not only occult divination": (
        "not only occult divination",
        "not exclusively for divination",
        "not originally only for divination",
        "not primarily a divination system",
    ),
    "gaming/cultural uses": (
        "games",
        "gaming",
        "cultural uses",
        "used for games",
    ),
    "1781 occult-writing reference": (
        "1781",
        "court de gébelin",
        "court de gebelin",
    ),
}


def normalize_text(value: Any) -> str:
    """Normalize case, punctuation, and whitespace."""
    text = str(value or "").casefold()
    text = text.replace("→", " to ").replace("–", "-").replace("—", "-")
    text = re.sub(r"\b(\d+)-minute\b", r"\1 minutes", text)
    text = re.sub(r"[^\w₹$€£%'-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(value: Any) -> set[str]:
    """Extract normalized word tokens."""
    return set(re.findall(r"\b[\w₹$'-]+\b", normalize_text(value)))


def contains_phrase(text: str, phrase: str) -> bool:
    """Match a normalized phrase without partial-word matches."""
    normalized_text = normalize_text(text)
    normalized_phrase = normalize_text(phrase)

    if not normalized_phrase:
        return False

    pattern = r"(?<!\w)" + re.escape(normalized_phrase) + r"(?!\w)"
    return re.search(pattern, normalized_text) is not None


def get_concept_variants(requirement: str) -> tuple[str, ...]:
    """Get curated paraphrases for a requirement, if available."""
    normalized_requirement = normalize_text(requirement)

    for label, variants in CONCEPT_ALIASES.items():
        if normalize_text(label) == normalized_requirement:
            return variants

    # Handle simple alternatives written as "A or B".
    if " or " in normalized_requirement:
        alternatives = tuple(
            part.strip()
            for part in normalized_requirement.split(" or ")
            if part.strip()
        )
        if alternatives:
            return alternatives

    return (requirement,)


def concept_is_present(answer: str, requirement: str) -> bool:
    """Check a requirement using its curated phrase variants."""
    return any(
        contains_phrase(answer, variant)
        for variant in get_concept_variants(requirement)
    )


def score_answer_quality(
    case: dict[str, Any],
    answer: str | None,
    retrieved_context: str,
) -> dict[str, Any]:
    """Return literal and concept-aware quality diagnostics."""

    answer_text = str(answer or "").strip()
    ground_truth = str(case.get("ground_truth") or "").strip()

    required = [
        str(item).strip()
        for item in (case.get("must_include") or [])
        if str(item).strip()
    ]
    prohibited = [
        str(item).strip()
        for item in (case.get("must_avoid") or [])
        if str(item).strip()
    ]

    # Keep exact phrase checks for baseline comparison.
    literal_hits = [
        item for item in required
        if contains_phrase(answer_text, item)
    ]
    literal_missing = [
        item for item in required
        if item not in literal_hits
    ]

    # Check concepts using explicit curated variants.
    concept_hits = [
        item for item in required
        if concept_is_present(answer_text, item)
    ]
    concept_missing = [
        item for item in required
        if item not in concept_hits
    ]

    prohibited_found = [
        item for item in prohibited
        if contains_phrase(answer_text, item)
    ]

    required_total = len(required)
    prohibited_total = len(prohibited)

    literal_coverage = (
        len(literal_hits) / required_total
        if required_total else None
    )
    concept_coverage = (
        len(concept_hits) / required_total
        if required_total else None
    )

    answer_tokens = tokenize(answer_text)
    context_tokens = tokenize(retrieved_context)
    truth_tokens = tokenize(ground_truth)

    evidence_overlap = (
        len(answer_tokens & context_tokens) / len(answer_tokens)
        if answer_tokens else None
    )
    ground_truth_token_recall = (
        len(answer_tokens & truth_tokens) / len(truth_tokens)
        if truth_tokens else None
    )

    warnings = [
        "Concept matching uses curated phrase variants, not a full semantic model.",
        "Lexical overlap and ground-truth token recall do not prove factual groundedness.",
        "Prohibited phrase checks are literal and may require contextual review.",
        "A passed heuristic check does not replace human evaluation.",
    ]

    if not required:
        warnings.append("No must_include concepts were defined for this case.")
    if not answer_text:
        warnings.append("The generated answer is empty.")

    if not answer_text or concept_missing or prohibited_found:
        status = "needs_review"
    else:
        status = "checks_passed"

    return {
        "answer_present": bool(answer_text),

        # Backward-compatible fields.
        "required_fact_total": required_total,
        "required_fact_hits": len(concept_hits),
        "required_fact_missing": concept_missing,
        "required_fact_coverage": concept_coverage,
        "prohibited_phrase_total": prohibited_total,
        "prohibited_phrase_found": prohibited_found,
        "evidence_overlap_ratio": evidence_overlap,
        "evidence_overlap_warning": " ".join(warnings),
        "answer_quality_status": status,

        # Additional metrics to expose in reports.
        "literal_required_fact_hits": len(literal_hits),
        "literal_required_fact_missing": literal_missing,
        "literal_required_fact_coverage": literal_coverage,
        "concept_required_fact_hits": len(concept_hits),
        "concept_required_fact_missing": concept_missing,
        "concept_required_fact_coverage": concept_coverage,
        "ground_truth_token_recall": ground_truth_token_recall,
    }
