import json
import re
import tempfile
from pathlib import Path
from urllib.parse import quote, quote_plus, unquote, urlsplit


REDACTED = "[REDACTED]"
_SECRET_NAMES = {
    "authorization", "proxyauthorization", "cookie", "setcookie", "key",
    "apikey", "secretkey", "token", "password", "passwd", "secret", "credentials",
}
_ASSIGNMENT = re.compile(
    r"""(?ix)(\b(?:authorization|proxy[-_]?authorization|(?:x[-_]?)?api[-_]?key|
    (?:access|refresh|id)[-_]?token|token|password|passwd|client[-_]?secret|secret)
    \b["']?\s*[:=]\s*)
    (?:"[^"]*"|'[^']*'|(?:Bearer|Basic)\s+\[REDACTED\]|\[REDACTED\]|[^\s&,;}\]]+)"""
)
_COOKIE = re.compile(
    r"""(?ix)(\b(?:set[-_]?cookie|cookie)\b["']?\s*[:=]\s*)
    (?:"[^"]*"|'[^']*'|[^\r\n}]+)"""
)


def _sensitive_name(name):
    normalized = re.sub(r"[^a-z0-9]", "", str(name).lower())
    return normalized in _SECRET_NAMES or normalized.endswith(
        ("apikey", "token", "password", "passwd", "secret", "credential")
    )


def collect_secrets(config):
    """Collect configured secrets and common escaped forms for diagnostic masking."""
    secrets = set()

    def add(text):
        if text:
            secrets.update((text, quote(text, safe=""), quote_plus(text), repr(text)[1:-1]))
            secrets.add(json.dumps(text, ensure_ascii=False)[1:-1])

    def visit(value, sensitive=False):
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, sensitive or _sensitive_name(key) or str(key).lower() == "headers")
        elif isinstance(value, list):
            for child in value:
                visit(child, sensitive)
        elif isinstance(value, str):
            if sensitive:
                add(value)
                if value.lower().startswith(("bearer ", "basic ")):
                    parts = value.split(None, 1)
                    if len(parts) == 2:
                        add(parts[1])
                # Also mask individual values if a Cookie header is echoed in parts.
                for part in value.split(";"):
                    if "=" in part:
                        add(part.split("=", 1)[1].strip())
            if value.startswith(("http://", "https://")):
                try:
                    parsed = urlsplit(value)
                    for credential in (parsed.username, parsed.password):
                        if credential:
                            add(unquote(credential))
                except ValueError:
                    pass  # The generator will reject malformed base URLs.
        elif sensitive and value is not None:
            add(str(value))

    visit(config)
    return tuple(sorted(secrets, key=len, reverse=True))


def redact(value, secrets=()):
    """Return a sanitized copy; do not alter requests, assertions or input config."""
    if isinstance(value, dict):
        sanitized = {}
        for key, child in value.items():
            if _sensitive_name(key):
                sanitized[key] = REDACTED
            elif key == "status" and child in ("PASS", "FAIL", "ERROR"):
                sanitized[key] = child
            elif key == "method" and child in ("GET", "POST"):
                sanitized[key] = child
            else:
                sanitized[key] = redact(child, secrets)
        return sanitized
    if isinstance(value, list):
        return [redact(child, secrets) for child in value]
    if not isinstance(value, str):
        return value

    for secret in secrets:
        if len(secret) < 4:
            value = re.sub(r"(?<!\w)" + re.escape(secret) + r"(?!\w)", REDACTED, value)
        else:
            value = value.replace(secret, REDACTED)
    value = re.sub(r"(?i)(https?://)[^/\s@]+@", r"\1[REDACTED]@", value)
    value = re.sub(r"(?i)\b(Bearer|Basic)\s+[a-z0-9._~+/=%-]+", r"\1[REDACTED]", value)
    value = _COOKIE.sub(lambda match: match[1] + REDACTED, value)
    value = _ASSIGNMENT.sub(lambda match: match[1] + REDACTED, value)
    # Actual response credentials may not exist in the configuration. Do not
    # persist raw expected/actual values from the assertion module's messages.
    return re.sub(
        r"\bExpected (?!status\b|object\b|array\b|at least\b).+, got .+",
        "Response value mismatch (values omitted)", value, flags=re.DOTALL,
    )


def write_report(report, output_path, secrets=()):
    """Write sanitized UTF-8 JSON atomically, leaving inputs/report objects intact."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output_path.parent, suffix=".tmp", delete=False
        ) as file:
            temporary_path = Path(file.name)
            json.dump(redact(report, secrets), file, ensure_ascii=False, indent=2)
            file.write("\n")
        temporary_path.replace(output_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
