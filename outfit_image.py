"""Compose ONE outfit picture (top + bottom + footwear) from three catalog photos.

The catalog photos are full-body model shots, so each one is cleaned and trimmed to its garment first:
the top keeps the torso (no head, no legs), the bottom keeps the waist-to-ankle part, and the shoes
are scaled to sit under the legs. Everything is stacked on one white card.
"""
import numpy as np
from PIL import Image

LONG_TOPS = {'Kurtas', 'Kurtis', 'Tunics', 'Dresses', 'Nehru Jackets', 'Lehenga Choli', 'Rompers', 'Dupatta'}
# bottoms whose catalog photo is worn under a long top: skip more of the photo to avoid the top's hem
UNDER_LONG_TOP = {'Churidar', 'Salwar', 'Patiala', 'Salwar and Dupatta', 'Leggings', 'Jeggings', 'Tights'}
SHORT_BOTTOMS = {'Skirts', 'Shorts', 'Capris'}


def _cleaned(img, tol=34):
    """Replace the studio background (colour of the border) by pure white."""
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    fg = (np.abs(a - bg).sum(axis=2) > tol)
    out = np.where(fg[..., None], a, 255).astype(np.uint8)
    return Image.fromarray(out)


def _trim(img, pad=2):
    """Crop away the white background."""
    a = np.asarray(img.convert("RGB"))
    mask = (a < 238).any(axis=2)
    if not mask.any():
        return img
    ys, xs = np.where(mask)
    return img.crop((max(xs.min() - pad, 0), max(ys.min() - pad, 0),
                     min(xs.max() + 1 + pad, img.width), min(ys.max() + 1 + pad, img.height)))


def _rows(img, a, b):
    return img.crop((0, int(img.height * a), img.width, int(img.height * b)))


def _fade_bottom(img, px):
    """RGBA copy whose lowest `px` rows fade out, so the cut edge blends into what is below."""
    rgba = img.convert("RGBA")
    alpha = np.full((img.height, img.width), 255, dtype=np.uint8)
    px = min(px, img.height // 2)
    if px > 0:
        alpha[-px:] = np.linspace(255, 0, px).astype(np.uint8)[:, None]
    rgba.putalpha(Image.fromarray(alpha))
    return rgba


def compose_outfit(top, bottom, shoes, top_type="", bottom_type="", size=(420, 640)):
    """top / bottom / shoes: PIL images (ideally AI-upscaled). Returns one PIL image (the outfit card)."""
    t = _trim(_cleaned(top))
    t = _trim(_rows(t, 0.22, 0.84 if top_type in LONG_TOPS else 0.62))      # no head, no legs
    b = _trim(_cleaned(bottom))
    start = 0.0 if bottom_type in SHORT_BOTTOMS else (0.62 if bottom_type in UNDER_LONG_TOP else 0.40)
    b = _trim(_rows(b, start, 0.93))
    s = _trim(_cleaned(shoes))

    # Photos are framed differently (some zoomed in), so keep the bottom in proportion to the top:
    # legs of trousers span ~65-90% of a shirt's width (sleeves included), churidar / leggings less.
    lo, hi = (0.40, 0.70) if bottom_type in UNDER_LONG_TOP else (0.65, 0.90)
    ratio = b.width / max(t.width, 1)
    if ratio > hi or ratio < lo:
        k = (hi if ratio > hi else lo) / ratio
        b = b.resize((max(1, int(b.width * k)), max(1, int(b.height * k))), Image.LANCZOS)

    # natural scale for clothes (all photos show a full body at a similar size); shoes sit under the legs
    s_w = int(max(t.width, b.width) * 0.60)
    s = s.resize((s_w, max(1, int(s.height * s_w / s.width))), Image.LANCZOS)

    overlap = int(t.height * 0.05)                   # top tucks slightly into the bottom
    gap_bs = int(b.height * 0.03)
    total_h = t.height - overlap + b.height + gap_bs + s.height
    total_w = max(t.width, b.width, s.width)
    card = Image.new("RGBA", (total_w, total_h), "white")
    y_b = t.height - overlap
    card.alpha_composite(b.convert("RGBA"), ((total_w - b.width) // 2, y_b))
    card.alpha_composite(_fade_bottom(t, max(4, overlap + 2)), ((total_w - t.width) // 2, 0))
    card.alpha_composite(s.convert("RGBA"), ((total_w - s.width) // 2, y_b + b.height + gap_bs))
    card = card.convert("RGB")

    W, H = size
    k = min((W - 40) / card.width, (H - 40) / card.height)
    card = card.resize((max(1, int(card.width * k)), max(1, int(card.height * k))), Image.LANCZOS)
    out = Image.new("RGB", size, "white")
    out.paste(card, ((W - card.width) // 2, (H - card.height) // 2))
    return out


def _fit(img, box_w, box_h):
    """Scale img to fit inside box (keeping proportions) and return it."""
    k = min(box_w / img.width, box_h / img.height)
    return img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS)


def _font(size):
    from PIL import ImageFont
    for name in ("segoeuib.ttf", "segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


# part of the photo that is the accessory: dupattas / jackets are shown on a model, so skip head and legs
_BOARD_CROPS = {'Dupatta': (0.12, 0.88), 'Jacket': (0.14, 0.80)}
_BOARD_WEIGHT = {'Dupatta': 1.7, 'Jacket': 1.5}      # taller tile than the small accessories


def compose_board(main, extras, size=(960, 1120), labels=None):
    """A "complete the look" board: the hero piece (saree / lehenga / kurta set, on the model) large on
    the left, the accessories (dupatta, jewellery, clutch, footwear ...) in labelled tiles on the right.
    `extras`: list of PIL images; `labels`: one caption per extra."""
    from PIL import ImageDraw
    W, H = size
    pad, gap, radius = 20, 16, 22
    out = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(out)
    border = (226, 222, 216)
    left_w = int(W * 0.60) - pad

    draw.rounded_rectangle([pad, pad, pad + left_w, H - pad], radius, fill="white", outline=border, width=2)
    m = _fit(_trim(_cleaned(main)), left_w - 2 * 28, H - 2 * pad - 2 * 28)
    out.paste(m, (pad + (left_w - m.width) // 2, (H - m.height) // 2))

    if extras:
        x0 = pad + left_w + gap
        x1 = W - pad
        labels = labels or [""] * len(extras)
        weights = [_BOARD_WEIGHT.get(lbl, 1.0) for lbl in labels]
        avail = H - 2 * pad - gap * (len(extras) - 1)
        y = pad
        for img, lbl, wgt in zip(extras, labels, weights):
            th = int(avail * wgt / sum(weights))
            draw.rounded_rectangle([x0, y, x1, y + th], radius, fill="white", outline=border, width=2)
            piece = _cleaned(img)
            if lbl in _BOARD_CROPS:
                piece = _rows(piece, *_BOARD_CROPS[lbl])
            piece = _fit(_trim(piece), (x1 - x0) - 2 * 22, th - 2 * 22 - 26)
            out.paste(piece, (x0 + ((x1 - x0) - piece.width) // 2, y + 20 + (th - 40 - 26 - piece.height) // 2 + 0))
            draw.text(((x0 + x1) // 2, y + th - 24), lbl.upper(), fill=(120, 113, 108), font=_font(21), anchor="mm")
            y += th + gap
    return out
