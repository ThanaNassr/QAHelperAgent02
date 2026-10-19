import json
import re
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for


BASE_DIR = Path(__file__).resolve().parent
CALLS_PATH = BASE_DIR / "data" / "candidate-calls.json"
DECISIONS_PATH = BASE_DIR / "decisions.json"
CRITERIA_PATH = BASE_DIR / "criteria.md"

app = Flask(__name__)

DEFAULT_SEVERITY_LABELS = {
    0: "No issue",
    1: "Very minor issue",
    2: "Minor issue",
    3: "Moderate issue",
    4: "Major issue (review recommended)",
    5: "Critical issue (approval must be blocked)",
}


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


def load_criteria_config() -> tuple[list[str], dict[int, str]]:
    if not CRITERIA_PATH.exists():
        return [], DEFAULT_SEVERITY_LABELS.copy()

    raw_text = CRITERIA_PATH.read_text(encoding="utf-8")
    text = _sanitize_line_number_prefixes(raw_text)
    lines = text.splitlines()

    criteria_items: list[str] = []
    scale_labels: dict[int, str] = {}
    section: str | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip().lower()
            if "severity" in heading and "scale" in heading:
                section = "scale"
            elif "criteria" in heading:
                section = "criteria"
            else:
                section = None
            continue

        scale_match = re.match(r"^([0-5])\s*[:\-–]\s*(.+)$", stripped)
        if scale_match and section == "scale":
            scale_labels[int(scale_match.group(1))] = scale_match.group(2).strip()
            continue

        bullet_match = re.match(r"^(?:[-*]|\d+[.)])\s+(.+)$", stripped)
        if bullet_match and section == "criteria":
            candidate = bullet_match.group(1).strip()
            if not re.match(r"^[0-5]\s*[:\-–]\s+", candidate):
                criteria_items.append(candidate)

    if not criteria_items:
        for line in lines:
            stripped = line.strip()
            bullet_match = re.match(r"^(?:[-*]|\d+[.)])\s+(.+)$", stripped)
            if not bullet_match:
                continue
            candidate = bullet_match.group(1).strip()
            if re.match(r"^[0-5]\s*[:\-–]\s+", candidate):
                continue
            criteria_items.append(candidate)

    labels = {level: scale_labels.get(level, DEFAULT_SEVERITY_LABELS[level]) for level in range(6)}
    return criteria_items, labels


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


def save_decision(call_id: str, call_date: str, decision: str, note: str, criteria: list[dict]) -> None:
    decisions = load_decisions()
    decisions[call_id] = {
        "call_id": call_id,
        "call_date": call_date,
        "decision": decision,
        "note": note,
        "criteria": criteria,
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


def parse_criteria_scores(criteria_items: list[str], form_data) -> tuple[list[dict], dict[str, int], bool, bool]:
    criteria_scores: list[dict] = []
    form_severity_values: dict[str, int] = {}
    has_severity_4 = False
    has_severity_5 = False

    for idx, item in enumerate(criteria_items):
        raw = (form_data.get(f"severity_{idx}") or "0").strip()
        try:
            severity = int(raw)
        except ValueError:
            severity = 0
        if severity < 0 or severity > 5:
            severity = 0

        form_severity_values[str(idx)] = severity
        criteria_scores.append({"item": item, "severity": severity})

        if severity == 4:
            has_severity_4 = True
        elif severity == 5:
            has_severity_5 = True

    return criteria_scores, form_severity_values, has_severity_4, has_severity_5


@app.route("/", methods=["GET"])
def review_call():
    calls = load_calls()
    if not calls:
        return "No calls found in data/candidate-calls.json", 404

    index = safe_index(request.args.get("index"), len(calls))
    call = calls[index]
    decisions = load_decisions()
    previous_decision = decisions.get(call["id"])
    criteria_items, severity_labels = load_criteria_config()
    initial_form_severities = {str(idx): 0 for idx, _ in enumerate(criteria_items)}

    return render_template(
        "review.html",
        call=call,
        turns=split_transcript(call.get("transcript", "")),
        index=index,
        total=len(calls),
        previous_decision=previous_decision,
        form_state={"decision": "", "note": ""},
        criteria_items=criteria_items,
        severity_labels=severity_labels,
        form_severity_values=initial_form_severities,
        severity_message=None,
        severity_message_type=None,
        error=None,
    )


@app.route("/decision", methods=["POST"])
def submit_decision():
    calls = load_calls()
    if not calls:
        return redirect(url_for("review_call"))

    index = safe_index(request.form.get("index"), len(calls))
    call = calls[index]
    previous_decision = load_decisions().get(call["id"])
    criteria_items, severity_labels = load_criteria_config()
    criteria_scores, form_severity_values, has_severity_4, has_severity_5 = parse_criteria_scores(
        criteria_items, request.form
    )

    decision = (request.form.get("decision") or "").strip().lower()
    note = (request.form.get("note") or "").strip()
    severity_message = None
    severity_message_type = None

    if has_severity_5:
        severity_message = (
            "At least one criteria item is set to severity 5. "
            "Approve is blocked and this call should be escalated for review."
        )
        severity_message_type = "critical"
    elif has_severity_4:
        severity_message = (
            "At least one criteria item is set to severity 4. "
            "Please review carefully before deciding."
        )
        severity_message_type = "warning"

    if decision not in {"approve", "reject"}:
        return render_template(
            "review.html",
            call=call,
            turns=split_transcript(call.get("transcript", "")),
            index=index,
            total=len(calls),
            previous_decision=previous_decision,
            form_state={"decision": decision, "note": note},
            criteria_items=criteria_items,
            severity_labels=severity_labels,
            form_severity_values=form_severity_values,
            severity_message=severity_message,
            severity_message_type=severity_message_type,
            error="Please choose approve or reject.",
        )

    if decision == "reject" and not note:
        return render_template(
            "review.html",
            call=call,
            turns=split_transcript(call.get("transcript", "")),
            index=index,
            total=len(calls),
            previous_decision=previous_decision,
            form_state={"decision": decision, "note": note},
            criteria_items=criteria_items,
            severity_labels=severity_labels,
            form_severity_values=form_severity_values,
            severity_message=severity_message,
            severity_message_type=severity_message_type,
            error="A note is required when rejecting a summary.",
        )

    if decision == "approve" and has_severity_5:
        return render_template(
            "review.html",
            call=call,
            turns=split_transcript(call.get("transcript", "")),
            index=index,
            total=len(calls),
            previous_decision=previous_decision,
            form_state={"decision": decision, "note": note},
            criteria_items=criteria_items,
            severity_labels=severity_labels,
            form_severity_values=form_severity_values,
            severity_message=severity_message,
            severity_message_type=severity_message_type,
            error="Approve is blocked when any criteria item has severity 5.",
        )

    save_decision(
        call_id=call["id"],
        call_date=call["call_date"],
        decision=decision,
        note=note,
        criteria=criteria_scores,
    )
    return redirect(url_for("review_call", index=index))


if __name__ == "__main__":
    app.run(debug=True)
