"""Confidence scoring and attribution mapping."""

from config import (
    LLM_WEIGHT,
    STYLE_WEIGHT,
    THRESHOLD_LIKELY_AI,
    THRESHOLD_LIKELY_HUMAN,
)


def compute_confidence(llm_score: float, style_score: float) -> float:
    """
    Combine signal scores into a single AI-likelihood confidence.

    Applies disagreement guard and human-bias adjustment to reduce false positives.
    When the LLM is strongly confident, it weighs more heavily than stylometrics.
    """
    base = LLM_WEIGHT * llm_score + STYLE_WEIGHT * style_score

    disagreement = abs(llm_score - style_score)
    if disagreement > 0.35:
        if llm_score >= 0.80:
            # Strong LLM signal — trust semantic analysis over structural mismatch
            base = base * 0.85 + llm_score * 0.15
        elif llm_score < 0.45:
            # LLM says human — pull toward human side to reduce false positives
            base = base * 0.65 + 0.35 * 0.35
        else:
            base = base * 0.7 + 0.5 * 0.3

    if llm_score >= 0.80 and style_score < 0.40:
        # Polished AI prose may look structurally human; trust strong LLM signal
        base = max(base, llm_score * 0.88)

    if llm_score < 0.45 and base > 0.55:
        base = min(base, 0.65)

    return round(max(0.0, min(1.0, base)), 4)


def map_attribution(confidence: float) -> str:
    """Map confidence score to attribution category."""
    if confidence >= THRESHOLD_LIKELY_AI:
        return "likely_ai"
    if confidence <= THRESHOLD_LIKELY_HUMAN:
        return "likely_human"
    return "uncertain"
