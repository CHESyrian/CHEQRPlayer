"""CHEQRPlayer *write* command – create QR-code images."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__


def register_write_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the ``write`` subcommand on a parent parser."""
    p = sub.add_parser(
        "write",
        help="Create QR-code PNG image(s) from text or a .txt/.json file",
        description=(
            "Create QR-code PNG image(s) from text or from a .txt / .json file. "
            "JSON may be a plain string, an object with text/payload/raw, or a "
            "CHEQRPlayer accounts export (one QR per account)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  CHEQRPlayer write --input-type text --text "Hello World" --output-file hello
  CHEQRPlayer write --input-type text --text "otpauth://totp/..." --color navy --output-file totp
  CHEQRPlayer write --input-type file --input-file notes.txt --output-file notes
  CHEQRPlayer write --input-type file --input-file accounts.json --color "#1a73e8" --output-file acc
""",
    )
    p.add_argument(
        "--input-type",
        required=True,
        choices=("text", "file"),
        help="Source of the payload: inline text or a file",
    )
    p.add_argument(
        "--text",
        default=None,
        help="Payload string (required when --input-type=text)",
    )
    p.add_argument(
        "--input-file",
        type=Path,
        metavar="PATH",
        default=None,
        help="Input file path (.txt or .json); required when --input-type=file",
    )
    p.add_argument(
        "--color",
        default="black",
        help="QR module (foreground) colour: name or #RRGGBB (default: black)",
    )
    p.add_argument(
        "--background",
        default="white",
        help="Background colour: name or #RRGGBB (default: white)",
    )
    p.add_argument(
        "--output-file",
        required=True,
        metavar="NAME",
        help="Output base name; written as NAME.png (or NAME_1.png, … if many)",
    )
    p.add_argument(
        "--box-size",
        type=int,
        default=10,
        help="Pixels per QR module (default: 10)",
    )
    p.add_argument(
        "--border",
        type=int,
        default=4,
        help="Border modules around the QR (default: 4)",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    p.set_defaults(func=run_write)
    return p


def run_write(args: argparse.Namespace) -> int:
    """Execute the write (create) command."""
    from .creator import CreateError, create_qr_codes, load_payloads

    log = logging.getLogger("qr_extractor.creator")

    if args.input_type == "text" and not args.text:
        log.error("--text is required when --input-type=text")
        return 2
    if args.input_type == "file" and args.input_file is None:
        log.error("--input-file is required when --input-type=file")
        return 2

    try:
        payloads = load_payloads(
            input_type=args.input_type,
            text=args.text,
            input_file=args.input_file,
        )
        paths = create_qr_codes(
            payloads,
            args.output_file,
            fill_color=args.color,
            back_color=args.background,
            box_size=args.box_size,
            border=args.border,
        )
    except CreateError as exc:
        log.error("%s", exc)
        return 2
    except OSError as exc:
        log.error("%s", exc)
        return 3

    if len(paths) == 1:
        sys.stdout.write(f"Wrote {paths[0]}\n")
    else:
        sys.stdout.write(f"Wrote {len(paths)} QR code(s):\n")
        for p in paths:
            sys.stdout.write(f"  {p}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Delegate to unified CHEQRPlayer CLI (write subcommand)."""
    from .player import main as player_main

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("read", "write", "-h", "--help", "--version"):
        argv = ["write", *argv]
    return player_main(argv)


if __name__ == "__main__":
    sys.exit(main())
