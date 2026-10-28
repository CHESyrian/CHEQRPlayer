"""Parse QR payloads, with specialised handling for otpauth:// and otpauth-migration://."""

from __future__ import annotations

import base64
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class AccountInfo:
    """Structured representation of a decoded QR payload."""

    index: int
    payload_type: str  # "otpauth" | "raw" | "unknown"
    raw: str
    # otpauth-specific (None when not applicable)
    otp_type: Optional[str] = None  # totp | hotp
    label: Optional[str] = None
    issuer: Optional[str] = None
    secret: Optional[str] = None
    algorithm: Optional[str] = None
    digits: Optional[int] = None
    period: Optional[int] = None  # TOTP
    counter: Optional[int] = None  # HOTP
    extra_params: Dict[str, str] = field(default_factory=dict)

    def to_dict(self, include_secret: bool = True) -> Dict[str, Any]:
        """Serialise to a plain dict with consistent field ordering."""
        d = {
            "index": self.index,
            "payload_type": self.payload_type,
            "raw": self.raw,
            "otp_type": self.otp_type,
            "label": self.label,
            "issuer": self.issuer,
            "secret": self.secret if include_secret else ("***" if self.secret else None),
            "algorithm": self.algorithm,
            "digits": self.digits,
            "period": self.period,
            "counter": self.counter,
            "extra_params": self.extra_params or None,
        }
        # Drop purely empty optional keys for cleaner output when not otpauth
        if self.payload_type != "otpauth":
            for k in (
                "otp_type",
                "label",
                "issuer",
                "secret",
                "algorithm",
                "digits",
                "period",
                "counter",
                "extra_params",
            ):
                d.pop(k, None)
        return d


_OTPAUTH_RE = re.compile(r"^otpauth://(totp|hotp)/(.+)$", re.IGNORECASE)
_MIGRATION_RE = re.compile(r"^otpauth-migration://", re.IGNORECASE)
_BASE32_RE = re.compile(r"^[A-Z2-7]+=*$", re.IGNORECASE)

# Google Authenticator migration protobuf enums
_MIG_ALG = {0: "SHA1", 1: "SHA1", 2: "SHA256", 3: "SHA512", 4: "MD5"}
_MIG_DIGITS = {0: 6, 1: 6, 2: 8}
_MIG_OTP = {0: "totp", 1: "hotp", 2: "totp"}


def _parse_label(path: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract issuer and account name from the path component.

    Formats seen in the wild:
      - Issuer:account@domain
      - account@domain          (issuer only in query)
      - Issuer:account
    """
    path = urllib.parse.unquote(path)
    if ":" in path:
        issuer, label = path.split(":", 1)
        return issuer.strip() or None, label.strip() or None
    return None, path.strip() or None


def parse_otpauth(uri: str) -> Optional[AccountInfo]:
    """
    Parse an otpauth:// URI into an AccountInfo.

    Returns None if the URI is malformed beyond recovery.
    Note: otpauth secrets are base32-encoded, not encrypted; this extracts
    the structured fields (secret, issuer, label, algorithm, digits, period/counter).
    """
    m = _OTPAUTH_RE.match(uri.strip())
    if not m:
        return None

    otp_type = m.group(1).lower()
    rest = m.group(2)

    if "?" in rest:
        path, query = rest.split("?", 1)
    else:
        path, query = rest, ""

    issuer_from_path, label = _parse_label(path)
    params = urllib.parse.parse_qs(query, keep_blank_values=False)

    def first(key: str, default: Optional[str] = None) -> Optional[str]:
        vals = params.get(key)
        return vals[0] if vals else default

    secret = first("secret")
    if not secret:
        return None

    algorithm = (first("algorithm") or "SHA1").upper()
    digits_str = first("digits", "6")
    try:
        digits = int(digits_str)
    except ValueError:
        digits = 6

    period: Optional[int] = None
    counter: Optional[int] = None
    if otp_type == "totp":
        try:
            period = int(first("period", "30"))
        except ValueError:
            period = 30
    else:  # hotp
        try:
            counter = int(first("counter", "0"))
        except ValueError:
            counter = 0

    issuer = first("issuer") or issuer_from_path

    known = {"secret", "algorithm", "digits", "period", "counter", "issuer"}
    extra = {k: v[0] for k, v in params.items() if k not in known}

    return AccountInfo(
        index=0,
        payload_type="otpauth",
        raw=uri,
        otp_type=otp_type,
        label=label,
        issuer=issuer,
        secret=secret,
        algorithm=algorithm,
        digits=digits,
        period=period,
        counter=counter,
        extra_params=extra,
    )


def _read_varint(buf: bytes, i: int) -> Tuple[int, int]:
    """Read a protobuf varint; return (value, new_offset)."""
    result = 0
    shift = 0
    while i < len(buf):
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, i
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")
    raise ValueError("truncated varint")


def _parse_protobuf_fields(buf: bytes) -> List[Tuple[int, int, Any]]:
    """
    Minimal protobuf wire-format decoder.

    Returns list of (field_number, wire_type, value) where value is int for
    varints or bytes for length-delimited fields.
    """
    i = 0
    fields: List[Tuple[int, int, Any]] = []
    while i < len(buf):
        key, i = _read_varint(buf, i)
        field_num = key >> 3
        wire = key & 7
        if wire == 0:  # varint
            val, i = _read_varint(buf, i)
            fields.append((field_num, wire, val))
        elif wire == 1:  # 64-bit
            fields.append((field_num, wire, buf[i : i + 8]))
            i += 8
        elif wire == 2:  # length-delimited
            length, i = _read_varint(buf, i)
            fields.append((field_num, wire, buf[i : i + length]))
            i += length
        elif wire == 5:  # 32-bit
            fields.append((field_num, wire, buf[i : i + 4]))
            i += 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
    return fields


def _b32_secret(secret_bytes: bytes) -> str:
    """Encode raw secret bytes as unpadded base32 (otpauth convention)."""
    return base64.b32encode(secret_bytes).decode("ascii").rstrip("=")


def _migration_otp_to_account(
    params: bytes,
    *,
    source_uri: str,
    index: int,
) -> Optional[AccountInfo]:
    """Parse one OtpParameters message into AccountInfo."""
    try:
        fields = _parse_protobuf_fields(params)
    except ValueError:
        return None

    secret_b: Optional[bytes] = None
    name: Optional[str] = None
    issuer: Optional[str] = None
    algorithm = "SHA1"
    digits = 6
    otp_type = "totp"
    counter: Optional[int] = None

    for field_num, wire, val in fields:
        if field_num == 1 and wire == 2:
            secret_b = val
        elif field_num == 2 and wire == 2:
            name = val.decode("utf-8", errors="replace")
        elif field_num == 3 and wire == 2:
            issuer = val.decode("utf-8", errors="replace")
        elif field_num == 4 and wire == 0:
            algorithm = _MIG_ALG.get(val, "SHA1")
        elif field_num == 5 and wire == 0:
            digits = _MIG_DIGITS.get(val, 6)
        elif field_num == 6 and wire == 0:
            otp_type = _MIG_OTP.get(val, "totp")
        elif field_num == 7 and wire == 0:
            counter = val

    if not secret_b:
        return None

    label = name
    # name often embeds "Issuer:account" (with or without a separate issuer field)
    if name and ":" in name:
        path_issuer, path_label = _parse_label(name)
        if not issuer:
            issuer, label = path_issuer, path_label
        elif path_issuer and path_issuer.lower() == issuer.lower():
            label = path_label

    period = 30 if otp_type == "totp" else None
    if otp_type == "hotp" and counter is None:
        counter = 0

    return AccountInfo(
        index=index,
        payload_type="otpauth",
        raw=source_uri,
        otp_type=otp_type,
        label=label,
        issuer=issuer,
        secret=_b32_secret(secret_b),
        algorithm=algorithm,
        digits=digits,
        period=period,
        counter=counter,
        extra_params={"source": "otpauth-migration"},
    )


def parse_otpauth_migration(uri: str) -> List[AccountInfo]:
    """
    Decode a Google Authenticator export URI
    (``otpauth-migration://offline?data=...``) into individual accounts.

    The ``data`` query parameter is base64-encoded protobuf (MigrationPayload).
    Returns an empty list if the URI is not a migration link or cannot be parsed.
    """
    uri = uri.strip()
    if not _MIGRATION_RE.match(uri):
        return []

    parsed = urllib.parse.urlparse(uri)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
    data_vals = qs.get("data")
    if not data_vals:
        return []

    data_b64 = data_vals[0]
    raw: Optional[bytes] = None
    for pad in ("", "=", "==", "==="):
        try:
            raw = base64.b64decode(data_b64 + pad, validate=False)
            break
        except Exception:
            continue
    if not raw:
        return []

    try:
        top = _parse_protobuf_fields(raw)
    except ValueError:
        return []

    accounts: List[AccountInfo] = []
    batch_meta: Dict[str, str] = {}
    for field_num, wire, val in top:
        if field_num == 1 and wire == 2:
            acc = _migration_otp_to_account(val, source_uri=uri, index=len(accounts) + 1)
            if acc is not None:
                accounts.append(acc)
        elif field_num == 2 and wire == 0:
            batch_meta["migration_version"] = str(val)
        elif field_num == 3 and wire == 0:
            batch_meta["batch_size"] = str(val)
        elif field_num == 4 and wire == 0:
            batch_meta["batch_index"] = str(val)
        elif field_num == 5 and wire == 0:
            batch_meta["batch_id"] = str(val)

    if batch_meta:
        for acc in accounts:
            acc.extra_params = {**acc.extra_params, **batch_meta}

    return accounts


def parse_payload(raw: str, index: int = 0, *, qr_type: str = "auto") -> AccountInfo:
    """
    Detect payload type and parse a *single* account.

    For ``otpauth-migration://`` URIs prefer :func:`accounts_from_payload`,
    which expands all exported accounts. This function returns a single
    summary row (first account, or a raw fallback).

    qr_type:
      - "auto"     : special-case otpauth:// and migration, otherwise raw
      - "totp"     : prefer authenticator parsing; treat plausible base32 as secret
      - "standard" : always treat as raw text (no otpauth expansion)
    """
    accounts = accounts_from_payload(raw, qr_type=qr_type)
    if not accounts:
        return AccountInfo(index=index, payload_type="unknown", raw=raw.strip())
    acc = accounts[0]
    acc.index = index
    return acc


def accounts_from_payload(raw: str, *, qr_type: str = "auto") -> List[AccountInfo]:
    """
    Parse one QR payload string into zero or more AccountInfo rows.

    Expands Google Authenticator migration QRs into one row per exported
    account. Ordinary otpauth:// and raw payloads yield a single-element list.
    """
    raw = raw.strip()
    if not raw:
        return [AccountInfo(index=0, payload_type="unknown", raw=raw)]

    if qr_type == "standard":
        return [AccountInfo(index=0, payload_type="raw", raw=raw)]

    # Google Authenticator export (may contain many accounts)
    if _MIGRATION_RE.match(raw):
        accounts = parse_otpauth_migration(raw)
        if accounts:
            return accounts
        return [
            AccountInfo(
                index=0,
                payload_type="raw",
                raw=raw,
                extra_params={"parse_error": "malformed otpauth-migration URI"},
            )
        ]

    # Single otpauth:// URI
    if raw.lower().startswith("otpauth://"):
        info = parse_otpauth(raw)
        if info is not None:
            return [info]
        return [
            AccountInfo(
                index=0,
                payload_type="otpauth",
                raw=raw,
                extra_params={"parse_error": "malformed otpauth URI"},
            )
        ]

    # Bare base32 secret heuristic (useful in totp mode and auto)
    if _BASE32_RE.fullmatch(raw) and len(raw) >= 16:
        return [
            AccountInfo(
                index=0,
                payload_type="raw",
                raw=raw,
                secret=raw,
                extra_params={"inferred": "possible_base32_secret"},
            )
        ]

    return [AccountInfo(index=0, payload_type="raw", raw=raw)]


def filter_by_qr_type(accounts: List[AccountInfo], qr_type: str) -> List[AccountInfo]:
    """
    Post-filter accounts according to the requested QR type.

    - auto     : keep everything
    - totp     : keep only otpauth entries and inferred base32 secrets
    - standard : keep everything (already forced to raw by parse_payload)
    """
    if qr_type == "auto" or qr_type == "standard":
        return accounts

    # totp mode: retain usable authenticator data
    kept: List[AccountInfo] = []
    for acc in accounts:
        if acc.payload_type == "otpauth" and acc.secret:
            kept.append(acc)
        elif acc.extra_params.get("inferred") == "possible_base32_secret":
            kept.append(acc)
        elif acc.payload_type == "otpauth":
            # malformed otpauth still reported so the user sees the problem
            kept.append(acc)
    return kept


def deduplicate(accounts: List[AccountInfo]) -> List[AccountInfo]:
    """
    Remove duplicate accounts, preserving order.

    otpauth rows are keyed by (otp_type, issuer, label, secret) so that
    accounts expanded from a single otpauth-migration:// QR are kept.
    Other rows are keyed by the full raw payload string.
    """
    seen: set[str] = set()
    unique: List[AccountInfo] = []
    for acc in accounts:
        if acc.payload_type == "otpauth" and acc.secret:
            key = f"otpauth|{acc.otp_type}|{acc.issuer}|{acc.label}|{acc.secret}"
        else:
            key = f"raw|{acc.raw}"
        if key not in seen:
            seen.add(key)
            unique.append(acc)
    for i, acc in enumerate(unique, start=1):
        acc.index = i
    return unique
