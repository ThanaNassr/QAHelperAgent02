import json
import re
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for


BASE_DIR = Path(__file__).resolve().parent
CALLS_PATH = BASE_DIR / "data" / "candidate-calls.json"
DECISIONS_PATH = BASE_DIR / "decisions.json"

app = Flask(__name__)


def _read_calls_text() -> str:
    return CALLS_PATH.read_text(encoding="utf-8")


def _sanitize_line_number_prefixes(text: str) -> str:
    return re.sub(r"^\s*\d+\|\s*", "", text, flags=re.MULTILINE)


def load_calls() -> list[dict]:
    raw_text = _read_calls_text()
    try:
        calls = json.loads(raw_text)
    except json.JSONDecodeError:
        calls = json.loads(_sanitize_line_number_prefixes(raw_text))

    if not isinstance(calls, list):
        raise ValueError("candidate-calls.json must contain a JSON array")
    return calls


def load_decisions() -> dict[str, dict]:
    if not DECISIONS_PATH.exists():
        return {}

    try:
        data = json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    decisions_by_call_id: dict[str, dict] = {}
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("call_id"):
                decisions_by_call_id[item["call_id"]] = item
    elif isinstance(data, dict):
        # Backward compatibility if file is ever stored as a map.
        for key, value in data.items():
            if isinstance(value, dict):
                decisions_by_call_id[key] = value
    return decisions_by_call_id


def save_decision(call_id: str, call_date: str, decision: str, note: str) -> None:
    decisions = load_decisions()
    decisions[call_id] = {
        "call_id": call_id,
        "call_date": call_date,
        "decision": decision,
        "note": note,
    }
    ordered = sorted(decisions.values(), key=lambda item: item["call_id"])
    DECISIONS_PATH.write_text(json.dumps(ordered, indent=2), encoding="utf-8")


def safe_index(index_value: str | None, calls_len: int) -> int:
    if calls_len == 0:
        return 0
    try:
        parsed = int(index_value or 0)
    except (TypeError, ValueError):
        parsed = 0
    return max(0, min(parsed, calls_len - 1))


def split_transcript(transcript: str) -> list[str]:
    return [line.strip() for line in transcript.splitlines() if line.strip()]


@app.route("/", methods=["GET"])
def review_call():
    calls = load_calls()
    if not calls:
        return "No calls found in data/candidate-calls.json", 404

    index = safe_index(request.args.get("index"), len(calls))
    call = calls[index]
    decisions = load_decisions()
    saved_decision = decisions.get(call["id"])

    return render_template(
        "review.html",
        call=call,
        turns=split_transcript(call.get("transcript", "")),
        index=index,
        total=len(calls),
        saved_decision=saved_decision,
        error=None,
    )


@app.route("/decision", methods=["POST"])
def submit_decision():
    calls = load_calls()
    if not calls:
        return redirect(url_for("review_call"))

    index = safe_index(request.form.get("index"), len(calls))
    call = calls[index]

    decision = (request.form.get("decision") or "").strip().lower()
    note = (request.form.get("note") or "").strip()

    if decision not in {"approve", "reject"}:
        return render_template(
            "review.html",
            call=call,
            turns=split_transcript(call.get("transcript", "")),
            index=index,
            total=len(calls),
            saved_decision={"decision": decision, "note": note},
            error="Please choose approve or reject.",
        )

    if decision == "reject" and not note:
        return render_template(
            "review.html",
            call=call,
            turns=split_transcript(call.get("transcript", "")),
            index=index,
            total=len(calls),
            saved_decision={"decision": decision, "note": note},
            error="A note is required when rejecting a summary.",
        )

    save_decision(call_id=call["id"], call_date=call["call_date"], decision=decision, note=note)
    return redirect(url_for("review_call", index=index))


if __name__ == "__main__":
    app.run(debug=True)
