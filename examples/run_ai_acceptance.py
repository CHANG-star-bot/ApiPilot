"""Standalone real-model acceptance; never calls ApiPilot's test executor.

Run from the project root: python -m examples.run_ai_acceptance
Two local fixtures, at most two model requests, no retries or output repair.
"""

import argparse
import json
import os
from pathlib import Path

from src.apipilot.ai_client import AIClient, AIOutputError, AIServiceError
from src.apipilot.ai_scenario_generator import (
    CATEGORIES, STRATEGIES, build_prompt, input_signature, parse_suggestions, validate_scenario,
)
from src.apipilot.openapi_parser import parse_openapi
from src.apipilot.reporting import collect_secrets, write_report


PROJECT = Path(__file__).resolve().parents[1]
FIXTURES = (
    PROJECT / "examples" / "ai_scenarios_openapi.json",
    PROJECT / "examples" / "ai_review_openapi.json",
)


def rule_baseline(interface):
    """Try each supported strategy on one parameter at a time, without AI."""
    results = []
    for parameter in interface["parameters"]:
        if "$ref" in parameter:
            continue
        for strategy in STRATEGIES:
            category = (
                "boundary" if strategy in ("minimum", "maximum") else
                "negative" if strategy in ("below_minimum", "above_maximum", "omit") else "normal"
            )
            candidate = {
                "name": f"Rule: {parameter['in']} {parameter['name']} {strategy}",
                "category": category,
                "intent": f"Review the {strategy} strategy for {parameter['name']}",
                "inputs": [{"name": parameter["name"], "in": parameter["in"], "strategy": strategy}],
                "expected_result": {"status_code": None, "body": None, "notes": "Confirm actual API behavior and assertions"},
            }
            try:
                result = validate_scenario(candidate, interface)
            except AIOutputError:
                continue  # No declared value/bound, or protected parameter.
            result["source"] = "rule_generated"
            for item in result["inputs"]:
                if item["source"] == "ai_inferred":
                    item["source"] = "rule_generated"
            results.append(result)
    return results


def empty_metrics():
    # null means not observed; zero would incorrectly imply a measured result.
    return {name: None for name in (
        "raw_json_type", "raw_suggestions", "raw_categories", "invalid_items",
        "duplicate_names", "duplicate_inputs", "accepted_suggestions",
        "rejected_suggestions", "novel_inputs_vs_rules",
    )}


def review_output(text, interface, rules):
    """Keep whole-batch validation authoritative; individual checks diagnose only."""
    metrics = empty_metrics()
    suggestions, error = None, None
    try:
        suggestions = parse_suggestions(text, interface)
    except AIOutputError as failure:
        error = str(failure)
    try:
        document = json.loads(text)
    except (ValueError, RecursionError):
        metrics["raw_json_type"] = "invalid_json"
        return metrics, suggestions, error
    metrics["raw_json_type"] = (
        "object" if isinstance(document, dict) else
        "array" if isinstance(document, list) else
        "null" if document is None else "scalar"
    )
    raw = document.get("scenarios") if isinstance(document, dict) else None
    if not isinstance(raw, list):
        return metrics, suggestions, error
    metrics.update(raw_suggestions=len(raw), invalid_items=0, duplicate_names=0, duplicate_inputs=0)
    categories = {name: 0 for name in sorted(CATEGORIES)}
    categories["unknown"] = 0
    names, signatures = set(), set()
    for item in raw:
        category = item.get("category") if isinstance(item, dict) else None
        categories[category if isinstance(category, str) and category in CATEGORIES else "unknown"] += 1
        name = item.get("name") if isinstance(item, dict) else None
        if isinstance(name, str):
            metrics["duplicate_names"] += int(name in names)
            names.add(name)
        try:
            valid = validate_scenario(item, interface)
        except AIOutputError:
            metrics["invalid_items"] += 1
            continue
        signature = input_signature(valid)
        metrics["duplicate_inputs"] += int(signature in signatures)
        signatures.add(signature)
    accepted = suggestions["ai_inferred"] if suggestions else []
    baseline = {input_signature(item) for item in rules}
    metrics.update(
        raw_categories=categories, accepted_suggestions=len(accepted),
        rejected_suggestions=len(raw) - len(accepted),
        novel_inputs_vs_rules=len({input_signature(item) for item in accepted} - baseline),
    )
    return metrics, suggestions, error


def run_acceptance(report_path, timeout=30.0):
    if Path(report_path).resolve() in {path.resolve() for path in FIXTURES}:
        raise ValueError("Report path must differ from the OpenAPI fixtures")
    # Parse and prepare both examples before making the first paid/free request.
    groups = []
    for fixture in FIXTURES:
        interfaces = parse_openapi(fixture)
        if len(interfaces) != 1:
            raise ValueError("Each acceptance fixture must contain exactly one GET/POST interface")
        interface = interfaces[0]
        groups.append({
            "fixture": fixture.name, "interface": interface,
            "prompt": build_prompt(interface), "rules": rule_baseline(interface),
        })
    report = {
        "kind": "real_model_acceptance", "executable": False,
        "status": "NOT_CALLED", "requested_model": None,
        "calls": 0, "responses": 0, "results": [],
        "quality_note": "Extra input combinations are only novelty, not proof of useful tests. Human review is required.",
    }
    client, config_error = None, None
    try:
        client = AIClient(timeout=timeout)
        report["requested_model"] = os.environ["APIPILOT_AI_MODEL"].strip()
    except AIServiceError as error:
        missing = any(not os.environ.get(name, "").strip() for name in (
            "APIPILOT_AI_URL", "APIPILOT_AI_MODEL", "APIPILOT_AI_API_KEY",
        ))
        report["status"] = "NOT_CONFIGURED" if missing else "CONFIG_ERROR"
        config_error = str(error)
    stopped = False
    for group in groups:
        declared_values = {
            (item["inputs"][0]["name"], item["inputs"][0]["in"])
            for item in group["rules"] if item["inputs"][0]["strategy"] == "declared_value"
        }
        pending = ["Confirm expected status and response assertions for every suggestion"]
        for parameter in group["interface"]["parameters"]:
            if "$ref" in parameter:
                pending.append("Resolve referenced parameter definitions manually")
            elif parameter.get("required") and (parameter["name"], parameter["in"]) not in declared_values:
                pending.append(f"Provide/approve {parameter['in']} parameter: {parameter['name']}")
        if group["interface"]["has_request_body"]:
            pending.append("Provide Body schema and approved business data; parser exposes only Body presence")
        entry = {
            "fixture": group["fixture"], "method": group["interface"]["method"],
            "path": group["interface"]["path"], "status": "NOT_CALLED",
            "actual_model": None, "metrics": empty_metrics(),
            "rule_baseline": group["rules"], "suggestions": None,
            "pending_information": pending,
        }
        report["results"].append(entry)
        if client is None:
            entry.update(status=report["status"], error=config_error)
            continue
        if stopped:
            entry["error"] = "Not called after a service failure; no automatic retries"
            continue
        report["calls"] += 1
        try:
            text = client.generate(group["prompt"])
            report["responses"] += 1
            metrics, suggestions, error = review_output(text, group["interface"], group["rules"])
            entry.update(metrics=metrics, suggestions=suggestions,
                         status="VALIDATED" if suggestions else "INVALID_OUTPUT")
            if error:
                entry["error"] = error
        except (AIServiceError, AIOutputError) as error:
            entry.update(status="SERVICE_ERROR" if isinstance(error, AIServiceError) else "INVALID_OUTPUT", error=str(error))
            stopped = isinstance(error, AIServiceError)
        entry["actual_model"] = client.last_model
    if client is not None:
        report["status"] = "VALIDATED" if all(item["status"] == "VALIDATED" for item in report["results"]) else "INCOMPLETE"
    secrets = collect_secrets({"api_key": os.environ.get("APIPILOT_AI_API_KEY", "").strip()})
    write_report(report, report_path, secrets)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="reports/ai_real_acceptance.json")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    try:
        report = run_acceptance(args.report, args.timeout)
    except (OSError, ValueError):
        print("Acceptance setup/report error; check fixture files, timeout and output path")
        return 2
    print(f"STATUS={report['status']} CALLS={report['calls']} RESPONSES={report['responses']}")
    for item in report["results"]:
        print(f"{item['method']} {item['path']}: {item['status']}")
    return 0 if report["status"] == "VALIDATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
