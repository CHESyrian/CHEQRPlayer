"""Tests for output formatters."""

from __future__ import annotations

import json
from io import StringIO

from qr_extractor.output import format_terminal, write_csv, write_json
from qr_extractor.parser import AccountInfo


def _sample() -> AccountInfo:
    return AccountInfo(
        index=1,
        payload_type="otpauth",
        raw="otpauth://totp/Ex:alice?secret=SEC&issuer=Ex",
        otp_type="totp",
        label="alice",
        issuer="Ex",
        secret="SEC",
        algorithm="SHA1",
        digits=6,
        period=30,
    )


def test_format_terminal_shows_secret():
    text = format_terminal([_sample()], show_secrets=True)
    assert "Secret   : SEC" in text
    assert "alice" in text


def test_format_terminal_hides_secret():
    text = format_terminal([_sample()], show_secrets=False)
    assert "***REDACTED***" in text
    assert "SEC" not in text


def test_write_json():
    buf = StringIO()
    write_json([_sample()], buf, show_secrets=True)
    data = json.loads(buf.getvalue())
    assert data["count"] == 1
    assert data["accounts"][0]["secret"] == "SEC"
    assert data["accounts"][0]["label"] == "alice"


def test_write_json_redacted():
    buf = StringIO()
    write_json([_sample()], buf, show_secrets=False)
    data = json.loads(buf.getvalue())
    assert data["accounts"][0]["secret"] == "***"


def test_write_csv():
    buf = StringIO()
    write_csv([_sample()], buf, show_secrets=True)
    content = buf.getvalue()
    assert "index,payload_type" in content
    assert "SEC" in content
