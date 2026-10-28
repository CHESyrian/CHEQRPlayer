"""Image loading and QR-code decoding with optional pre-processing."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


class DecodeError(Exception):
    """Raised when an image cannot be decoded or no QR codes are found."""


def _load_image(path: Path) -> np.ndarray:
    """Load image as BGR numpy array; raise DecodeError on failure."""
    if not path.exists():
        raise DecodeError(f"File does not exist: {path}")
    if not path.is_file():
        raise DecodeError(f"Not a regular file: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise DecodeError(
            f"Unsupported format '{path.suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    # Try OpenCV first (fast path for most formats)
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is not None:
        return img

    # Fallback via Pillow (handles more edge-case TIFFs, etc.)
    try:
        with Image.open(path) as pil:
            pil = pil.convert("RGB")
            arr = np.array(pil)
            # RGB → BGR for OpenCV consistency
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    except Exception as exc:
        raise DecodeError(f"Unable to open image: {exc}") from exc


def _glare_reduce(gray: np.ndarray) -> np.ndarray:
    """
    Homomorphic-style glare reduction: divide by a large Gaussian blur.
    Helps when a phone screen reflection washes out the centre of a QR.
    """
    blur = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), 30)
    # avoid divide-by-zero
    blur = np.maximum(blur, 1.0)
    divided = cv2.divide(gray.astype(np.float32), blur, scale=128.0)
    return np.clip(divided, 0, 255).astype(np.uint8)


def _preprocess_variants(img: np.ndarray) -> List[np.ndarray]:
    """
    Generate pre-processed versions that help with low contrast, glare,
    small modules, and uneven lighting (e.g. phone photos of authenticator QRs).
    """
    variants: List[np.ndarray] = [img]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    variants.append(gray)

    # Adaptive thresholds — mean C=2 often recovers glare-damaged codes
    for method, tag in (
        (cv2.ADAPTIVE_THRESH_MEAN_C, "mean"),
        (cv2.ADAPTIVE_THRESH_GAUSSIAN_C, "gauss"),
    ):
        for block in (11, 21, 31, 41):
            for C in (2, 5, 10):
                try:
                    ath = cv2.adaptiveThreshold(
                        gray, 255, method, cv2.THRESH_BINARY, block, C
                    )
                    variants.append(ath)
                    variants.append(255 - ath)
                except Exception:
                    pass

    # Otsu + inverse
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(otsu)
    variants.append(255 - otsu)

    # CLAHE local contrast
    try:
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        cl = clahe.apply(gray)
        variants.append(cl)
        _, cl_otsu = cv2.threshold(cl, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(cl_otsu)
    except Exception:
        pass

    # Glare / reflection reduction
    try:
        reduced = _glare_reduce(gray)
        variants.append(reduced)
        _, r_otsu = cv2.threshold(reduced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(r_otsu)
        variants.append(255 - r_otsu)
        try:
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            variants.append(clahe.apply(reduced))
        except Exception:
            pass
    except Exception:
        pass

    # Cap brightest pixels then re-normalize (soft glare clip)
    for pct in (95, 98):
        try:
            thr = float(np.percentile(gray, pct))
            capped = gray.copy()
            capped[capped > thr] = int(thr)
            capped = cv2.normalize(capped, None, 0, 255, cv2.NORM_MINMAX).astype(
                np.uint8
            )
            variants.append(capped)
            _, c_otsu = cv2.threshold(
                capped, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            variants.append(c_otsu)
        except Exception:
            pass

    # Upscale — helps small modules and phone photos
    h, w = gray.shape[:2]
    for scale in (1.5, 2.0, 3.0):
        if max(h, w) * scale > 2400:
            continue
        try:
            up = cv2.resize(
                gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
            )
            variants.append(up)
            _, up_otsu = cv2.threshold(
                up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            variants.append(up_otsu)
            # adaptive on upscaled
            ath = cv2.adaptiveThreshold(
                up, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 21, 2
            )
            variants.append(ath)
        except Exception:
            pass

    return variants


def _decode_with_opencv(img: np.ndarray) -> List[str]:
    """Return list of decoded strings using OpenCV's multi detector."""
    detector = cv2.QRCodeDetector()
    try:
        # OpenCV ≥ 4.5
        ok, decoded_info, points, _ = detector.detectAndDecodeMulti(img)
        if ok and decoded_info:
            return [s for s in decoded_info if s]
    except Exception as exc:
        logger.debug("detectAndDecodeMulti failed: %s", exc)

    # Fallback single
    try:
        data, _, _ = detector.detectAndDecode(img)
        if data:
            return [data]
    except Exception as exc:
        logger.debug("detectAndDecode failed: %s", exc)

    return []


def decode_image(
    path: Path | str,
    *,
    max_attempts: int = 0,
    verbose: bool = False,
) -> List[str]:
    """
    Decode all QR codes found in the image at *path*.

    Returns a list of raw payload strings (may be empty).
    Raises DecodeError only for I/O / format problems; an image with
    zero QR codes simply returns an empty list.

    *max_attempts* limits how many pre-process variants are tried.
    ``0`` (default) means try all generated variants.
    """
    path = Path(path)
    img = _load_image(path)
    logger.info("Loaded image %s shape=%s", path.name, img.shape)

    payloads: List[str] = []
    seen: set[str] = set()

    variants = _preprocess_variants(img)
    limit = len(variants) if max_attempts <= 0 else min(max_attempts, len(variants))

    for i, variant in enumerate(variants[:limit]):
        found = _decode_with_opencv(variant)
        for p in found:
            if p not in seen:
                seen.add(p)
                payloads.append(p)
                if verbose:
                    logger.debug("Decoded (variant %d): %s…", i, p[:60])
        # Early exit once we have at least one payload from a successful variant
        if payloads:
            break

    if not payloads:
        logger.warning("No QR codes detected in %s", path)
    else:
        logger.info("Found %d unique QR payload(s)", len(payloads))

    return payloads
