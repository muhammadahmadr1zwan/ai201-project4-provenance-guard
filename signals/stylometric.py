"""Stylometric heuristic detection signal (pure Python)."""

import math
import re
import statistics


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"[.!?]+", text)
    return [s.strip() for s in parts if s.strip()]


def _tokenize_words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def _sentence_length_variance_score(sentences: list[str]) -> float:
    """Low variance -> more AI-like -> higher score."""
    if len(sentences) < 2:
        return 0.5

    lengths = [len(s.split()) for s in sentences]
    mean_len = statistics.mean(lengths)
    if mean_len == 0:
        return 0.5

    try:
        stdev = statistics.stdev(lengths)
    except statistics.StatisticsError:
        return 0.5

    cv = stdev / mean_len  # coefficient of variation
    # Human writing typically has CV > 0.4; AI often < 0.25
    if cv >= 0.55:
        return 0.1
    if cv >= 0.35:
        return 0.35
    if cv >= 0.20:
        return 0.6
    return 0.85


def _type_token_ratio_score(words: list[str]) -> float:
    """Low TTR -> repetitive vocabulary -> more AI-like."""
    if len(words) < 5:
        return 0.5

    ttr = len(set(words)) / len(words)
    if ttr >= 0.75:
        return 0.15
    if ttr >= 0.55:
        return 0.4
    if ttr >= 0.40:
        return 0.65
    return 0.85


def _punctuation_density_score(text: str) -> float:
    """Very regular or very sparse punctuation patterns."""
    if not text:
        return 0.5

    punct_count = len(re.findall(r"[,;:\-—()\"']", text))
    density = punct_count / max(len(text), 1) * 100

    # AI tends toward moderate, consistent punctuation density (~2-4 per 100 chars)
    if 1.5 <= density <= 4.5:
        return 0.7
    if density < 0.5 or density > 8:
        return 0.25  # human irregularity
    return 0.45


def _word_length_variance_score(words: list[str]) -> float:
    """Uniform word lengths -> more AI-like."""
    if len(words) < 5:
        return 0.5

    lengths = [len(w) for w in words]
    mean_len = statistics.mean(lengths)
    if mean_len == 0:
        return 0.5

    try:
        cv = statistics.stdev(lengths) / mean_len
    except statistics.StatisticsError:
        return 0.5

    if cv >= 0.45:
        return 0.15
    if cv >= 0.30:
        return 0.4
    return 0.75


def analyze_stylometric(text: str) -> tuple[float, dict[str, float]]:
    """
    Compute stylometric AI-likelihood score.

    Returns:
        (style_score, metrics) where style_score is in [0, 1], higher = more likely AI.
    """
    sentences = _split_sentences(text)
    words = _tokenize_words(text)

    slv = _sentence_length_variance_score(sentences)
    ttr = _type_token_ratio_score(words)
    punct = _punctuation_density_score(text)
    wlv = _word_length_variance_score(words)

    metrics = {
        "sentence_length_variance": round(slv, 4),
        "type_token_ratio": round(ttr, 4),
        "punctuation_density": round(punct, 4),
        "word_length_variance": round(wlv, 4),
    }

    # Weighted combination of sub-metrics
    style_score = 0.35 * slv + 0.30 * ttr + 0.15 * punct + 0.20 * wlv
    style_score = max(0.0, min(1.0, style_score))

    return style_score, metrics
