"""Pillow drawing — replaces every cv2 draw call. Operates on PIL RGB images.

Colours are RGB (Pillow), not BGR (OpenCV).
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont

GREEN = (0, 255, 0)
RED = (255, 0, 0)
BLACK = (0, 0, 0)

try:
    _FONT = ImageFont.truetype("arial.ttf", 14)
    _BIG = ImageFont.truetype("arialbd.ttf", 40)
except Exception:  # noqa: BLE001
    _FONT = ImageFont.load_default()
    _BIG = ImageFont.load_default()


def _pts(poly):
    return [(int(x), int(y)) for x, y in poly]


def draw_zone(img: Image.Image, poly, triggered: bool) -> Image.Image:
    """Semi-transparent fill + outline. Green normally, red when triggered."""
    if poly is None:
        return img
    color = RED if triggered else GREEN
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).polygon(_pts(poly), fill=color + (40,))  # ~0.16 alpha
    out = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    ring = _pts(poly)
    ImageDraw.Draw(out).line(ring + [ring[0]], fill=color, width=2)
    return out


def draw_feet(img: Image.Image, feet) -> None:
    """feet: iterable of ((x, y), inside_bool). Draws in place."""
    d = ImageDraw.Draw(img)
    for (x, y), inside in feet:
        color = RED if inside else GREEN
        d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=color)


def draw_ppe(img: Image.Image, dets) -> None:
    """Draw PPE boxes + labels in place. NO-* / Fall classes are red, rest green."""
    d = ImageDraw.Draw(img)
    for det in dets:
        x1, y1, x2, y2 = map(int, det["bbox"])
        name, conf = det["name"], det["conf"]
        bad = name.startswith("NO-") or name == "Fall-Detected"
        color = RED if bad else GREEN
        d.rectangle([x1, y1, x2, y2], outline=color, width=2)
        label = f"{name} {conf:.2f}"
        tb = d.textbbox((x1, max(0, y1 - 16)), label, font=_FONT)
        d.rectangle([tb[0], tb[1], tb[2] + 2, tb[3]], fill=color)
        d.text((x1 + 1, max(0, y1 - 16)), label, fill=BLACK, font=_FONT)


# COCO 17-keypoint skeleton edges (for DEBUG_POSE mode)
_SKELETON = [
    (5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16), (0, 1), (0, 2), (1, 3), (2, 4),
]
_CYAN = (0, 220, 255)
_VIS = 0.3


def draw_skeleton(img: Image.Image, persons) -> None:
    """Draw full pose skeleton (bones + keypoints) in place — debug view."""
    d = ImageDraw.Draw(img)
    for p in persons:
        kp = p["keypoints"]
        for a, b in _SKELETON:
            if kp[a, 2] > _VIS and kp[b, 2] > _VIS:
                d.line([(kp[a, 0], kp[a, 1]), (kp[b, 0], kp[b, 1])], fill=_CYAN, width=2)
        for x, y, c in kp:
            if c > _VIS:
                d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=_CYAN)


def no_signal_image(w: int = 640, h: int = 480) -> Image.Image:
    img = Image.new("RGB", (w, h), (14, 14, 14))
    d = ImageDraw.Draw(img)
    for x in range(0, w, 40):
        d.line([(x, 0), (x, h)], fill=(28, 28, 28))
    for y in range(0, h, 40):
        d.line([(0, y), (w, y)], fill=(28, 28, 28))
    text = "NO SIGNAL"
    tb = d.textbbox((0, 0), text, font=_BIG)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    d.text(((w - tw) // 2, (h - th) // 2), text, fill=(52, 231, 255), font=_BIG)
    return img
