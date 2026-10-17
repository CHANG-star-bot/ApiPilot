import json
import re


def parse_openapi(file_path):
    """Read a local OpenAPI JSON file and return GET/POST interface metadata.

    This performs basic structure checks, not full OpenAPI validation.
    The returned interfaces are not executable test cases.
    """
    with open(file_path, "r", encoding="utf-8") as file:
        try:
            document = json.load(file)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid OpenAPI JSON: {error.msg}") from error

    if not isinstance(document, dict):
        raise ValueError("OpenAPI document must be an object")

    version = document.get("openapi")
    if not isinstance(version, str) or not re.fullmatch(r"3\.(0|1)\.[0-9]+", version):
        raise ValueError("Only OpenAPI 3.0.x and 3.1.x JSON documents are supported")

    info = document.get("info")
    if not isinstance(info, dict) or not all(
        isinstance(info.get(field), str) for field in ("title", "version")
    ):
        raise ValueError("info must contain string title and version fields")

    paths = document.get("paths")
    # OpenAPI 3.1 can describe only components or webhooks, without any paths.
    if "paths" not in document and version.startswith("3.1."):
        if "components" in document or "webhooks" in document:
            paths = {}
    if not isinstance(paths, dict):
        raise ValueError("paths must be an object")

    interfaces = []
    for path, path_item in paths.items():
        if path.startswith("x-"):
            continue
        if not path.startswith("/"):
            raise ValueError(f"API path must start with '/': {path}")
        if not isinstance(path_item, dict):
            raise ValueError(f"Path Item must be an object: {path}")
        if "$ref" in path_item:
            raise ValueError(f"Path Item references are not supported: {path}")

        path_parameters = _read_parameters(path_item, path)
        for method in ("get", "post"):
            if method not in path_item:
                continue
            operation = path_item[method]
            label = f"{method.upper()} {path}"
            if not isinstance(operation, dict):
                raise ValueError(f"Operation must be an object: {label}")

            summary = operation.get("summary", label)
            if not isinstance(summary, str):
                raise ValueError(f"summary must be a string: {label}")
            if "requestBody" in operation and not isinstance(operation["requestBody"], dict):
                raise ValueError(f"requestBody must be an object: {label}")

            # Operation parameters override path parameters with the same name/in.
            parameters = {}
            for parameter in path_parameters + _read_parameters(operation, label):
                if "$ref" in parameter:
                    key = ("$ref", parameter["$ref"])
                else:
                    key = (parameter["name"], parameter["in"])
                parameters[key] = parameter

            interfaces.append({
                "method": method.upper(),
                "path": path,
                "summary": summary or label,
                "parameters": list(parameters.values()),
                "has_request_body": "requestBody" in operation,
            })

    return interfaces


def _read_parameters(container, location):
    parameters = container.get("parameters", [])
    if not isinstance(parameters, list):
        raise ValueError(f"parameters must be an array: {location}")
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise ValueError(f"Each parameter must be an object: {location}")
        if "$ref" in parameter:
            if not isinstance(parameter["$ref"], str):
                raise ValueError(f"Parameter $ref must be a string: {location}")
            # Preserve references as metadata; never resolve or fetch them.
            continue
        if not isinstance(parameter.get("name"), str) or parameter.get("in") not in (
            "query", "header", "path", "cookie"
        ):
            raise ValueError(f"Inline parameters need name and valid in fields: {location}")
    return parameters
