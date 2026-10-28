"""CHEQRPlayer – decode and create QR codes (incl. otpauth / TOTP)."""

__version__ = "1.0.0"
__app_name__ = "CHEQRPlayer"
__all__ = [
    "decode_image",
    "parse_payload",
    "filter_by_qr_type",
    "format_terminal",
    "write_output",
    "create_qr_codes",
    "load_payloads",
]
