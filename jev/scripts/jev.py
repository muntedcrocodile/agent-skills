#!/usr/bin/env python3
"""Portable, one-attempt OpenRouter Jev client; Python 3.10+ standard library only."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.14"
MAX_REQUEST = 32 * 1024 * 1024
MAX_RESPONSE = 4 * 1024 * 1024


class JevError(Exception):
    def __init__(self, code, **details):
        self.details = {"error": code, **details}
        super().__init__(code)


def parse_json(text):
    def reject_constant(_):
        raise ValueError("nonfinite number")

    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value

    try:
        value = json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_pairs)
        # Also catch overflowing exponents such as 1e999.
        json.dumps(value, allow_nan=False)
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise JevError("invalid_json") from None


def number(value, low, high):
    return (type(value) is int or (type(value) is float and math.isfinite(value))) and low <= value <= high


def validate_request(value, model=None):
    if not isinstance(value, dict) or "state" not in value or not isinstance(value["state"], (str, dict, list)):
        raise JevError("invalid_state")
    if set(value) - {"model", "state", "questions", "provider", "session_id", "trace", "user"}:
        raise JevError("unsupported_request_field")
    chosen = model or value.get("model") or os.environ.get("JEV_MODEL") or DEFAULT_MODEL
    if model and "model" in value and value["model"] != model:
        raise JevError("request_model_conflict")
    if not isinstance(chosen, str) or not (chosen.startswith("typesafe/jev-") or chosen == "~typesafe/jev-latest") or "router" in chosen:
        raise JevError("invalid_model")
    questions = value.get("questions")
    if not isinstance(questions, dict) or not 1 <= len(questions) <= 32:
        raise JevError("invalid_questions", hint="Use 1–32 questions per request.")
    for key, question in questions.items():
        if not isinstance(key, str) or not key or not isinstance(question, dict):
            raise JevError("invalid_question")
        kind = question.get("type")
        if kind not in ("choice", "noul", "score", "box") or not isinstance(question.get("instructions"), (str, dict, list)) or not question["instructions"]:
            raise JevError("invalid_question")
        criteria = question.get("criteria")
        if kind == "choice" and (not isinstance(criteria, dict) or len(criteria) < 2 or any(not isinstance(k, str) or not k for k in criteria)):
            raise JevError("invalid_choice_criteria")
        if kind == "score" and (not isinstance(criteria, list) or not 2 <= len(criteria) <= 10):
            raise JevError("invalid_score_criteria")
        if kind == "noul" and criteria is not None and (not isinstance(criteria, dict) or set(criteria) != {"true", "false"}):
            raise JevError("invalid_noul_criteria")
        if kind == "box" and "criteria" in question:
            raise JevError("box_has_no_criteria")
    payload = {**value, "model": chosen}
    try:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise JevError("invalid_json") from None
    if len(body) > MAX_REQUEST:
        raise JevError("request_too_large")
    return payload, body


def validate_response(value, payload, expected_model=None):
    if not isinstance(value, dict) or not isinstance(value.get("model"), str) or not value["model"]:
        raise JevError("invalid_response_model")
    if expected_model and value["model"] != expected_model:
        raise JevError("resolved_model_mismatch")
    answers = value.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(payload["questions"]):
        raise JevError("answer_ids_mismatch")
    for key, question in payload["questions"].items():
        answer = answers[key]
        kind = question["type"]
        if not isinstance(answer, dict) or answer.get("type") != kind:
            raise JevError("answer_type_mismatch")
        if kind == "choice" and (not isinstance(answer.get("choice"), str) or answer["choice"] not in question["criteria"]):
            raise JevError("invalid_choice_answer")
        if kind == "noul" and not number(answer.get("noul"), 0, 1):
            raise JevError("invalid_noul_answer")
        if kind == "score" and not number(answer.get("score"), 0, len(question["criteria"]) - 1):
            raise JevError("invalid_score_answer")
        if kind == "box":
            box = answer.get("box")
            if not isinstance(box, dict) or any(not number(box.get(k), 0, 1) for k in ("top", "bottom", "left", "right")):
                raise JevError("invalid_box_answer")
            if box["top"] > box["bottom"] or box["left"] > box["right"]:
                raise JevError("invalid_box_answer")
        if "confidence" in answer and not number(answer["confidence"], 0, 1):
            raise JevError("invalid_confidence")
        if "probabilities" in answer:
            probabilities = answer["probabilities"]
            if kind not in ("choice", "score"):
                raise JevError("invalid_probabilities")
            keys = set(question["criteria"]) if kind == "choice" else {str(i) for i in range(len(question["criteria"]))}
            if not isinstance(probabilities, dict) or set(probabilities) != keys or any(not number(p, 0, 1) for p in probabilities.values()):
                raise JevError("invalid_probabilities")


def safe_metadata(value):
    """Retain accounting fields on validation failure without echoing upstream bodies."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in ("model", "id", "provider"):
        if isinstance(value.get(key), str):
            result[key] = value[key][:256]
    usage = value.get("usage")
    if isinstance(usage, dict):
        result["usage"] = {k: usage[k] for k in ("input_tokens", "output_tokens", "cost") if number(usage.get(k), 0, float("inf"))}
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def decide(payload, body, key, timeout, expected_model=None, opener=None):
    if not key or not key.strip():
        raise JevError("missing_credential", requests=0, hint="Provide OPENROUTER_API_KEY through the process environment.")
    if "\n" in key or "\r" in key:
        raise JevError("invalid_credential", requests=0)
    opener = opener or urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json", "Accept": "application/json"
    })
    started = time.monotonic()
    metrics = {"requests": 1, "questions": len(payload["questions"])}
    value = None
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise JevError("response_too_large")
        value = parse_json(raw)
        validate_response(value, payload, expected_model)
    except urllib.error.HTTPError as error:
        details = {"http_status": error.code}
        retry = error.headers.get("Retry-After") if error.headers else None
        if retry and retry.isdigit():
            details["retry_after_s"] = int(retry)
        error.close()
        raise JevError("upstream_http_error", **details, **metrics, http_elapsed_s=time.monotonic()-started, billing="unknown") from None
    except (OSError, urllib.error.URLError, ValueError):
        raise JevError("transport_error", **metrics, http_elapsed_s=time.monotonic()-started, billing="unknown", hint="Request may have reached the provider; do not replay blindly.") from None
    except JevError as error:
        raise JevError(error.details["error"], **metrics, http_elapsed_s=time.monotonic()-started, response_metadata=safe_metadata(value), billing="reported_usage_if_present_otherwise_unknown") from None
    metrics["http_elapsed_s"] = time.monotonic() - started
    return {"response": value, "metrics": metrics}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-", help="Request JSON file, or - for stdin")
    parser.add_argument("--output", help="Create a new result file; default stdout")
    parser.add_argument("--model", help="Requested model; must agree with payload if present")
    parser.add_argument("--expected-model", default=os.environ.get("JEV_EXPECTED_SNAPSHOT"), help="Require this exact returned snapshot")
    parser.add_argument("--timeout", type=float, default=30, help="Per-operation network timeout in seconds")
    parser.add_argument("--validate-only", action="store_true", help="Validate locally; no credential or network access")
    args = parser.parse_args(argv)
    destination = None
    created = False
    result = None
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise JevError("invalid_timeout")
        if args.input == "-":
            raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        else:
            with open(args.input, "rb") as source:
                raw = source.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise JevError("request_too_large")
        payload, body = validate_request(parse_json(raw), args.model)
        if args.validate_only:
            result = {"valid": True, "model": payload["model"], "questions": len(payload["questions"]), "request_bytes": len(body), "requests": 0}
        else:
            # Reserve output before spending; never overwrite existing files or follow symlinks.
            if args.output:
                destination = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                created = True
            result = decide(payload, body, os.environ.get("OPENROUTER_API_KEY"), args.timeout, args.expected_model)
        text = json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        if destination is not None:
            with os.fdopen(destination, "w", encoding="utf-8") as output:
                destination = None
                output.write(text)
            created = False
        else:
            sys.stdout.write(text)
        return 0
    except (JevError, OSError) as error:
        if destination is not None:
            os.close(destination)
        if created:
            Path(args.output).unlink(missing_ok=True)
        details = error.details if isinstance(error, JevError) else {"error": "local_io_error"}
        if isinstance(error, OSError):
            if result and "response" in result:
                details.update(result["metrics"], response_metadata=safe_metadata(result["response"]))
            else:
                details["requests"] = 0
        print(json.dumps(details, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
