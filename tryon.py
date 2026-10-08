"""Garment cut-outs for the React try-on page.

Catalog photos show a model wearing the item. SegFormer isolates the clothes and caches a
transparent PNG in tryon_cache/. The React app (frontend/src/pages/TryOn.jsx) draws that
cut-out on the body from a webcam frame or uploaded photo.
"""
import base64
import io
import json
import os

os.environ["TRANSFORMERS_NO_TF"] = "1"
os.environ["USE_TF"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import numpy as np
from PIL import Image, ImageFilter

SEG_MODEL = "mattmdjaga/segformer_b2_clothes"
# label ids of that model: 4 upper-clothes, 5 skirt, 6 pants, 7 dress, 8 belt, 17 scarf (dupatta / pallu)
KIND_LABELS = {
    'top': (4, 17),
    'bottom': (5, 6),
    'long': (4, 7, 17),                  # kurta, tunic, jacket: long tops that reach the knees
    'full': (4, 5, 6, 7, 8, 17),         # saree, lehenga, kurta set, dress: the whole outfit
}
CACHE_DIR = "tryon_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# catalog article types that are worn as one long piece / long top
FULL_TYPES = {'Sarees', 'Lehenga Choli', 'Kurta Sets', 'Dresses', 'Salwar and Dupatta', 'Jumpsuit', 'Rompers'}
LONG_TYPES = {'Kurtas', 'Kurtis', 'Tunics', 'Nehru Jackets', 'Waistcoat', 'Dupatta'}


def kind_for(article_type, sub_category=""):
    """'top' / 'bottom' / 'long' / 'full' for a catalog article type."""
    if article_type in FULL_TYPES:
        return 'full'
    if article_type in LONG_TYPES:
        return 'long'
    if sub_category == 'Bottomwear':
        return 'bottom'
    return 'top'


class Segmenter:
    """SegFormer clothes parser (about 100 MB, downloaded once from Hugging Face)."""

    def __init__(self):
        import torch
        from transformers import AutoImageProcessor, SegformerForSemanticSegmentation
        self.torch = torch
        # CPU on purpose: a cut-out takes ~1-2 s, is cached forever, and the 4 GB GPU is already
        # shared with CLIP
        self.device = "cpu"
        self.processor = AutoImageProcessor.from_pretrained(SEG_MODEL, use_fast=False)
        self.model = SegformerForSemanticSegmentation.from_pretrained(SEG_MODEL).to(self.device).eval()

    def labels(self, pil_img):
        """(H, W) array of label ids for the image."""
        torch = self.torch
        inputs = self.processor(images=pil_img.convert("RGB"), return_tensors="pt").to(self.device)
        with torch.no_grad():
            logits = self.model(**inputs).logits
        up = torch.nn.functional.interpolate(logits, size=pil_img.size[::-1], mode="bilinear", align_corners=False)
        return up.argmax(dim=1)[0].cpu().numpy()


def _largest_clean(mask):
    """Close small holes and drop specks, so the garment is one solid shape."""
    import cv2
    m = (mask.astype(np.uint8)) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    n, comp, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n <= 1:
        return m > 0
    keep = np.zeros_like(m)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= 0.03 * stats[1:, cv2.CC_STAT_AREA].max():     # keep real parts (e.g. sleeves)
            keep[comp == i] = 255
    return keep > 0


def garment_cutout(pil_img, kind, segmenter, max_h=900):
    """Transparent PNG of just the garment worn in `pil_img`.

    Returns (RGBA image cropped to the garment, shoulder_fraction) where shoulder_fraction is the garment
    width near its top edge divided by its full width (the app uses it to match the garment to the
    wearer's shoulders / hips), or (None, None) if no such garment is found.
    """
    pil_img = pil_img.convert("RGB")
    if pil_img.height > max_h:
        pil_img = pil_img.resize((round(pil_img.width * max_h / pil_img.height), max_h), Image.LANCZOS)
    labels = segmenter.labels(pil_img)
    mask = np.isin(labels, KIND_LABELS[kind])
    if mask.sum() < 0.02 * mask.size:
        return None, None
    mask = _largest_clean(mask)
    if kind in ('full', 'long'):          # saree / kurta: keep a body-wide silhouette, not a thin drape
        import cv2
        mask = cv2.dilate(mask.astype(np.uint8), np.ones((21, 15), np.uint8), iterations=1) > 0
    ys, xs = np.where(mask)
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    alpha = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
    rgba = pil_img.copy()
    rgba.putalpha(alpha)
    rgba = rgba.crop(box)
    a = np.asarray(rgba.getchannel("A")) > 128
    top = int(a.shape[0] * 0.06) if kind != 'bottom' else 0
    rows = a[top: max(top + 2, int(a.shape[0] * 0.25))]     # upper part of the garment: shoulders / waist
    widths = rows.sum(axis=1)
    frac = float(np.clip(np.median(widths[widths > 0]) / a.shape[1], 0.25, 1.0)) if (widths > 0).any() else 0.7
    return rgba, frac


def cutout_for(row, kind, segmenter, photo_bytes):
    """Cached cut-out of one catalog item: (data URL of the PNG, shoulder fraction) or (None, None).

    `segmenter` and `photo_bytes` may be functions, so the model is only loaded and the photo only
    fetched when the cut-out is not on disk yet."""
    key = os.path.join(CACHE_DIR, f"{os.path.splitext(str(row['id']))[0]}_{kind}_v2")
    if os.path.exists(key + ".png") and os.path.exists(key + ".json"):
        with open(key + ".png", "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode(), json.load(open(key + ".json"))['sw']
    if os.path.exists(key + ".none"):
        return None, None
    seg = segmenter() if callable(segmenter) else segmenter
    data = photo_bytes() if callable(photo_bytes) else photo_bytes
    img, frac = garment_cutout(Image.open(io.BytesIO(data)), kind, seg)
    if img is None:
        open(key + ".none", "w").close()
        return None, None
    img.save(key + ".png")
    json.dump({'sw': frac}, open(key + ".json", "w"))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), frac
