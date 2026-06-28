"""Provenance Guard — Flask application."""

import uuid

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import audit_log
from config import RATE_LIMIT_SUBMIT
from labels import generate_label
from scoring import compute_confidence, map_attribution
from signals.llm_signal import analyze_llm
from signals.stylometric import analyze_stylometric

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

audit_log.init_db()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/submit", methods=["POST"])
@limiter.limit(RATE_LIMIT_SUBMIT)
def submit():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    text = data.get("text", "").strip()
    creator_id = data.get("creator_id", "").strip()

    if not text:
        return jsonify({"error": "Field 'text' is required and must be non-empty"}), 400
    if not creator_id:
        return jsonify({"error": "Field 'creator_id' is required"}), 400

    llm_score, llm_reasoning = analyze_llm(text)
    style_score, style_metrics = analyze_stylometric(text)
    confidence = compute_confidence(llm_score, style_score)
    attribution = map_attribution(confidence)
    label = generate_label(confidence, attribution)
    content_id = str(uuid.uuid4())

    audit_log.save_submission(
        content_id=content_id,
        creator_id=creator_id,
        text=text,
        attribution=attribution,
        confidence=confidence,
        llm_score=llm_score,
        style_score=style_score,
        label=label,
    )

    return jsonify(
        {
            "content_id": content_id,
            "attribution": attribution,
            "confidence": confidence,
            "label": label,
            "status": "classified",
            "signals": {
                "llm_score": round(llm_score, 4),
                "llm_reasoning": llm_reasoning,
                "style_score": round(style_score, 4),
                "style_metrics": style_metrics,
            },
        }
    )


@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    content_id = data.get("content_id", "").strip()
    creator_reasoning = data.get("creator_reasoning", "").strip()

    if not content_id:
        return jsonify({"error": "Field 'content_id' is required"}), 400
    if not creator_reasoning:
        return jsonify({"error": "Field 'creator_reasoning' is required"}), 400

    submission = audit_log.get_submission(content_id)
    if submission is None:
        return jsonify({"error": f"No submission found for content_id '{content_id}'"}), 404

    if submission["status"] == "under_review":
        return jsonify(
            {
                "content_id": content_id,
                "status": "under_review",
                "message": "An appeal is already under review for this content.",
            }
        )

    appeal_entry = audit_log.save_appeal(content_id, creator_reasoning)

    return jsonify(
        {
            "content_id": content_id,
            "status": "under_review",
            "message": "Your appeal has been received and is under review.",
            "appeal": {
                "timestamp": appeal_entry["timestamp"],
                "creator_reasoning": creator_reasoning,
                "original_attribution": appeal_entry["original_attribution"],
                "original_confidence": appeal_entry["original_confidence"],
            },
        }
    )


@app.route("/log", methods=["GET"])
def get_log():
    limit = request.args.get("limit", 50, type=int)
    limit = max(1, min(limit, 200))
    entries = audit_log.get_log_entries(limit=limit)
    return jsonify({"entries": entries, "count": len(entries)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
