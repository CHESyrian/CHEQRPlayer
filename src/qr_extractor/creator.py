"""Generate QR-code images from text or file input (txt / json)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import qrcode
from qrcode.constants import ERROR_CORRECT_M
from PIL import Image, ImageColor

logger = logging.getLogger(__name__)

SUPPORTED_FILE_EXTENSIONS = {".txt", ".json"}
DEFAULT_FILL = "black"
DEFAULT_BACK = "white"
DEFAULT_BOX_SIZE = 10
DEFAULT_BORDER = 4


class CreateError(Exception):
    """Raised when QR creation input is invalid or writing fails."""


def _parse_color(value: str, *, role: str = "fill") -> Tuple[int, int, int]:
    """
    Accept a colour name or #RRGGBB / #RGB hex string.
    Returns an RGB tuple suitable for Pillow / qrcode.
    """
    value = value.strip()
    try:
        rgb = ImageColor.getrgb(value)
    except ValueError as exc:
        raise CreateError(
            f"Invalid {role} colour '{value}'. "
            "Use a name (e.g. black, red) or hex (#RRGGBB)."
        ) from exc
    # ImageColor may return RGBA; keep RGB only
    return rgb[0], rgb[1], rgb[2]


def _load_text_payloads(text: str) -> List[str]:
    text = text.strip()
    if not text:
        raise CreateError("Input text is empty")
    return [text]


def _load_txt_file(path: Path) -> List[str]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CreateError(f"Cannot read file: {exc}") from exc
    return _load_text_payloads(content)


def _payloads_from_json_obj(data: object) -> List[str]:
    """
    Extract one or more QR payloads from parsed JSON.

    Supported shapes:
      - string                         → single payload
      - {"text"|"payload"|"raw": str}  → single payload
      - {"accounts": [ {...}, ... ]}   → CHEQRPlayer-style export (use "raw")
      - [ str | {...}, ... ]           → multiple payloads
    """
    if isinstance(data, str):
        s = data.strip()
        if not s:
            raise CreateError("JSON string payload is empty")
        return [s]

    if isinstance(data, dict):
        # CHEQRPlayer accounts export
        if "accounts" in data and isinstance(data["accounts"], list):
            payloads: List[str] = []
            for i, acc in enumerate(data["accounts"]):
                if not isinstance(acc, dict):
                    continue
                raw = acc.get("raw") or acc.get("payload") or acc.get("text")
                if isinstance(raw, str) and raw.strip():
                    payloads.append(raw.strip())
                elif acc.get("secret") and acc.get("otp_type"):
                    # Reconstruct a minimal otpauth URI when only fields exist
                    otp = acc.get("otp_type", "totp")
                    label = acc.get("label") or "account"
                    issuer = acc.get("issuer")
                    secret = acc["secret"]
                    path = f"{issuer}:{label}" if issuer else label
                    q = f"secret={secret}"
                    if issuer:
                        q += f"&issuer={issuer}"
                    if acc.get("algorithm"):
                        q += f"&algorithm={acc['algorithm']}"
                    if acc.get("digits") is not None:
                        q += f"&digits={acc['digits']}"
                    if otp == "totp" and acc.get("period") is not None:
                        q += f"&period={acc['period']}"
                    if otp == "hotp" and acc.get("counter") is not None:
                        q += f"&counter={acc['counter']}"
                    payloads.append(f"otpauth://{otp}/{path}?{q}")
            if not payloads:
                raise CreateError("JSON 'accounts' list produced no usable payloads")
            return payloads

        for key in ("text", "payload", "raw", "data", "content"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return [val.strip()]
        raise CreateError(
            "JSON object has no usable string field "
            "(expected text/payload/raw or an accounts list)"
        )

    if isinstance(data, list):
        payloads = []
        for item in data:
            payloads.extend(_payloads_from_json_obj(item))
        if not payloads:
            raise CreateError("JSON array produced no usable payloads")
        return payloads

    raise CreateError(f"Unsupported JSON type: {type(data).__name__}")


def _load_json_file(path: Path) -> List[str]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CreateError(f"Invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise CreateError(f"Cannot read file: {exc}") from exc
    return _payloads_from_json_obj(data)


def load_payloads(
    *,
    input_type: str,
    text: Optional[str] = None,
    input_file: Optional[Path] = None,
) -> List[str]:
    """
    Resolve input into a list of payload strings to encode.

    input_type:
      - "text" → use *text*
      - "file" → read *input_file* (.txt or .json)
    """
    if input_type == "text":
        if text is None or not str(text).strip():
            raise CreateError("--text is required when --input-type=text")
        return _load_text_payloads(str(text))

    if input_type == "file":
        if input_file is None:
            raise CreateError("--input-file is required when --input-type=file")
        path = Path(input_file)
        if not path.exists():
            raise CreateError(f"File does not exist: {path}")
        if not path.is_file():
            raise CreateError(f"Not a regular file: {path}")
        ext = path.suffix.lower()
        if ext not in SUPPORTED_FILE_EXTENSIONS:
            raise CreateError(
                f"Unsupported file type '{ext}'. Supported: .txt, .json"
            )
        if ext == ".txt":
            return _load_txt_file(path)
        return _load_json_file(path)

    raise CreateError(f"Unknown input-type: {input_type}")


def make_qr_image(
    payload: str,
    *,
    fill_color: str = DEFAULT_FILL,
    back_color: str = DEFAULT_BACK,
    box_size: int = DEFAULT_BOX_SIZE,
    border: int = DEFAULT_BORDER,
) -> Image.Image:
    """Build a Pillow Image containing a QR code for *payload*."""
    fill = _parse_color(fill_color, role="fill")
    back = _parse_color(back_color, role="background")

    qr = qrcode.QRCode(
        version=None,  # auto
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    img = qr.make_image(
        image_factory=None,  # default PilImage
        fill_color=fill,
        back_color=back,
    )
    # Ensure we always return a true PIL Image
    if not isinstance(img, Image.Image):
        img = img.get_image()
    return img.convert("RGB")


def resolve_output_path(output_file: Union[str, Path], index: Optional[int] = None) -> Path:
    """
    Normalise output path: always end with .png.
    When multiple payloads exist, append _N before the extension.
    """
    path = Path(output_file)
    # Strip existing image suffix so we control the final name
    stem = path.stem if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} else path.name
    parent = path.parent if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} else (
        path.parent if path.suffix else path.parent
    )
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"} and path.suffix:
        # e.g. user passed "out.qr" → treat whole name as stem
        stem = path.name
        parent = path.parent

    if index is not None:
        filename = f"{stem}_{index}.png"
    else:
        filename = f"{stem}.png"
    return parent / filename


def create_qr_codes(
    payloads: Sequence[str],
    output_file: Union[str, Path],
    *,
    fill_color: str = DEFAULT_FILL,
    back_color: str = DEFAULT_BACK,
    box_size: int = DEFAULT_BOX_SIZE,
    border: int = DEFAULT_BORDER,
) -> List[Path]:
    """
    Generate one PNG per payload and write them to disk.
    Returns the list of written paths.
    """
    if not payloads:
        raise CreateError("No payloads to encode")

    multi = len(payloads) > 1
    written: List[Path] = []

    for i, payload in enumerate(payloads, start=1):
        out = resolve_output_path(output_file, index=i if multi else None)
        out.parent.mkdir(parents=True, exist_ok=True)
        img = make_qr_image(
            payload,
            fill_color=fill_color,
            back_color=back_color,
            box_size=box_size,
            border=border,
        )
        try:
            img.save(out, format="PNG")
        except OSError as exc:
            raise CreateError(f"Failed to write {out}: {exc}") from exc
        logger.info("Wrote QR code → %s (%d bytes payload)", out, len(payload))
        written.append(out)

    return written
