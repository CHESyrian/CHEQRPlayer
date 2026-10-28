"""Unified CHEQRPlayer CLI – subcommands: read | write."""

from __future__ import annotations

import argparse
import logging
import sys

from . import __app_name__, __version__
from .cli import register_read_parser
from .create_cli import register_write_parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=__app_name__,
        description=(
            "CHEQRPlayer – decode QR codes from images (read) or create "
            "QR-code PNG images (write). Supports standard payloads and "
            "TOTP/HOTP (otpauth://) authenticator URIs."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""\
Commands:
  read    Decode QR codes from an image
  write   Create QR-code PNG image(s)

Examples:
  {__app_name__} read --image shot.png --output-type terminal
  {__app_name__} read --image shot.png --qr-type totp --output-type file --output-file accounts.json
  {__app_name__} write --input-type text --text "Hello" --output-file hello
  {__app_name__} write --input-type file --input-file notes.txt --color navy --output-file notes
""",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = p.add_subparsers(
        dest="command",
        title="commands",
        metavar="{read,write}",
        required=True,
    )
    register_read_parser(sub)
    register_write_parser(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    verbose = getattr(args, "verbose", False)
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    return int(func(args))


if __name__ == "__main__":
    sys.exit(main())
