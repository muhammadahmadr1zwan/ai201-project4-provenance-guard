"""Application configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "provenance_guard.db"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

# Confidence thresholds (score = probability of AI generation)
THRESHOLD_LIKELY_AI = 0.75
THRESHOLD_LIKELY_HUMAN = 0.39

# Signal weights
LLM_WEIGHT = 0.60
STYLE_WEIGHT = 0.40

# Rate limits applied to POST /submit
RATE_LIMIT_SUBMIT = "10 per minute;100 per day"
