import json
import re
from urllib.parse import quote, urlsplit

from .openapi_parser import parse_openapi


def generate_cases(openapi_path, config_path):
    """Combine local OpenAPI metadata with explicit JSON test settings.

    Configuration: {"base_url": "https://example.test/api", "cases": [...]}.
    Each case is matched by method/path and may provide path_params, params,
    headers, body, expected_status, expected_body and a display name.

    Return separate executable_cases and pending_cases lists; never execute them.
    V0.2 conservatively requires a non-null body for every declared requestBody.
    Body schemas, authentication and reference expansion are not inferred.
    """
    interfaces = parse_openapi(openapi_path)
    base_url, settings_by_interface = _load_config(config_path)
    known_interfaces = {(item["method"], item["path"]) for item in interfaces}
    for key in settings_by_interface:
        if key not in known_interfaces:
            raise ValueError(f"Configured interface not found in OpenAPI: {key[0]} {key[1]}")

    result = {"executable_cases": [], "pending_cases": []}
    for interface in interfaces:
        method, path = interface["method"], interface["path"]
        settings = settings_by_interface.get((method, path))
        reasons = []
        if settings is None:
            reasons.append("Missing test configuration")
            settings = {}

        status = settings.get("expected_status")
        if status is None:
            reasons.append("Missing expected_status")
        elif type(status) is not int or not 100 <= status <= 599:
            reasons.append("expected_status must be an integer between 100 and 599")

        resolved_path = _fill_path(path, interface["parameters"], settings, reasons)
        _check_required_parameters(interface["parameters"], settings, reasons)
        if interface["has_request_body"] and settings.get("body") is None:
            reasons.append("Missing body for declared requestBody")
        if method == "GET" and settings.get("body") is not None:
            reasons.append("GET body is not supported by the current http_client")

        name = settings.get("name", interface["summary"])
        if reasons:
            # Pending records deliberately lack the URL/status needed by run_case.
            result["pending_cases"].append({
                "name": name,
                "method": method,
                "path": path,
                "reasons": reasons,
            })
            continue

        case = {
            "name": name,
            "method": method,
            "url": base_url.rstrip("/") + "/" + resolved_path.lstrip("/"),
            "expected_status": status,
        }
        for field in ("params", "headers", "body", "expected_body"):
            if field in settings:
                case[field] = settings[field]
        result["executable_cases"].append(case)

    return result


def _load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as file:
        try:
            config = json.load(file)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid test configuration JSON: {error.msg}") from error
    if not isinstance(config, dict):
        raise ValueError("Test configuration must be an object")

    base_url = config.get("base_url")
    if not isinstance(base_url, str):
        raise ValueError("base_url must be an HTTP(S) URL")
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("base_url must be an HTTP(S) URL")
    if parts.query or parts.fragment:
        raise ValueError("base_url must not contain a query string or fragment")

    entries = config.get("cases", [])
    if not isinstance(entries, list):
        raise ValueError("Configuration cases must be an array")
    settings_by_interface = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each case configuration must be an object")
        method, path = entry.get("method"), entry.get("path")
        if not isinstance(method, str) or method.upper() not in ("GET", "POST"):
            raise ValueError("Case method must be GET or POST")
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValueError("Case path must start with '/'")
        for field in ("path_params", "params", "headers"):
            if entry.get(field) is not None and not isinstance(entry[field], dict):
                raise ValueError(f"{field} must be an object or null")
        if "name" in entry and not isinstance(entry["name"], str):
            raise ValueError("Case name must be a string")
        key = (method.upper(), path)
        if key in settings_by_interface:
            raise ValueError(f"Duplicate case configuration: {key[0]} {key[1]}")
        settings_by_interface[key] = entry
    return base_url, settings_by_interface


def _fill_path(path, parameters, settings, reasons):
    names = re.findall(r"\{([^{}]+)\}", path)
    names += [item["name"] for item in parameters if item.get("in") == "path"]
    values = settings.get("path_params") or {}
    for name in dict.fromkeys(names):
        value = values.get(name)
        if value is None or value == "":
            reasons.append(f"Missing path parameter: {name}")
        elif not isinstance(value, (str, int, float, bool)):
            reasons.append(f"Path parameter must be a scalar: {name}")
        else:
            text = json.dumps(value) if isinstance(value, bool) else str(value)
            path = path.replace("{" + name + "}", quote(text, safe=""))
    return path


def _check_required_parameters(parameters, settings, reasons):
    params = settings.get("params") or {}
    headers = {name.lower(): value for name, value in (settings.get("headers") or {}).items()}
    for parameter in parameters:
        if "$ref" in parameter:
            reasons.append(f"Unresolved parameter reference: {parameter['$ref']}")
            continue
        location, name = parameter["in"], parameter["name"]
        if not parameter.get("required") or location == "path":
            continue
        if location == "cookie":
            reasons.append(f"Required cookie parameter is not supported: {name}")
            continue
        value = headers.get(name.lower()) if location == "header" else params.get(name)
        if value is None or value == "" or value == []:
            reasons.append(f"Missing required {location} parameter: {name}")
