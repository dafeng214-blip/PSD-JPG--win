#!/usr/bin/env python3
"""
PSD -> JPEG conversion core utilities.
"""

from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from PIL import Image
from psd_tools import PSDImage


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    """Flatten image on white background and return RGB image."""
    if image.mode == "RGB":
        return image
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    background = Image.new("RGB", image.size, (255, 255, 255))
    background.paste(image, mask=image.split()[-1])
    return background


def psd_to_jpg(psd_path: Path, output_path: Path, quality: int = 95) -> Tuple[bool, str | None]:
    """Convert single PSD file to JPEG."""
    try:
        psd = PSDImage.open(psd_path)
        # Use psd_tools composite to include nested groups/layers reliably.
        composed = psd.composite(force=True)
        if composed is None:
            return False, "无法合成 PSD 图像"
        rgb = _flatten_to_rgb(composed)
        rgb.save(output_path, "JPEG", quality=quality, optimize=True, progressive=True)
        return True, None
    except Exception as exc:  # pragma: no cover - runtime safety
        return False, str(exc)


def collect_psd_files(paths: Sequence[Path], recursive: bool = False) -> List[Path]:
    """Collect PSD files from mixed input of files and directories."""
    results: List[Path] = []
    for p in paths:
        if p.is_file() and p.suffix.lower() == ".psd" and not p.name.startswith("._"):
            results.append(p)
            continue
        if p.is_dir():
            iterator: Iterable[Path] = p.rglob("*.psd") if recursive else p.glob("*.psd")
            results.extend([f for f in iterator if not f.name.startswith("._")])
    # De-duplicate and keep stable order.
    seen = set()
    deduped: List[Path] = []
    for item in results:
        key = str(item.resolve())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
