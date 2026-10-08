"""Shared stylist logic for the FastAPI app. No Streamlit."""
import io
import os
import threading
import zlib

import numpy as np
import pandas as pd
from PIL import Image, ImageFilter, ImageOps

os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

from detect import Detector
from hdphotos import original_photo, prefetch
from outfit import (
    OCCASIONS, build_outfits, parse_request,
    infer_gender, effective_occasion,
    garment_pool, footwear_pool, score_pool, pick_diverse,
)
from outfit_image import compose_board, compose_outfit
from rag import Retriever, answer_outfit_request, answer_question, llm_status, split_outfit_reply
from tryon import Segmenter, cutout_for, kind_for

HERE = os.path.dirname(os.path.abspath(__file__))
CLIP_EMB_PATH = os.path.join(HERE, "clip_embeddings.npy")
OUTFIT_DIR = os.path.join(HERE, "outfit_cache")
HD_DIR = os.path.join(HERE, "hd_cache")
os.makedirs(OUTFIT_DIR, exist_ok=True)
os.makedirs(HD_DIR, exist_ok=True)

OUTFIT_OPTIONS = 6
ROLE_ORDER = ("Main", "Top", "Bottom", "Dupatta", "Jacket", "Jewellery", "Bag", "Watch", "Footwear")
ROLE_NAMES = {
    "Main": "Main piece", "Top": "Top", "Bottom": "Bottom", "Dupatta": "Dupatta",
    "Jacket": "Jacket", "Jewellery": "Jewellery", "Bag": "Clutch", "Watch": "Watch",
    "Footwear": "Footwear",
}
TYPE_NAMES = {
    "Sarees": "Saree", "Kurtas": "Kurta", "Kurta Sets": "Kurta set", "Clutches": "Clutch",
    "Tshirts": "T-shirt", "Shirts": "Shirt", "Tops": "Top", "Jeans": "Jeans",
    "Lehenga Choli": "Lehenga choli", "Jewellery Set": "Jewellery set",
    "Necklace and Chains": "Necklace", "Dresses": "Dress", "Nehru Jackets": "Nehru jacket",
}
COLOUR_HEX = {
    "Red": "#C62828", "Maroon": "#7B1E3A", "Pink": "#EC7FA9", "Blue": "#2F6DB5",
    "Navy Blue": "#1F2A5A", "Green": "#2E8B57", "Yellow": "#F2C230", "Orange": "#F28C28",
    "Purple": "#7E57C2", "Black": "#222222", "White": "#FFFFFF", "Off White": "#F4EFE6",
    "Cream": "#F3E9D2", "Beige": "#D9C3A0", "Brown": "#7B5233", "Grey": "#9AA0A6",
    "Gold": "#D4AF37", "Silver": "#C0C0C0", "Teal": "#1F8A8A",
}
LABEL_WORDS = (
    "topwear", "bottomwear", "apparel set", "ethnic fall", "ethnic summer",
    "casual fall", "casual summer", "accessories", "free gifts",
)
SUGGESTIONS = [
    ("Diwali look · Women", "outfit for women for diwali"),
    ("Karwa Chauth look", "karwa chauth outfit"),
    ("Wedding lehenga", "lehenga for wedding"),
    ("Festive look · Men", "diwali outfit for men"),
    ("Party outfit · Women", "party outfit for women"),
    ("Formal look · Men", "formal outfit for men"),
]


class Engine:
    def __init__(self):
        self.df = pd.read_pickle(os.path.join(HERE, "df_with_labels.pkl"))
        self.matrix = np.load(CLIP_EMB_PATH).astype("float32")
        if len(self.matrix) != len(self.df):
            raise RuntimeError("clip_embeddings.npy does not match the catalog")
        self.detector = Detector()
        self.df = self.df.copy()
        self.df["photo_ok"] = self._photo_ok()
        self.df["flashy"] = self.detector.flashy_scores(self.matrix)
        self.df["dressy"] = self.detector.dressy_scores(
            self.matrix, (self.df["masterCategory"] == "Footwear").to_numpy()
        )
        self.df["usage"] = self.df["usage"].astype(str).str.strip()
        self.df["gender"] = self.df["gender"].astype(str).str.strip()
        self.df["articleType"] = self.df["articleType"].astype(str).str.strip()
        self.retriever = Retriever(self.df)
        self._segmenter = None
        self._by_id = {str(r["id"]): r for _, r in self.df.iterrows()}
        threading.Thread(target=self._warmup, daemon=True).start()

    def _warmup(self):
        """Load SegFormer and cache featured cut-outs so the first Try on is faster."""
        try:
            print("Warming try-on cut-outs...")
            self.segmenter()
            for item in self.featured():
                self.prepare_garments(item.get("tryon") or [])
            print("Try-on cache ready.")
        except Exception as exc:
            print("Try-on warmup skipped:", exc)

    def resolve_gender(self, sim, img, gender="Any"):
        if gender not in ("Any", ""):
            return gender
        catalog_who = infer_gender(sim, self.df["gender"].to_numpy(), threshold=0.58, min_votes=8)
        clip_who, clip_p = self.detector.guess_gender(img)
        if catalog_who and clip_who and catalog_who == clip_who:
            return catalog_who
        if clip_who and clip_p >= 0.58:
            return clip_who
        return catalog_who or clip_who or "Men"

    def _photo_ok(self):
        p = self.detector.group_probs(self.matrix)
        sub = self.df["subCategory"].astype(str).to_numpy()
        master = self.df["masterCategory"].astype(str).to_numpy()
        ok = np.ones(len(self.df), dtype=bool)
        for mask, group in (
            (sub == "Topwear", "upper"),
            (sub == "Bottomwear", "lower"),
            (master == "Footwear", "footwear"),
            (sub == "Bags", "other"),
        ):
            ok[mask] = p[group][mask] >= 0.5
        return ok

    def segmenter(self):
        if self._segmenter is None:
            self._segmenter = Segmenter()
        return self._segmenter

    def enhanced_jpeg(self, path, scale=4):
        original = original_photo(path)
        if original is not None:
            return original
        cached = os.path.join(HD_DIR, os.path.splitext(os.path.basename(str(path)))[0] + ".jpg")
        if os.path.exists(cached):
            with open(cached, "rb") as f:
                return f.read()
        img = Image.open(path).convert("RGB")
        img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=110, threshold=2))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=95)
        return buf.getvalue()

    def product_jpeg(self, pid):
        row = self._by_id.get(str(pid))
        if row is None:
            return None
        return self.enhanced_jpeg(row["image_path"])

    def outfit_jpeg(self, filename):
        name = os.path.basename(filename)
        path = os.path.join(OUTFIT_DIR, name)
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            return f.read()

    def _pic(self, row):
        return Image.open(io.BytesIO(self.enhanced_jpeg(row["image_path"]))).convert("RGB")

    def outfit_card(self, outfit):
        prefetch([r["image_path"] for r in outfit.values() if hasattr(r, "get")])
        if outfit.get("kind") == "board":
            roles = [r for r in ("Dupatta", "Jacket", "Jewellery", "Bag", "Watch", "Footwear") if r in outfit]
            ids = [str(outfit["Main"]["id"])] + [str(outfit[r]["id"]) for r in roles]
            path = os.path.join(OUTFIT_DIR, "board2_" + "_".join(ids) + ".png")
            if not os.path.exists(path):
                names = {
                    "Dupatta": "Dupatta", "Jacket": "Jacket", "Jewellery": "Jewellery",
                    "Bag": "Clutch", "Watch": "Watch", "Footwear": "Footwear",
                }
                compose_board(
                    self._pic(outfit["Main"]),
                    [self._pic(outfit[r]) for r in roles],
                    labels=[names[r] for r in roles],
                ).save(path)
            return path
        ids = [str(outfit[r]["id"]) for r in ("Top", "Bottom", "Footwear")]
        path = os.path.join(OUTFIT_DIR, "_".join(ids) + ".png")
        if not os.path.exists(path):
            compose_outfit(
                *[self._pic(outfit[r]) for r in ("Top", "Bottom", "Footwear")],
                top_type=outfit["Top"]["articleType"],
                bottom_type=outfit["Bottom"]["articleType"],
            ).save(path)
        return path

    def outfit_items(self, outfit):
        rows = []
        for role in ROLE_ORDER:
            if role in outfit:
                r = outfit[role]
                rows.append({
                    "role": ROLE_NAMES[role],
                    "name": TYPE_NAMES.get(r["articleType"], r["articleType"]),
                    "colour": str(r["baseColour"]),
                    "hex": COLOUR_HEX.get(str(r["baseColour"]), "#CFCFCF"),
                })
        return rows

    def plain_note(self, outfit):
        parts = [f"{i['colour'].lower()} {i['name'].lower()}" for i in self.outfit_items(outfit)]
        if len(parts) < 2:
            return ""
        mid = ", ".join(parts[1:-1])
        and_ = (" and " if len(parts) > 2 else "") + parts[-1]
        extra = (mid + and_) if mid else and_
        return f"{parts[0].capitalize()} with {extra}."

    def outfit_payload(self, n, outfit, path, note=""):
        if (not note or any(w in note.lower() for w in LABEL_WORDS)
                or note.startswith(("Women ", "Men ", "Girls ", "Boys "))):
            note = self.plain_note(outfit)
        garments = []
        for role in ("Main", "Top", "Bottom", "Jacket"):
            if role in outfit:
                r = outfit[role]
                garments.append({
                    "id": str(r["id"]),
                    "articleType": r["articleType"],
                    "subCategory": r["subCategory"],
                })
        return {
            "n": n,
            "image": "/api/outfit/" + os.path.basename(path),
            "items": self.outfit_items(outfit),
            "note": note,
            "similar": bool(outfit.get("similar")),
            "caption": f"Outfit {n}: " + ", ".join(i["name"] for i in self.outfit_items(outfit)),
            "tryon": garments,
        }

    def featured(self):
        picks = []
        for mask, label, prompt in (
            ((self.df["gender"] == "Women") & (self.df["subCategory"] == "Saree"), "Saree edit", "festive saree look for women"),
            ((self.df["gender"] == "Women") & (self.df["articleType"] == "Kurta Sets"), "Kurta sets", "kurta set for women for festive"),
            ((self.df["gender"] == "Men") & (self.df["articleType"] == "Kurtas"), "Men festive", "diwali outfit for men"),
            ((self.df["gender"] == "Men") & (self.df["articleType"] == "Shirts"), "Shirts", "formal shirt look for men"),
        ):
            pool = self.df.loc[mask]
            if pool.empty:
                continue
            row = pool.sort_values("flashy", ascending=False).iloc[0] if "flashy" in pool else pool.iloc[0]
            picks.append({
                "label": label,
                "caption": f"{row['baseColour']} {TYPE_NAMES.get(row['articleType'], row['articleType'])}",
                "image": f"/api/product/{row['id']}",
                "prompt": prompt,
                "tryon": [{
                    "id": str(row["id"]),
                    "articleType": row["articleType"],
                    "subCategory": row["subCategory"],
                }],
            })
        return picks

    def auth_shots(self):
        picks = []
        seen = set()
        for mask, label in (
            ((self.df["gender"] == "Women") & (self.df["subCategory"] == "Saree"), "Saree edit"),
            ((self.df["gender"] == "Women") & (self.df["articleType"] == "Kurta Sets"), "Kurta sets"),
            ((self.df["gender"] == "Men") & (self.df["articleType"] == "Kurtas"), "Men festive"),
            ((self.df["gender"] == "Men") & (self.df["articleType"] == "Shirts"), "Shirts"),
        ):
            pool = self.df.loc[mask]
            if pool.empty:
                continue
            top = pool.sort_values("flashy", ascending=False).head(3) if "flashy" in pool.columns else pool.head(3)
            for _, row in top.iterrows():
                pid = str(row["id"])
                if pid in seen:
                    continue
                seen.add(pid)
                picks.append({
                    "label": label,
                    "caption": f"{row['baseColour']} {TYPE_NAMES.get(row['articleType'], row['articleType'])}",
                    "image": f"/api/product/{pid}",
                })
        return picks

    def meta(self):
        genders = ["Any"] + sorted(self.df["gender"].dropna().unique().tolist())
        return {
            "genders": genders,
            "occasions": ["Any"] + OCCASIONS,
            "suggestions": [{"label": a, "prompt": b} for a, b in SUGGESTIONS],
            "featured": self.featured(),
            "shots": self.auth_shots(),
            "llm": llm_status() or "",
        }

    def chat(self, question, gender="Any", occasion="Any", history=None):
        history = history or []
        request = parse_request(question, gender, occasion)
        records, images, tip = [], [], ""
        if request["outfit"]:
            occ = request["occasion"] or "Casual"
            assumed = request["gender"] is None
            who = request["gender"] or "Men"
            tips = self.retriever.guide(f"{question} {occ}", k=3)
            outfits = build_outfits(
                self.df, occ, who, n=OUTFIT_OPTIONS,
                seed=zlib.crc32(question.encode("utf-8")),
                festive=request["festive"], main=request["main"], colours=request["colours"],
            )
            if outfits:
                paths = [self.outfit_card(o) for o in outfits]
                reply, err = answer_outfit_request(
                    question, outfits, tips, occ, who, history=history,
                    assumed_gender=assumed, colours=request["colours"],
                )
                notes = {}
                if reply:
                    intro, notes, tip = split_outfit_reply(reply, len(outfits))
                    reply = intro or "Here are outfits picked for you."
                else:
                    reply = f"{err}" + (("\n\nStyling tips:\n" + "\n".join(f"- {t}" for t in tips)) if tips else "")
                records = [self.outfit_payload(n, o, p, notes.get(n, ""))
                           for n, (o, p) in enumerate(zip(outfits, paths), 1)]
                records.sort(key=lambda r: bool(r.get("similar")))
                for i, rec in enumerate(records, 1):
                    rec["n"] = i
            else:
                reply = "Catalog mein iske liye matching items nahi mile."
            if request.get("missing"):
                reply += f"\n\n(Catalog mein {', '.join(request['missing'])} nahi hai.)"
            if assumed:
                reply += f"\n\n(Gender nahi bataya, isliye {who} ke looks dikhaye.)"
        else:
            found = self.retriever.catalog_search(question, gender=gender, usage=occasion, k=6)
            tips = self.retriever.guide(question, k=3)
            reply, err = answer_question(question, found, tips, history=history)
            if not reply:
                reply = err or "Could not answer."
            images = [
                {"id": str(r["id"]), "caption": r["articleType"], "image": f"/api/product/{r['id']}"}
                for _, r in found.iterrows()
            ]
        return {"reply": reply, "outfits": records, "images": images, "tip": tip}

    def _pick_partner(self, pool, colour, occasion, wanted, is_shoe, used, used_look, gender):
        if pool is None or pool.empty:
            return None
        looks = pool["articleType"].astype(str) + "|" + pool["baseColour"].astype(str)
        free = pool[~pool.index.isin(used) & ~looks.isin(used_look)]
        if free.empty:
            free = pool[~pool.index.isin(used)]
        if free.empty:
            free = pool
        sc = score_pool(free, colour, occasion, wanted, is_footwear=is_shoe)
        if is_shoe and gender == "Women" and occasion in ("Ethnic", "Party", "Formal") and "dressy" in free:
            sc = sc + 0.5 * free["dressy"]
        pick = pick_diverse(free.assign(score=sc).sort_values("score", ascending=False), 1)
        if pick.empty:
            return None
        return pick.iloc[0]

    def _closest(self, pool):
        if pool is None or pool.empty:
            return None
        return pool.sort_values("similarity", ascending=False).iloc[0]

    def complete_from_upload(self, upload_img, detected, gender="Any", occasion="Any", n=3):
        """Finish an uploaded garment: a t-shirt/top gets bottom + footwear for this client and occasion."""
        sim = self.matrix @ detected["embedding"]
        who = self.resolve_gender(sim, upload_img, gender)
        occ = effective_occasion(occasion, detected["articleType"])
        colour = detected["colour"]
        group = detected["group"]
        catalog = self.df.assign(similarity=sim)
        if who:
            catalog = catalog[catalog["gender"].isin([who, "Unisex"])]
        if catalog.empty:
            catalog = self.df.assign(similarity=sim)

        def usable(pool):
            if pool is None or pool.empty:
                return pool
            good = pool[pool["photo_ok"]] if "photo_ok" in pool else pool
            return good if len(good) >= 8 else pool

        tops, t_wanted, _ = garment_pool(catalog[catalog["subCategory"] == "Topwear"], "Topwear", occ, who)
        bottoms, b_wanted, _ = garment_pool(catalog[catalog["subCategory"] == "Bottomwear"], "Bottomwear", occ, who)
        shoes, s_wanted, _ = footwear_pool(catalog[catalog["masterCategory"] == "Footwear"], occ, who)
        tops, bottoms, shoes = usable(tops), usable(bottoms), usable(shoes)

        yours = None
        if group == "upper":
            yours = self._closest(catalog[catalog["subCategory"] == "Topwear"])
        elif group == "lower":
            yours = self._closest(catalog[catalog["subCategory"] == "Bottomwear"])
        elif group == "footwear":
            yours = self._closest(catalog[catalog["masterCategory"] == "Footwear"])
        if yours is None:
            yours = self._closest(catalog)

        outfits, used, used_look = [], set(), set()
        for _ in range(n):
            look = {}
            extras, labels = [], []
            if group == "upper":
                look["Top"] = yours
                bottom = self._pick_partner(bottoms, colour, occ, b_wanted, False, used, used_look, who)
                shoe = self._pick_partner(shoes, colour, occ, s_wanted, True, used, used_look, who)
                if bottom is None or shoe is None:
                    break
                look["Bottom"], look["Footwear"] = bottom, shoe
                extras, labels = [self._pic(bottom), self._pic(shoe)], ["Bottom", "Footwear"]
                used.update((bottom.name, shoe.name))
                used_look.update((
                    f"{bottom['articleType']}|{bottom['baseColour']}",
                    f"{shoe['articleType']}|{shoe['baseColour']}",
                ))
            elif group == "lower":
                look["Bottom"] = yours
                top = self._pick_partner(tops, colour, occ, t_wanted, False, used, used_look, who)
                shoe = self._pick_partner(shoes, colour, occ, s_wanted, True, used, used_look, who)
                if top is None or shoe is None:
                    break
                look["Top"], look["Footwear"] = top, shoe
                extras, labels = [self._pic(top), self._pic(shoe)], ["Top", "Footwear"]
                used.update((top.name, shoe.name))
                used_look.update((
                    f"{top['articleType']}|{top['baseColour']}",
                    f"{shoe['articleType']}|{shoe['baseColour']}",
                ))
            elif group == "footwear":
                look["Footwear"] = yours
                top = self._pick_partner(tops, colour, occ, t_wanted, False, used, used_look, who)
                bottom = self._pick_partner(bottoms, colour, occ, b_wanted, False, used, used_look, who)
                if top is None or bottom is None:
                    break
                look["Top"], look["Bottom"] = top, bottom
                extras, labels = [self._pic(top), self._pic(bottom)], ["Top", "Bottom"]
                used.update((top.name, bottom.name))
                used_look.update((
                    f"{top['articleType']}|{top['baseColour']}",
                    f"{bottom['articleType']}|{bottom['baseColour']}",
                ))
            else:
                break
            token = "up_" + "_".join(str(look[r]["id"]) for r in ROLE_ORDER if r in look)
            path = os.path.join(OUTFIT_DIR, token + ".png")
            if not os.path.exists(path):
                compose_board(upload_img, extras, labels=labels).save(path)
            rec = self.outfit_payload(len(outfits) + 1, look, path)
            yours_name = TYPE_NAMES.get(detected["articleType"], detected["articleType"])
            skip = ROLE_NAMES[{
                "upper": "Top", "lower": "Bottom", "footwear": "Footwear",
            }[group]]
            rec["items"] = [{
                "role": "Your piece",
                "name": yours_name,
                "colour": colour,
                "hex": COLOUR_HEX.get(colour, "#CFCFCF"),
            }] + [it for it in rec["items"] if it["role"] != skip]
            partners = " and ".join(
                f"{it['colour'].lower()} {it['name'].lower()}" for it in rec["items"][1:]
            )
            rec["note"] = (
                f"{colour} {yours_name.lower()} — finished with {partners} "
                f"for {who.lower()} · {occ.lower()}."
            )
            outfits.append(rec)
        return outfits, who, occ

    def match_upload(self, raw, gender="Any", occasion="Any"):
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
        detected = self.detector.analyze(img)
        sim = self.matrix @ detected["embedding"]
        top = np.argsort(sim)[::-1][:8]
        hits = []
        for i in top:
            r = self.df.iloc[int(i)]
            if gender not in ("Any", "") and r["gender"] not in (gender, "Unisex"):
                continue
            hits.append({
                "id": str(r["id"]),
                "caption": f"{r['baseColour']} {r['articleType']}",
                "image": f"/api/product/{r['id']}",
            })
            if len(hits) >= 6:
                break
        outfits, who, occ = [], gender, occasion
        if detected["group"] in ("upper", "lower", "footwear"):
            outfits, who, occ = self.complete_from_upload(img, detected, gender, occasion)
        kind = TYPE_NAMES.get(detected["articleType"], detected["articleType"])
        if outfits:
            reply = (
                f"{detected['colour']} {kind.lower()} detected. "
                f"Here are bottoms and footwear for {who.lower()} · {occ.lower()}."
                if detected["group"] == "upper" else
                f"{detected['colour']} {kind.lower()} detected. "
                f"Completed for {who.lower()} · {occ.lower()}."
            )
        else:
            reply = f"{detected['colour']} {kind} · closest catalog matches."
        return {
            "colour": detected["colour"],
            "articleType": detected["articleType"],
            "group": detected["group"],
            "confidence": float(detected["confidence"]),
            "gender": who,
            "occasion": occ,
            "reply": reply,
            "matches": hits,
            "outfits": outfits,
        }

    def prepare_garments(self, pieces):
        garments = []
        for g in pieces or []:
            row = self._by_id.get(str(g.get("id")))
            if row is None:
                continue
            kind = kind_for(row["articleType"], row["subCategory"])
            png, sw = cutout_for(
                {"id": row["id"], "image_path": row["image_path"]},
                kind, self.segmenter, lambda r=row: self.enhanced_jpeg(r["image_path"]),
            )
            if png:
                garments.append({
                    "name": TYPE_NAMES.get(row["articleType"], row["articleType"]),
                    "kind": kind, "png": png, "sw": sw,
                })
        return garments
