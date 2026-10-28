"""Unit tests for QR creation helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qr_extractor.creator import (
    CreateError,
    create_qr_codes,
    load_payloads,
    make_qr_image,
    resolve_output_path,
)


def test_load_text():
    assert load_payloads(input_type="text", text="  hello  ") == ["hello"]


def test_load_text_empty_raises():
    with pytest.raises(CreateError):
        load_payloads(input_type="text", text="   ")


def test_load_txt_file(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("from file", encoding="utf-8")
    assert load_payloads(input_type="file", input_file=f) == ["from file"]


def test_load_json_string(tmp_path: Path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps("plain"), encoding="utf-8")
    assert load_payloads(input_type="file", input_file=f) == ["plain"]


def test_load_json_object_text(tmp_path: Path):
    f = tmp_path / "o.json"
    f.write_text(json.dumps({"text": "obj"}), encoding="utf-8")
    assert load_payloads(input_type="file", input_file=f) == ["obj"]


def test_load_json_accounts(tmp_path: Path):
    f = tmp_path / "acc.json"
    data = {
        "accounts": [
            {"raw": "otpauth://totp/x?secret=AAA"},
            {"raw": "https://example.com"},
        ]
    }
    f.write_text(json.dumps(data), encoding="utf-8")
    payloads = load_payloads(input_type="file", input_file=f)
    assert len(payloads) == 2
    assert payloads[0].startswith("otpauth://")


def test_unsupported_extension(tmp_path: Path):
    f = tmp_path / "x.csv"
    f.write_text("a", encoding="utf-8")
    with pytest.raises(CreateError, match="Unsupported"):
        load_payloads(input_type="file", input_file=f)


def test_make_qr_image():
    img = make_qr_image("test", fill_color="black", back_color="white")
    assert img.size[0] > 0
    assert img.mode == "RGB"


def test_invalid_color():
    with pytest.raises(CreateError, match="colour"):
        make_qr_image("x", fill_color="not-a-real-color-xyz")


def test_resolve_output_path_single():
    assert resolve_output_path("out").name == "out.png"
    assert resolve_output_path("out.png").name == "out.png"


def test_resolve_output_path_multi():
    assert resolve_output_path("out", index=1).name == "out_1.png"
    assert resolve_output_path("out.png", index=2).name == "out_2.png"


def test_create_writes_png(tmp_path: Path):
    out = tmp_path / "qr"
    paths = create_qr_codes(["hello"], out)
    assert len(paths) == 1
    assert paths[0].suffix == ".png"
    assert paths[0].exists()
    assert paths[0].stat().st_size > 0


def test_create_multi(tmp_path: Path):
    out = tmp_path / "multi"
    paths = create_qr_codes(["a", "b"], out)
    assert len(paths) == 2
    assert paths[0].name == "multi_1.png"
    assert paths[1].name == "multi_2.png"
