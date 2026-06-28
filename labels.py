"""Transparency label generation."""

from config import THRESHOLD_LIKELY_AI, THRESHOLD_LIKELY_HUMAN

LABEL_LIKELY_AI = (
    "**Likely AI-Generated** — Our multi-signal analysis indicates a high likelihood "
    "({confidence_pct}%) that this content was produced by artificial intelligence. "
    "This does not reflect on the creator's intent. If you believe this classification "
    "is wrong, the creator may submit an appeal for human review."
)

LABEL_LIKELY_HUMAN = (
    "**Likely Human-Written** — Our multi-signal analysis indicates a high likelihood "
    "({confidence_pct}%) that this content was written by the creator. "
    "No further action is needed unless new information arises."
)

LABEL_UNCERTAIN = (
    "**Attribution Uncertain** — We could not determine with confidence whether this "
    "content is human-written or AI-generated (confidence in AI attribution: "
    "{confidence_pct}%). The creator's stated attribution stands. Creators who believe "
    "they have been misclassified may submit an appeal."
)


def generate_label(confidence: float, attribution: str) -> str:
    """Return the transparency label text for a given confidence and attribution."""
    confidence_pct = int(round(confidence * 100))

    if attribution == "likely_ai":
        # For human label, show inverse confidence (confidence in human)
        return LABEL_LIKELY_AI.format(confidence_pct=confidence_pct)
    if attribution == "likely_human":
        human_pct = int(round((1 - confidence) * 100))
        return LABEL_LIKELY_HUMAN.format(confidence_pct=human_pct)
    return LABEL_UNCERTAIN.format(confidence_pct=confidence_pct)


def get_label_variant_name(attribution: str) -> str:
    """Return human-readable variant name for documentation."""
    mapping = {
        "likely_ai": "high-confidence AI",
        "likely_human": "high-confidence human",
        "uncertain": "uncertain",
    }
    return mapping.get(attribution, "unknown")
