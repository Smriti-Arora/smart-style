"""Zero-shot understanding of an uploaded clothing photo with CLIP.

The trained EfficientNet classifier heads are collapsed (they predict "Tshirts" for everything),
so the item type / colour of an upload are detected with CLIP instead.
CLIP weights come from the local HuggingFace cache (openai/clip-vit-base-patch32).
"""
import os

os.environ["TRANSFORMERS_NO_TF"] = "1"
os.environ["USE_TF"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import numpy as np
import torch
from transformers import CLIPModel, CLIPProcessor

MODEL_NAME = "openai/clip-vit-base-patch32"

# (text prompt, outfit group, catalog articleType name)
ITEMS = [
    ("a t-shirt", "upper", "Tshirts"),
    ("a shirt with collar and buttons", "upper", "Shirts"),
    ("a women's top or blouse", "upper", "Tops"),
    ("a kurta", "upper", "Kurtas"),
    ("a sweatshirt or hoodie", "upper", "Sweatshirts"),
    ("a sweater", "upper", "Sweaters"),
    ("a jacket", "upper", "Jackets"),
    ("a pair of jeans", "lower", "Jeans"),
    ("a pair of trousers", "lower", "Trousers"),
    ("a pair of shorts", "lower", "Shorts"),
    ("a skirt", "lower", "Skirts"),
    ("a pair of track pants", "lower", "Track Pants"),
    ("a pair of leggings", "lower", "Leggings"),
    ("a pair of casual shoes", "footwear", "Casual Shoes"),
    ("a pair of formal shoes", "footwear", "Formal Shoes"),
    ("a pair of sports shoes", "footwear", "Sports Shoes"),
    ("a pair of sandals", "footwear", "Sandals"),
    ("a pair of flip flops", "footwear", "Flip Flops"),
    ("a pair of high heels", "footwear", "Heels"),
    ("a pair of flat shoes", "footwear", "Flats"),
    ("a dress", "dress", "Dresses"),
    ("a saree", "dress", "Sarees"),
    ("a wrist watch", "other", "Watches"),
    ("a handbag", "other", "Handbags"),
    ("a pair of sunglasses", "other", "Sunglasses"),
    ("a belt", "other", "Belts"),
    ("a wallet", "other", "Wallets"),
    ("a backpack", "other", "Backpacks"),
    ("a perfume bottle", "other", "Perfume and Body Mist"),
]

COLOURS = ["Black", "White", "Blue", "Navy Blue", "Red", "Green", "Grey", "Brown", "Pink",
           "Yellow", "Beige", "Maroon", "Orange", "Purple", "Olive", "Cream", "Teal", "Khaki"]

class Detector:
    def __init__(self):
        self.model = CLIPModel.from_pretrained(MODEL_NAME).eval()
        # Slow processor: this CLIP checkpoint has no _valid_processor_keys on the fast class.
        self.processor = CLIPProcessor.from_pretrained(MODEL_NAME, use_fast=False)
        self.item_feats = self._text([f"a photo of {p}" for p, _, _ in ITEMS])
        self.colour_feats = self._text([f"a photo of a {c.lower()} coloured garment" for c in COLOURS])

    @torch.no_grad()
    def _text(self, texts):
        inputs = self.processor(text=texts, return_tensors="pt", padding=True)
        f = self.model.get_text_features(**inputs)
        return f / f.norm(dim=-1, keepdim=True)

    @torch.no_grad()
    def group_probs(self, matrix):
        """For every L2-normalised catalog embedding: {group: probability that the photo mainly
        shows that kind of garment}. Used to drop catalog photos that don't show their labelled item
        (e.g. a 'Tshirts' product photographed as a full-body shot where the jeans dominate)."""
        logits = 100.0 * torch.from_numpy(np.asarray(matrix, dtype="float32")) @ self.item_feats.T
        p = logits.softmax(dim=-1).numpy()
        groups = np.array([g for _, g, _ in ITEMS])
        return {g: p[:, groups == g].sum(axis=1) for g in set(groups)}

    FLASHY = [
        "a person wearing a shiny, richly embroidered festive outfit with gold work",
        "a bright, colourful, glamorous celebration outfit",
        "an elegant outfit in vivid jewel colours with decorative patterns",
    ]
    PLAIN = [
        "a person wearing a plain, simple, dull everyday outfit",
        "a plain pale garment with no design",
        "a basic casual outfit in a muted colour",
    ]

    @torch.no_grad()
    def flashy_scores(self, matrix):
        """0..1 per catalog photo: how festive / flashy (bright, embroidered, rich) it looks versus plain.

        Zero-shot from the stored CLIP embeddings; returned as a percentile rank so the scores are
        evenly spread (the raw CLIP differences are tiny)."""
        pos, neg = self._text(self.FLASHY), self._text(self.PLAIN)
        m = torch.from_numpy(np.asarray(matrix, dtype="float32"))
        diff = (m @ pos.T).mean(dim=1) - (m @ neg.T).mean(dim=1)
        diff = diff.numpy()
        ranks = diff.argsort().argsort()
        return ranks / max(len(diff) - 1, 1)

    DRESSY_SHOES = [
        "a pair of elegant dressy party sandals with straps",
        "a pair of elegant high heels",
        "a pair of embellished ethnic sandals",
    ]
    CASUAL_SHOES = [
        "a pair of flip flops with a thong strap",
        "a pair of casual rubber slippers",
        "a pair of sneakers",
        "a pair of plain flat ballet shoes",
    ]

    @torch.no_grad()
    def dressy_scores(self, matrix, footwear_mask):
        """0..1 per catalog photo: how dressy it looks as footwear (strappy heels / embellished
        sandals score high; flip flops, slippers and sneakers score low). Catalog labels are not
        enough here - many 'Flats' are thong flip flops. Percentile rank among the footwear only
        (everything that is not footwear gets 0)."""
        pos, neg = self._text(self.DRESSY_SHOES), self._text(self.CASUAL_SHOES)
        m = torch.from_numpy(np.asarray(matrix, dtype="float32"))
        diff = ((m @ pos.T).mean(dim=1) - (m @ neg.T).mean(dim=1)).numpy()
        out = np.zeros(len(diff))
        mask = np.asarray(footwear_mask, dtype=bool)
        d = diff[mask]
        out[mask] = d.argsort().argsort() / max(len(d) - 1, 1)
        return out

    @torch.no_grad()
    def analyze(self, pil_img):
        """Returns dict: embedding, group, articleType, colour, confidence (0-1)."""
        inputs = self.processor(images=pil_img.convert("RGB"), return_tensors="pt")
        f = self.model.get_image_features(**inputs)
        f = f / f.norm(dim=-1, keepdim=True)

        def probs(text_feats):
            return (100.0 * f @ text_feats.T).softmax(dim=-1)[0].numpy()

        p_item = probs(self.item_feats)
        groups = {}
        for p, (_, g, _) in zip(p_item, ITEMS):
            groups[g] = groups.get(g, 0.0) + float(p)
        group = max(groups, key=groups.get)
        best = max((i for i, it in enumerate(ITEMS) if it[1] == group), key=lambda i: p_item[i])

        return {
            "embedding": f[0].numpy(),   # L2-normalised CLIP image embedding (for catalog ranking)
            "group": group,
            "articleType": ITEMS[best][2],
            "colour": COLOURS[int(np.argmax(probs(self.colour_feats)))],
            "confidence": groups[group],
        }

    @torch.no_grad()
    def guess_gender(self, pil_img):
        """('Men' | 'Women' | None, confidence) from the garment photo itself."""
        inputs = self.processor(images=pil_img.convert("RGB"), return_tensors="pt")
        f = self.model.get_image_features(**inputs)
        f = f / f.norm(dim=-1, keepdim=True)
        texts = [
            "a photo of menswear, a men's garment for a man",
            "a photo of womenswear, a women's garment for a woman",
            "a men's t-shirt, shirt or kurta",
            "a women's top, kurti, saree, lehenga or dress",
        ]
        p = (100.0 * f @ self._text(texts).T).softmax(dim=-1)[0].numpy()
        men, women = float(p[0] + p[2]), float(p[1] + p[3])
        total = men + women
        if total <= 0:
            return None, 0.0
        men, women = men / total, women / total
        if men >= women + 0.06:
            return "Men", men
        if women >= men + 0.06:
            return "Women", women
        return None, max(men, women)
