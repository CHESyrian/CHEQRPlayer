# CHEQRPlayer

A production-ready command-line utility to **read** (decode) and **write** (create) QR codes. It supports standard payloads, **TOTP/HOTP authenticator URIs** (`otpauth://` — Google Authenticator, Authy, Microsoft Authenticator, etc.), and **Google Authenticator export QRs** (`otpauth-migration://offline?data=…`).

## Commands

```text
CHEQRPlayer read  [options]   # decode QR codes from an image
CHEQRPlayer write [options]   # create QR-code PNG image(s)
```

| Command | Purpose |
|---------|---------|
| `read` | Decode one or more QR codes from an image; special-cases `otpauth://` |
| `write` | Generate PNG QR image(s) from text or a `.txt` / `.json` file |

> **Note on “decryption”:** Authenticator QR codes are not encrypted. The secret is base32-encoded in the URI. This tool parses and extracts those fields.

## Features

- Unified CLI: `CHEQRPlayer read | write`
- Multiple QR codes per image
- Explicit QR type selection on read (`--qr-type auto|standard|totp`)
- Robust decoding via OpenCV (grayscale, adaptive/Otsu thresholding, upscaling)
- Full otpauth parsing: type, label, issuer, secret, algorithm, digits, period/counter
- Google Authenticator migration QR support (expands one export into many accounts)
- Create coloured QR PNGs from text, `.txt`, or `.json` (incl. accounts export)
- Terminal / JSON / CSV output; optional `--hide-secrets`
- Local-only processing

## Installation

This project uses **[uv](https://docs.astral.sh/uv/)** for environment and dependency management.

```bash
# Create/sync a project virtual environment and install the package (editable)
uv sync

# Or install with development extras (pytest, etc.)
uv sync --extra dev
```

Requires **Python ≥ 3.14**, `opencv-contrib-python`, Pillow, and `qrcode`.

After `uv sync`, the commands `CHEQRPlayer` and `cheqrplayer` are available via:

```bash
uv run CHEQRPlayer --help
# or activate the env:
source .venv/bin/activate   # Linux/macOS
CHEQRPlayer --help
```

## Quick wrapper (`bin/CHEQRPlayer`)

```bash
chmod +x bin/CHEQRPlayer
ln -s "$(pwd)/bin/CHEQRPlayer" ~/bin/CHEQRPlayer

CHEQRPlayer read  --image shot.png --output-type terminal
CHEQRPlayer write --input-type text --text "Hello" --output-file hello
```

## Usage – read

```text
CHEQRPlayer read --image <path> --output-type <terminal|file> [options]
```

| Flag | Description |
|------|-------------|
| `--image PATH` | Input image (PNG, JPG, BMP, TIFF, WEBP) **required** |
| `--output-type {terminal,file}` | Where to write results **required** |
| `--qr-type {auto,standard,totp}` | How to interpret payloads (default: `auto`) |
| `--output-file PATH` | Destination when `--output-type=file` |
| `--format {json,csv}` | File format (default: `json`) |
| `-v, --verbose` | Debug logging |
| `--hide-secrets` | Redact secrets in output |

### Exit codes (read)

| Code | Meaning |
|------|---------|
| 0 | Success (at least one account) |
| 1 | No matching QR / accounts found |
| 2 | I/O or format error |
| 3 | Failed to write output file |

### Examples (read)

```bash
CHEQRPlayer read --image screenshots/auth.png --output-type terminal
CHEQRPlayer read --image shot.png --qr-type totp --output-type terminal
CHEQRPlayer read --image shot.png --qr-type standard --output-type terminal
CHEQRPlayer read --image shot.png --output-type file --output-file accounts.json
CHEQRPlayer read --image shot.png --output-type file --output-file out.csv --format csv --hide-secrets
```

## Usage – write

```text
CHEQRPlayer write --input-type <text|file> --output-file <name> [options]
```

| Flag | Description |
|------|-------------|
| `--input-type {text,file}` | Source of payload **required** |
| `--text STRING` | Payload when `--input-type=text` |
| `--input-file PATH` | `.txt` or `.json` when `--input-type=file` |
| `--color COLOR` | Foreground (name or `#RRGGBB`, default: black) |
| `--background COLOR` | Background (default: white) |
| `--output-file NAME` | Base name → `NAME.png` (or `NAME_1.png`, …) **required** |
| `--box-size N` | Pixels per module (default: 10) |
| `--border N` | Quiet-zone modules (default: 4) |

JSON input may be a plain string, `{text|payload|raw}`, or a CHEQRPlayer accounts export (one QR per account).

### Examples (write)

```bash
CHEQRPlayer write --input-type text --text "Hello World" --output-file hello
CHEQRPlayer write --input-type text --text "otpauth://totp/..." --color navy --output-file totp
CHEQRPlayer write --input-type file --input-file notes.txt --output-file notes
CHEQRPlayer write --input-type file --input-file accounts.json --color "#1a73e8" --output-file acc
```

## Security & privacy

- Secrets are shown by default in read output (they are the payload). Use `--hide-secrets` when sharing.
- Logging never emits secrets unless `-v` is set.
- All processing is local; nothing is uploaded.

## Project layout

```
CHEQRPlayer/
├── bin/
│   └── CHEQRPlayer    # unified wrapper: read | write
├── src/qr_extractor/
│   ├── player.py       # unified CLI entry-point
│   ├── cli.py          # read subcommand
│   ├── create_cli.py   # write subcommand
│   ├── decoder.py
│   ├── parser.py
│   ├── output.py
│   └── creator.py
├── tests/
├── samples/
├── pyproject.toml
├── uv.lock
└── README.md
```

## Running tests

```bash
uv sync --extra dev
uv run pytest -q
```

## License

MIT
