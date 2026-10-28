"""CHEQRPlayer *read* command – decode QR codes from images."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__


def register_read_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the ``read`` subcommand on a parent parser."""
    p = sub.add_parser(
        "read",
        help="Decode QR codes from an image (standard or TOTP/otpauth)",
        description=(
            "Decode QR codes from an image and extract structured account "
            "information. Supports standard QR payloads, otpauth:// TOTP/HOTP "
            "URIs, and Google Authenticator export QRs (otpauth-migration://)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  CHEQRPlayer read --image shot.png --output-type terminal
  CHEQRPlayer read --image shot.png --qr-type totp --output-type terminal
  CHEQRPlayer read --image shot.png --output-type file --output-file accounts.json
""",
    )
    p.add_argument(
        "--image",
        required=True,
        type=Path,
        metavar="PATH",
        help="Path to the input image (PNG, JPG, BMP, TIFF, …)",
    )
    p.add_argument(
        "--qr-type",
        choices=("auto", "standard", "totp"),
        default="auto",
        help=(
            "QR content mode: "
            "'auto' (default) detects otpauth://, otpauth-migration:// and raw; "
            "'totp' extracts only authenticator accounts; "
            "'standard' treats every payload as plain text"
        ),
    )
    p.add_argument(
        "--output-type",
        required=True,
        choices=("terminal", "file"),
        help="Where to write results",
    )
    p.add_argument(
        "--output-file",
        type=Path,
        metavar="PATH",
        help="Destination file (required when --output-type=file)",
    )
    p.add_argument(
        "--format",
        choices=("json", "csv"),
        default="json",
        help="File format when writing to disk (default: json)",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging (may include secrets)",
    )
    p.add_argument(
        "--hide-secrets",
        action="store_true",
        help="Redact secret values in all output",
    )
    p.set_defaults(func=run_read)
    return p


def run_read(args: argparse.Namespace) -> int:
    """Execute the read (decode) command."""
    from .decoder import DecodeError, decode_image
    from .output import write_output
    from .parser import accounts_from_payload, deduplicate, filter_by_qr_type

    log = logging.getLogger("qr_extractor")

    if args.output_type == "file" and args.output_file is None:
        log.error("--output-file is required when --output-type=file")
        return 2

    try:
        payloads = decode_image(args.image, verbose=args.verbose)
    except DecodeError as exc:
        log.error("%s", exc)
        return 2

    accounts: list = []
    for p in payloads:
        accounts.extend(accounts_from_payload(p, qr_type=args.qr_type))
    accounts = deduplicate(accounts)
    accounts = filter_by_qr_type(accounts, args.qr_type)
    for i, acc in enumerate(accounts, start=1):
        acc.index = i

    if not accounts:
        if args.qr_type == "totp":
            log.warning("No TOTP/otpauth accounts found in the image")
            msg = "No TOTP accounts found.\n"
        else:
            log.warning("No QR codes could be decoded from the image")
            msg = "No accounts found.\n"
        if args.output_type == "terminal":
            sys.stdout.write(msg)
        else:
            write_output(
                [],
                "file",
                args.output_file,
                fmt=args.format,
                show_secrets=not args.hide_secrets,
            )
        return 1

    show_secrets = not args.hide_secrets
    if args.verbose and show_secrets:
        for a in accounts:
            log.debug("Parsed: %s", a.to_dict(include_secret=True))

    try:
        write_output(
            accounts,
            args.output_type,
            args.output_file,
            fmt=args.format,
            show_secrets=show_secrets,
        )
    except OSError as exc:
        log.error("Failed to write output: %s", exc)
        return 3

    return 0


def main(argv: list[str] | None = None) -> int:
    """Delegate to unified CHEQRPlayer CLI (read subcommand)."""
    from .player import main as player_main

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("read", "write", "-h", "--help", "--version"):
        argv = ["read", *argv]
    return player_main(argv)


if __name__ == "__main__":
    sys.exit(main())
