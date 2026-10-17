import argparse
import math
import sys
from pathlib import Path

from .case_generator import generate_cases
from .case_loader import load_cases
from .http_client import DEFAULT_TIMEOUT
from .reporting import collect_secrets, redact, write_report
from .suite_runner import run_suite


def _positive_timeout(value):
    try:
        timeout = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number") from error
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number")
    return timeout


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate and execute ApiPilot API test cases.")
    parser.add_argument("--openapi", required=True, type=Path, help="Local OpenAPI JSON file")
    parser.add_argument("--config", required=True, type=Path, help="Local JSON test configuration")
    parser.add_argument("--report", required=True, type=Path, help="Output JSON report path")
    parser.add_argument(
        "--timeout", type=_positive_timeout, default=DEFAULT_TIMEOUT,
        help="Connection/read timeout in seconds (default: 10)",
    )
    args = parser.parse_args(argv)
    secrets = ()
    try:
        # Read configuration for redaction; generation still belongs to case_generator.
        secrets = collect_secrets(load_cases(args.config))
        generated = generate_cases(args.openapi, args.config)
        if args.report.resolve() in (args.openapi.resolve(), args.config.resolve()):
            raise ValueError("Report output must not overwrite an input file")
        if args.report.is_dir():
            raise ValueError("Report output must be a file, not a directory")
        args.report.parent.mkdir(parents=True, exist_ok=True)

        report = run_suite(**generated, timeout=args.timeout)
        summary = report["summary"]
        print(
            f"TOTAL={summary['total']} EXECUTED={summary['total']} "
            f"PASS={summary['PASS']} FAIL={summary['FAIL']} "
            f"ERROR={summary['ERROR']} PENDING={summary['pending']}"
        )
        write_report(report, args.report, secrets)
    except (OSError, ValueError, TypeError) as error:
        message = redact(f"{type(error).__name__}: {error}", secrets)
        print(f"ApiPilot error: {message}", file=sys.stderr)
        return 2

    print(f"Report: {args.report}")
    if summary["total"] == 0:
        print("No executable cases; the report preserves any pending reasons.", file=sys.stderr)
        return 2
    return 1 if summary["FAIL"] or summary["ERROR"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
