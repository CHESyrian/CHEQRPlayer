"""Unit tests for otpauth parsing, payload classification, and qr-type filtering."""

from __future__ import annotations

import pytest

from qr_extractor.parser import (
    AccountInfo,
    accounts_from_payload,
    deduplicate,
    filter_by_qr_type,
    parse_otpauth,
    parse_otpauth_migration,
    parse_payload,
)


class TestParseOtpauth:
    def test_basic_totp(self):
        uri = (
            "otpauth://totp/Example:alice@google.com"
            "?secret=JBSWY3DPEHPK3PXP&issuer=Example&algorithm=SHA1&digits=6&period=30"
        )
        info = parse_otpauth(uri)
        assert info is not None
        assert info.otp_type == "totp"
        assert info.label == "alice@google.com"
        assert info.issuer == "Example"
        assert info.secret == "JBSWY3DPEHPK3PXP"
        assert info.algorithm == "SHA1"
        assert info.digits == 6
        assert info.period == 30
        assert info.counter is None

    def test_hotp(self):
        uri = "otpauth://hotp/ACME:bob?secret=HXDMVJECJJWSRB3H&issuer=ACME&counter=42"
        info = parse_otpauth(uri)
        assert info is not None
        assert info.otp_type == "hotp"
        assert info.label == "bob"
        assert info.issuer == "ACME"
        assert info.counter == 42
        assert info.period is None

    def test_issuer_only_in_query(self):
        uri = "otpauth://totp/alice@example.com?secret=ABC123&issuer=MyIssuer"
        info = parse_otpauth(uri)
        assert info is not None
        assert info.label == "alice@example.com"
        assert info.issuer == "MyIssuer"

    def test_url_encoded_label(self):
        uri = "otpauth://totp/GitHub%3Auser%40github.com?secret=SECRET&issuer=GitHub"
        info = parse_otpauth(uri)
        assert info is not None
        assert info.label == "user@github.com"
        assert info.issuer == "GitHub"

    def test_missing_secret_returns_none(self):
        uri = "otpauth://totp/test?issuer=Foo"
        assert parse_otpauth(uri) is None

    def test_defaults(self):
        uri = "otpauth://totp/Test?secret=JBSWY3DPEHPK3PXP"
        info = parse_otpauth(uri)
        assert info is not None
        assert info.algorithm == "SHA1"
        assert info.digits == 6
        assert info.period == 30

    def test_extra_params(self):
        uri = "otpauth://totp/x?secret=AAA&foo=bar&baz=qux"
        info = parse_otpauth(uri)
        assert info is not None
        assert info.extra_params == {"foo": "bar", "baz": "qux"}


class TestParsePayload:
    def test_otpauth_happy(self):
        uri = "otpauth://totp/A:B?secret=XYZ"
        acc = parse_payload(uri, index=3)
        assert acc.payload_type == "otpauth"
        assert acc.index == 3
        assert acc.secret == "XYZ"

    def test_malformed_otpauth(self):
        uri = "otpauth://totp/no-secret"
        acc = parse_payload(uri)
        assert acc.payload_type == "otpauth"
        assert "parse_error" in (acc.extra_params or {})

    def test_raw_text(self):
        acc = parse_payload("https://example.com")
        assert acc.payload_type == "raw"
        assert acc.raw == "https://example.com"

    def test_possible_base32_secret(self):
        secret = "JBSWY3DPEHPK3PXP"
        acc = parse_payload(secret)
        assert acc.payload_type == "raw"
        assert acc.secret == secret
        assert acc.extra_params.get("inferred") == "possible_base32_secret"

    def test_empty(self):
        acc = parse_payload("   ")
        assert acc.payload_type == "unknown"

    def test_standard_forces_raw(self):
        uri = "otpauth://totp/A:B?secret=XYZ"
        acc = parse_payload(uri, qr_type="standard")
        assert acc.payload_type == "raw"
        assert acc.raw == uri
        assert acc.secret is None

    def test_totp_mode_parses_otpauth(self):
        uri = "otpauth://totp/A:B?secret=XYZ"
        acc = parse_payload(uri, qr_type="totp")
        assert acc.payload_type == "otpauth"
        assert acc.secret == "XYZ"


class TestFilterByQrType:
    def test_auto_keeps_all(self):
        accounts = [
            AccountInfo(1, "otpauth", "otpauth://totp/x?secret=AAA", secret="AAA", otp_type="totp"),
            AccountInfo(2, "raw", "https://example.com"),
        ]
        result = filter_by_qr_type(accounts, "auto")
        assert len(result) == 2

    def test_totp_keeps_only_authenticator(self):
        accounts = [
            AccountInfo(1, "otpauth", "otpauth://totp/x?secret=AAA", secret="AAA", otp_type="totp"),
            AccountInfo(2, "raw", "https://example.com"),
            AccountInfo(
                3,
                "raw",
                "JBSWY3DPEHPK3PXP",
                secret="JBSWY3DPEHPK3PXP",
                extra_params={"inferred": "possible_base32_secret"},
            ),
        ]
        result = filter_by_qr_type(accounts, "totp")
        assert len(result) == 2
        assert all(
            a.payload_type == "otpauth" or a.extra_params.get("inferred")
            for a in result
        )

    def test_standard_keeps_all(self):
        accounts = [
            AccountInfo(1, "raw", "otpauth://totp/x?secret=AAA"),
            AccountInfo(2, "raw", "https://example.com"),
        ]
        result = filter_by_qr_type(accounts, "standard")
        assert len(result) == 2


class TestDeduplicate:
    def test_removes_duplicates_preserves_order(self):
        a1 = AccountInfo(1, "raw", "aaa")
        a2 = AccountInfo(2, "raw", "bbb")
        a3 = AccountInfo(3, "raw", "aaa")
        result = deduplicate([a1, a2, a3])
        assert len(result) == 2
        assert result[0].raw == "aaa"
        assert result[1].raw == "bbb"
        assert result[0].index == 1
        assert result[1].index == 2

    def test_keeps_distinct_migration_accounts_same_raw(self):
        uri = "otpauth-migration://offline?data=xxx"
        a1 = AccountInfo(
            1, "otpauth", uri, otp_type="totp", issuer="A", label="u1", secret="SECRET1"
        )
        a2 = AccountInfo(
            2, "otpauth", uri, otp_type="totp", issuer="B", label="u2", secret="SECRET2"
        )
        result = deduplicate([a1, a2])
        assert len(result) == 2


class TestOtpauthMigration:
    # Public example from dim13/otpauth docs
    SAMPLE = (
        "otpauth-migration://offline?data="
        "CjEKCkhlbGxvId6tvu8SGEV4YW1wbGU6YWxpY2VAZ29vZ2xlLmNvbRoHRXhhbXBsZTAC"
    )

    def test_parse_known_sample(self):
        accounts = parse_otpauth_migration(self.SAMPLE)
        assert len(accounts) == 1
        acc = accounts[0]
        assert acc.payload_type == "otpauth"
        assert acc.otp_type == "totp"
        assert acc.secret == "JBSWY3DPEHPK3PXP"
        assert acc.issuer == "Example"
        assert acc.label == "alice@google.com"
        assert acc.algorithm == "SHA1"
        assert acc.digits == 6
        assert acc.period == 30
        assert acc.extra_params.get("source") == "otpauth-migration"

    def test_accounts_from_payload_expands(self):
        accounts = accounts_from_payload(self.SAMPLE)
        assert len(accounts) == 1
        assert accounts[0].secret == "JBSWY3DPEHPK3PXP"

    def test_standard_mode_keeps_raw(self):
        accounts = accounts_from_payload(self.SAMPLE, qr_type="standard")
        assert len(accounts) == 1
        assert accounts[0].payload_type == "raw"
        assert accounts[0].secret is None

    def test_not_migration_returns_empty(self):
        assert parse_otpauth_migration("otpauth://totp/x?secret=AAA") == []
