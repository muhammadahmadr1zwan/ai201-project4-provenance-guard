# Provenance Guard

A backend API that classifies submitted text for AI vs. human attribution, scores confidence with honest uncertainty, surfaces transparency labels to readers, and provides an appeals path for contested classifications.

Built for creative sharing platforms that need attribution context without pretending detection is perfect.

---

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Mac/Linux

pip install -r requirements.txt

# Copy .env.example to .env and add your Groq API key
copy .env.example .env

python app.py
# Server runs at http://127.0.0.1:5000
```

### Example Requests

**Submit content for analysis:**

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "The sun dipped below the horizon...", "creator_id": "user-42"}' \
  | python -m json.tool
```

**Submit an appeal:**

```bash
curl -s -X POST http://localhost:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id": "PASTE-UUID-HERE", "creator_reasoning": "I wrote this myself."}' \
  | python -m json.tool
```

**View audit log:**

```bash
curl -s http://localhost:5000/log | python -m json.tool
```

---

## Architecture Overview

When a creator submits text via `POST /submit`, the request flows through these components:

1. **Flask API** — Validates JSON payload (`text`, `creator_id`), applies rate limiting.
2. **Signal 1: Groq LLM** — Sends text to `llama-3.3-70b-versatile` for holistic semantic/style assessment → `llm_score` (0–1).
3. **Signal 2: Stylometric Heuristics** — Computes sentence-length variance, type-token ratio, punctuation density, and word-length variance in pure Python → `style_score` (0–1).
4. **Confidence Scorer** — Weighted combination (60% LLM, 40% stylometric) with disagreement guard and human-bias adjustment → `confidence` (0–1).
5. **Label Generator** — Maps confidence to one of three transparency label variants.
6. **Audit Log (SQLite)** — Persists structured entry with all scores, label, and timestamp.
7. **JSON Response** — Returns `content_id`, `attribution`, `confidence`, `label`, and individual signal scores.

**Appeal flow:** `POST /appeal` with `content_id` + `creator_reasoning` → lookup original decision → update status to `under_review` → append appeal entry to audit log → return confirmation.

See [`planning.md`](planning.md) for the full architecture diagram.

---

## Detection Signals

### Signal 1: Groq LLM Classification

| | |
|---|---|
| **Measures** | Semantic and stylistic coherence — formulaic transitions, uniform tone, balanced hedging, lack of personal idiosyncrasy |
| **Output** | `llm_score` float [0, 1] — higher = more likely AI-generated |
| **Why chosen** | Captures holistic "feel" of text that statistical methods miss; detects polished AI prose even when structure looks normal |
| **Blind spot** | Professional human copywriting, non-native formal English, and heavily edited prose can read as "AI-like." Adversarially paraphrased AI text may evade detection |

### Signal 2: Stylometric Heuristics

| | |
|---|---|
| **Measures** | Sentence-length variance, type-token ratio (vocabulary diversity), punctuation density, word-length variance |
| **Output** | `style_score` float [0, 1] — higher = more likely AI-generated (more structurally uniform) |
| **Why chosen** | Genuinely independent from semantic analysis; fast, free, no API dependency; catches mechanically uniform text the LLM might overlook |
| **Blind spot** | Minimalist poetry, repetitive lyrics, listicle-style writing, and technical documentation with consistent formatting score as "AI-like" despite being human |

These signals are **distinct**: one is semantic, one is structural. Their combination is more informative than either alone.

---

## Confidence Scoring

### Approach

```
base = 0.60 × llm_score + 0.40 × style_score
```

**Disagreement guard:** When signals differ by > 0.35:
- LLM ≥ 0.80 → trust semantic signal (polished AI may look structurally human)
- LLM < 0.45 → pull toward human side (false-positive protection)
- Otherwise → pull toward uncertain zone (0.5)

**Human-bias cap:** When LLM says human (< 0.45) but combined score > 0.55, cap at 0.65.

### Thresholds

| Confidence | Attribution | Label |
|------------|-------------|-------|
| ≥ 0.75 | `likely_ai` | High-confidence AI |
| 0.40 – 0.74 | `uncertain` | Uncertain |
| ≤ 0.39 | `likely_human` | High-confidence human |

A score of 0.51 and 0.95 produce **different labels** — we never force binary output.

### Validation

Tested against four anchor texts spanning the confidence range with the live Groq API (`llama-3.3-70b-versatile`). Scores vary meaningfully: clearly AI text scored **0.792**, clearly human text scored **0.119**, and borderline professional prose scored **0.667** (uncertain band). All three label variants were reachable in a single test run.

### Example Submissions (Live Groq API Results)

**High-confidence AI** (confidence = 0.792):

```json
{
  "attribution": "likely_ai",
  "confidence": 0.792,
  "label": "**Likely AI-Generated** — Our multi-signal analysis indicates a high likelihood (79%) that this content was produced by artificial intelligence...",
  "signals": {
    "llm_score": 0.9,
    "llm_reasoning": "The text exhibits formulaic transitions, uniform sentence structure, and overly polished prose...",
    "style_score": 0.265
  }
}
```

Text: *"Artificial intelligence represents a transformative paradigm shift… Furthermore, stakeholders across various sectors must collaborate…"*

**High-confidence human** (confidence = 0.119):

```json
{
  "attribution": "likely_human",
  "confidence": 0.119,
  "label": "**Likely Human-Written** — Our multi-signal analysis indicates a high likelihood (88%) that this content was written by the creator...",
  "signals": {
    "llm_score": 0.1,
    "llm_reasoning": "The text's use of colloquial expressions, informal tone, and personal opinions suggest a human-written review...",
    "style_score": 0.1475
  }
}
```

Text: *"ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it…"*

**Uncertain** (confidence = 0.667):

```json
{
  "attribution": "uncertain",
  "confidence": 0.6674,
  "label": "**Attribution Uncertain** — We could not determine with confidence whether this content is human-written or AI-generated (confidence in AI attribution: 67%)...",
  "signals": {
    "llm_score": 0.8,
    "llm_reasoning": "The text's polished and formulaic structure, lack of personal tone, and balanced hedging suggest a high likelihood of AI generation.",
    "style_score": 0.41
  }
}
```

Text: *"The implementation of machine learning requires careful consideration of data quality and model bias. Teams must balance innovation with responsible deployment practices…"*

---

## Transparency Labels

Exact text displayed for each variant (also shown as quoted strings below):

| Variant | Exact Label Text |
|---------|-----------------|
| **High-confidence AI** | **Likely AI-Generated** — Our multi-signal analysis indicates a high likelihood ({confidence_pct}%) that this content was produced by artificial intelligence. This does not reflect on the creator's intent. If you believe this classification is wrong, the creator may submit an appeal for human review. |
| **High-confidence human** | **Likely Human-Written** — Our multi-signal analysis indicates a high likelihood ({confidence_pct}%) that this content was written by the creator. No further action is needed unless new information arises. |
| **Uncertain** | **Attribution Uncertain** — We could not determine with confidence whether this content is human-written or AI-generated (confidence in AI attribution: {confidence_pct}%). The creator's stated attribution stands. Creators who believe they have been misclassified may submit an appeal. |

**Rendered examples from live API responses (labels differ in both wording and meaning, not just the number):**

> **Likely AI-Generated** — Our multi-signal analysis indicates a high likelihood (79%) that this content was produced by artificial intelligence. This does not reflect on the creator's intent. If you believe this classification is wrong, the creator may submit an appeal for human review.

> **Likely Human-Written** — Our multi-signal analysis indicates a high likelihood (88%) that this content was written by the creator. No further action is needed unless new information arises.

> **Attribution Uncertain** — We could not determine with confidence whether this content is human-written or AI-generated (confidence in AI attribution: 67%). The creator's stated attribution stands. Creators who believe they have been misclassified may submit an appeal.

> `{confidence_pct}` is replaced at runtime. For human labels, the percentage reflects confidence in *human* authorship (i.e., `100 - AI confidence`).

---

## Rate Limiting

**Limits:** `10 per minute; 100 per day` on `POST /submit`

**Reasoning:**
- **10/minute:** A writer submitting their own work might paste 2–3 pieces in quick succession during an editing session. Ten per minute accommodates legitimate burst usage while blocking scripted flooding (an adversary sending hundreds of requests).
- **100/day:** Even prolific creators rarely submit more than 20–30 pieces daily. One hundred provides generous headroom for power users and platform integrations while capping sustained abuse from a single IP.

**Evidence** (12 rapid requests after 3 prior submissions in the same minute window — 10/minute cap):

```
200
200
200
200
200
200
200
429
429
429
429
429
```

First 7 succeeded (3 prior + 7 = 10/minute limit); requests 8–12 returned HTTP 429 Too Many Requests.

---

## Audit Log

Every classification and appeal is stored in SQLite with structured JSON payloads. Retrieve via `GET /log`.

**Sample entries** (from live Groq API testing):

```json
{
  "entries": [
    {
      "entry_type": "appeal",
      "content_id": "f592b0bf-bed7-4e9c-917e-fb9c20380ff4",
      "creator_id": "demo-human",
      "timestamp": "2026-06-28T22:45:53.382375+00:00",
      "status": "under_review",
      "appeal_reasoning": "I wrote this ramen review myself after visiting the restaurant last weekend. My casual writing style is just how I text friends.",
      "original_attribution": "likely_human",
      "original_confidence": 0.119,
      "original_llm_score": 0.1,
      "original_style_score": 0.1475
    },
    {
      "content_id": "1c2470b6-2a64-45b0-9683-9daa5ed47a11",
      "creator_id": "demo-ai",
      "timestamp": "2026-06-28T22:45:52.089218+00:00",
      "attribution": "likely_ai",
      "confidence": 0.792,
      "llm_score": 0.9,
      "style_score": 0.265,
      "status": "classified"
    },
    {
      "content_id": "f592b0bf-bed7-4e9c-917e-fb9c20380ff4",
      "creator_id": "demo-human",
      "timestamp": "2026-06-28T22:45:52.723627+00:00",
      "attribution": "likely_human",
      "confidence": 0.119,
      "llm_score": 0.1,
      "style_score": 0.1475,
      "status": "classified"
    }
  ]
}
```

The appeal entry references the original classification (same `content_id`) with `original_confidence`, `original_llm_score`, and `original_style_score` preserved alongside the creator's reasoning.

---

## Appeals Workflow

Creators contest a classification via `POST /appeal`:

```json
{
  "content_id": "uuid-from-submit-response",
  "creator_reasoning": "Free-text explanation of why the classification is wrong"
}
```

The system:
1. Looks up the original classification by `content_id`
2. Updates status from `classified` → `under_review`
3. Logs the appeal with original scores, label, and creator reasoning
4. Returns confirmation — no automated re-classification (human reviewer would adjudicate)

---

## Known Limitations

**Formal academic human prose** is the primary misclassification risk. A human economist writing *"Furthermore, central banks face a fundamental tension between their mandate for price stability and the unintended consequences of prolonged low interest rates…"* triggers both the LLM signal (reads polished and formulaic) and stylometrics (uniform sentence structure). The system may assign `uncertain` or even `likely_ai` to genuinely human professional writing. Our human-bias cap and uncertain label reflect this asymmetry — a false positive is worse than a false negative on a writing platform — but perfect detection remains unsolved.

Secondary limitations: non-English text, very short submissions (< 50 words), and minimalist poetry with repetitive structure.

---

## Spec Reflection

**How the spec helped:** The spec's emphasis on designing confidence scoring *before* implementation forced me to define what 0.5 means to a user (uncertain, creator's attribution stands) before writing code. This prevented the common trap of treating confidence as a raw model output rather than a calibrated communication tool. The false-positive asymmetry hint directly shaped the human-bias cap and disagreement guard.

**Where implementation diverged:** The spec suggested a simple disagreement guard pulling all conflicting signals toward 0.5. In testing, this caused clearly AI-generated text (LLM = 0.88) to land in the uncertain band because stylometrics scored it as structurally human (0.265). I added a conditional rule: when the LLM is strongly confident (≥ 0.80) but stylometrics disagree, trust the LLM more heavily. This better reflects that polished AI prose is the stylometric signal's blind spot, not evidence of human authorship.

---

## AI Usage

### Instance 1: Flask app skeleton and first signal (Milestone 3)

**Directed:** Provided the detection signals section and architecture diagram from `planning.md` and asked for a Flask app skeleton with `POST /submit`, Groq LLM signal function, and SQLite audit log.

**Produced:** A monolithic `app.py` with inline Groq calls and print-based logging.

**Revised:** Split into modular files (`signals/llm_signal.py`, `audit_log.py`, `app.py`). Replaced print logging with structured SQLite JSON payloads. Added a heuristic fallback when no API key is configured so stylometric testing works offline.

### Instance 2: Confidence scoring and production layer (Milestones 4–5)

**Directed:** Provided uncertainty representation, label variants, and appeals workflow sections; asked for stylometric signal, scoring logic, label generator, and appeal endpoint.

**Produced:** A symmetric weighted average with a single disagreement guard pulling all conflicts toward 0.5.

**Revised:** Replaced with asymmetric guards — human-bias cap when LLM says human, LLM-trust boost when LLM ≥ 0.80, and separate threshold bands. Tested against four anchor texts and adjusted until clearly AI (0.77) vs. clearly human (0.15) produced meaningfully different labels. Verified all three label variants are reachable.

---

## Project Structure

```
ai201-project4-provenance-guard/
├── app.py                  # Flask routes
├── audit_log.py            # SQLite audit log
├── config.py               # Thresholds, weights, rate limits
├── labels.py               # Transparency label generation
├── scoring.py              # Confidence scoring logic
├── signals/
│   ├── llm_signal.py       # Groq LLM detection
│   └── stylometric.py      # Structural heuristics
├── planning.md             # Architecture spec (pre-implementation)
├── requirements.txt
├── .env.example
└── README.md
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| POST | `/submit` | Submit text for attribution analysis |
| POST | `/appeal` | Contest a classification |
| GET | `/log` | Retrieve audit log entries |
| GET | `/health` | Health check |
