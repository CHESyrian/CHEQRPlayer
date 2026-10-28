"""Terminal and file output formatters."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import List, TextIO

from .parser import AccountInfo


def format_terminal(accounts: List[AccountInfo], *, show_secrets: bool = True) -> str:
    """Human-readable multi-line summary suitable for stdout."""
    if not accounts:
        return "No accounts found.\n"

    lines: List[str] = []
    lines.append(f"Found {len(accounts)} account(s):\n")
    lines.append("=" * 60)

    for acc in accounts:
        lines.append(f"\n[{acc.index}]  type={acc.payload_type}")
        if acc.payload_type == "otpauth":
            lines.append(f"    OTP type : {acc.otp_type}")
            lines.append(f"    Label    : {acc.label or '(none)'}")
            lines.append(f"    Issuer   : {acc.issuer or '(none)'}")
            secret_display = acc.secret if show_secrets else "***REDACTED***"
            lines.append(f"    Secret   : {secret_display}")
            lines.append(f"    Algorithm: {acc.algorithm}")
            lines.append(f"    Digits   : {acc.digits}")
            if acc.otp_type == "totp":
                lines.append(f"    Period   : {acc.period}s")
            else:
                lines.append(f"    Counter  : {acc.counter}")
            if acc.extra_params:
                lines.append(f"    Extra    : {acc.extra_params}")
        else:
            lines.append(f"    Raw      : {acc.raw}")
            if acc.extra_params:
                lines.append(f"    Note     : {acc.extra_params}")
        lines.append("-" * 40)

    return "\n".join(lines) + "\n"


def write_json(
    accounts: List[AccountInfo],
    fp: TextIO,
    *,
    show_secrets: bool = True,
    indent: int = 2,
) -> None:
    data = [a.to_dict(include_secret=show_secrets) for a in accounts]
    json.dump({"count": len(data), "accounts": data}, fp, indent=indent, ensure_ascii=False)
    fp.write("\n")


def write_csv(
    accounts: List[AccountInfo],
    fp: TextIO,
    *,
    show_secrets: bool = True,
) -> None:
    fieldnames = [
        "index",
        "payload_type",
        "otp_type",
        "label",
        "issuer",
        "secret",
        "algorithm",
        "digits",
        "period",
        "counter",
        "raw",
    ]
    writer = csv.DictWriter(fp, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for acc in accounts:
        row = acc.to_dict(include_secret=show_secrets)
        # Flatten extra_params into a string for CSV simplicity
        if acc.extra_params:
            row["raw"] = f"{row.get('raw', '')} | extra={acc.extra_params}"
        writer.writerow(row)


def write_output(
    accounts: List[AccountInfo],
    output_type: str,
    output_file: Path | None = None,
    *,
    fmt: str = "json",
    show_secrets: bool = True,
) -> None:
    """
    Dispatch to terminal or file writer.

    *fmt* is used only when writing to file (json|csv).
    """
    if output_type == "terminal":
        text = format_terminal(accounts, show_secrets=show_secrets)
        sys.stdout.write(text)
        return

    if output_file is None:
        raise ValueError("--output-file is required when --output-type=file")

    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8", newline="") as fp:
        if fmt == "csv":
            write_csv(accounts, fp, show_secrets=show_secrets)
        else:
            write_json(accounts, fp, show_secrets=show_secrets)
