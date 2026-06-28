# Provenance Guard — Planning Document

## Problem Statement

Creative sharing platforms need a backend service that classifies submitted text for AI vs. human attribution, communicates uncertainty honestly, surfaces transparency labels to readers, and gives creators a path to appeal misclassifications — without pretending detection is perfect.

---

## Architecture

### Narrative

When a creator submits text via `POST /submit`, the Flask API validates the payload, runs two independent detection signals in sequence (Groq LLM classification and stylometric heuristics), combines their scores into a calibrated confidence value, maps that score to one of three transparency label variants, persists the full decision to a SQLite audit log, and returns a structured JSON response. If a creator later contests the result, they call `POST /appeal` with their reasoning; the system updates the content status to `under_review`, appends the appeal to the audit log alongside the original decision, and returns confirmation. A reviewer (or grader) can inspect all decisions via `GET /log`.

### Diagram

```
SUBMISSION FLOW
===============

  Client                Flask API              Detection Pipeline           Storage
    |                       |                          |                        |
    |  POST /submit         |                          |                        |
    |  {text, creator_id}   |                          |                        |
    |---------------------->|                          |                        |
    |                       |  raw text                |                        |
    |                       |------------------------->|                        |
    |                       |                          |                        |
    |                       |              +-----------+-----------+            |
    |                       |              | Signal 1: Groq LLM    |            |
    |                       |              | (semantic/style)      |            |
    |                       |              | -> llm_score (0-1)    |            |
    |                       |              +-----------+-----------+            |
    |                       |                          |                        |
    |                       |              +-----------+-----------+            |
    |                       |              | Signal 2: Stylometric |            |
    |                       |              | (structural stats)    |            |
    |                       |              | -> style_score (0-1)  |            |
    |                       |              +-----------+-----------+            |
    |                       |                          |                        |
    |                       |              +-----------+-----------+            |
    |                       |              | Confidence Scorer     |            |
    |                       |              | -> confidence (0-1)   |            |
    |                       |              | -> attribution label  |            |
    |                       |              +-----------+-----------+            |
    |                       |                          |                        |
    |                       |              +-----------+-----------+            |
    |                       |              | Label Generator       |            |
    |                       |              | -> transparency text  |            |
    |                       |              +-----------+-----------+            |
    |                       |                          |                        |
    |                       |  structured entry        |                        |
    |                       |------------------------------------------------->|
    |                       |                          |              SQLite audit log
    |  JSON response        |                          |                        |
    |  {content_id,         |                          |                        |
    |   attribution,        |                          |                        |
    |   confidence, label}  |                          |                        |
    |<----------------------|                          |                        |


APPEAL FLOW
===========

  Client                Flask API              Storage
    |                       |                     |
    |  POST /appeal         |                     |
    |  {content_id,         |                     |
    |   creator_reasoning}  |                     |
    |---------------------->|                     |
    |                       |  lookup content_id  |
    |                       |-------------------->|
    |                       |  original decision  |
    |                       |<--------------------|
    |                       |  update status ->   |
    |                       |    "under_review"   |
    |                       |  append appeal log  |
    |                       |-------------------->|
    |  confirmation         |                     |
    |<----------------------|                     |
```

---

## Detection Signals

### Signal 1: Groq LLM Classification (llama-3.3-70b-versatile)

| Property | Detail |
|----------|--------|
| **Measures** | Holistic semantic and stylistic coherence — whether the text reads as naturally human-authored or exhibits patterns typical of LLM output (formulaic transitions, balanced hedging, uniform tone). |
| **Output** | `llm_score` float in [0, 1] — probability the text is AI-generated. Higher = more likely AI. |
| **Why it differs** | LLMs produce semantically coherent but stylistically "smooth" text; humans introduce idiosyncrasy, digression, and uneven polish. |
| **Blind spot** | Heavily edited human prose, professional copywriting, and non-native formal English can read as "AI-like" to an LLM judge. Adversarially rewritten AI text may evade detection. |

### Signal 2: Stylometric Heuristics (pure Python)

| Property | Detail |
|----------|--------|
| **Measures** | Structural statistical properties: sentence-length variance, type-token ratio (vocabulary diversity), punctuation density, and word-length variance. |
| **Output** | `style_score` float in [0, 1] — probability the text is AI-generated based on structural uniformity. |
| **Why it differs** | AI text tends toward uniform sentence lengths, moderate vocabulary diversity, and consistent punctuation patterns. Human writing is more variable — short fragments mixed with long sentences, slang, irregular punctuation. |
| **Blind spot** | Deliberately minimalist poetry, repetitive song lyrics, or listicle-style writing with uniform structure will score as "AI-like" despite being human. Technical documentation with consistent formatting also triggers false positives. |

### Combination Formula

```
base_confidence = 0.60 * llm_score + 0.40 * style_score

# False-positive guard: if signals disagree by > 0.35, adjust based on which signal dominates
disagreement = abs(llm_score - style_score)
if disagreement > 0.35:
    if llm_score >= 0.80:
        base_confidence = base_confidence * 0.85 + llm_score * 0.15  # trust strong LLM signal
    elif llm_score < 0.45:
        base_confidence = base_confidence * 0.65 + 0.35 * 0.35  # favor human side
    else:
        base_confidence = base_confidence * 0.7 + 0.5 * 0.3  # pull toward uncertain

# Human-bias adjustment: when base is borderline-high but LLM says human (< 0.45),
# cap confidence at 0.65 to avoid harsh AI labels on likely-human text
if llm_score < 0.45 and base_confidence > 0.55:
    base_confidence = min(base_confidence, 0.65)

# LLM-trust boost: polished AI prose may look structurally human
if llm_score >= 0.80 and style_score < 0.40:
    base_confidence = max(base_confidence, llm_score * 0.88)
```

---

## Uncertainty Representation

| Score Range | Meaning | Attribution | Label Variant |
|-------------|---------|-------------|---------------|
| 0.00 – 0.39 | High-confidence human | `likely_human` | Human label |
| 0.40 – 0.74 | Uncertain | `uncertain` | Uncertain label |
| 0.75 – 1.00 | High-confidence AI | `likely_ai` | AI label |

**What 0.6 means:** The system leans slightly toward AI-generated but lacks conviction. A reader sees the "Uncertain" label — the creator's attribution stands, and an appeal path is offered. We deliberately avoid presenting 0.51 and 0.95 identically.

**Calibration approach:** Tested against four anchor texts (clearly AI, clearly human, formal human, lightly edited AI). Verified that scores span the full range and that borderline cases land in the uncertain band.

---

## Transparency Label Design

### High-Confidence AI (confidence ≥ 0.75)

> **Likely AI-Generated** — Our multi-signal analysis indicates a high likelihood ({confidence_pct}%) that this content was produced by artificial intelligence. This does not reflect on the creator's intent. If you believe this classification is wrong, the creator may submit an appeal for human review.

### High-Confidence Human (confidence ≤ 0.39)

> **Likely Human-Written** — Our multi-signal analysis indicates a high likelihood ({confidence_pct}%) that this content was written by the creator. No further action is needed unless new information arises.

### Uncertain (confidence 0.40 – 0.74)

> **Attribution Uncertain** — We could not determine with confidence whether this content is human-written or AI-generated (confidence in AI attribution: {confidence_pct}%). The creator's stated attribution stands. Creators who believe they have been misclassified may submit an appeal.

Note: `{confidence_pct}` is replaced with the rounded percentage at response time.

---

## Appeals Workflow

| Step | Detail |
|------|--------|
| **Who** | The original creator (identified by `creator_id` at submission time). No auth layer in this prototype — any client with a valid `content_id` may appeal. |
| **Input** | `content_id` (UUID from `/submit` response) + `creator_reasoning` (free text explaining why the classification is wrong). |
| **System actions** | 1) Look up original classification entry. 2) Update content status from `classified` → `under_review`. 3) Write a new audit log entry of type `appeal` linking to the original `content_id`, storing the reasoning and timestamp. 4) Return confirmation with updated status. |
| **Reviewer view** | A human reviewer opening the appeal queue (via `GET /log` filtered by status) would see: original text snippet, both signal scores, combined confidence, original label, appeal reasoning, and timestamp. They would manually re-adjudicate — automated re-classification is out of scope. |

---

## Anticipated Edge Cases

1. **Minimalist poetry with repetition** — A poem like "the sea / the sea / the sea / returns" has low sentence-length variance and low type-token ratio. Stylometric signal will score it as AI-like even though it is human. Mitigation: disagreement guard pulls score toward uncertain; appeal path available.

2. **Professional/academic human prose** — Formal writing with balanced structure ("Furthermore… It is important to note…") triggers both the LLM signal (reads polished) and stylometrics (uniform sentences). A human economist's blog post may land in the uncertain or even likely-AI band. This is the primary false-positive scenario; our human-bias cap and uncertain label reflect that asymmetry.

3. **Very short submissions** (< 50 words) — Insufficient text for reliable stylometric measurement. System still processes but confidence should naturally be lower due to high variance in small samples.

4. **Non-English text** — Groq prompt assumes English; stylometric baselines are English-calibrated. Non-English content will produce unreliable scores.

---

## API Surface

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/submit` | `{ "text": string, "creator_id": string }` | `{ content_id, attribution, confidence, label, signals: { llm_score, style_score }, status }` |
| POST | `/appeal` | `{ "content_id": string, "creator_reasoning": string }` | `{ content_id, status, message }` |
| GET | `/log` | — (optional `?limit=N`) | `{ entries: [...] }` |
| GET | `/health` | — | `{ status: "ok" }` |

---

## AI Tool Plan

### M3 — Submission Endpoint + First Signal

- **Spec sections provided:** Detection Signals (Signal 1), Architecture diagram, API Surface.
- **Request:** Flask app skeleton with `POST /submit`, Groq LLM signal function, SQLite audit log init, `GET /log` stub.
- **Verification:** curl POST with sample text returns `content_id` + `llm_score`; GET /log shows structured entry.

### M4 — Second Signal + Confidence Scoring

- **Spec sections provided:** Detection Signals (Signal 2), Uncertainty Representation, combination formula, Architecture diagram.
- **Request:** Stylometric signal function, confidence scorer, label attribution mapper.
- **Verification:** Run four anchor texts; confirm scores span range and clearly AI ≠ clearly human.

### M5 — Production Layer

- **Spec sections provided:** Transparency Label Design, Appeals Workflow, Architecture diagram.
- **Request:** Label generator with three variants, `POST /appeal` endpoint, Flask-Limiter on `/submit`.
- **Verification:** All three label variants reachable; appeal updates status in log; rate limit returns 429 after 10 rapid requests.

---

## Stretch Features

*(Not implemented in initial release — update this section before starting any stretch work.)*
