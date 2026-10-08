"""RAG helpers for the Smart Style recommender.

Pipeline
--------
1. Retrieval
   - styling knowledge base  -> styling_guide.txt (one chunk per blank-line separated paragraph)
   - product catalog         -> text document per product built from catalog metadata
   Both are indexed with TF-IDF (scikit-learn, no extra install, no downloads).
2. Generation
   - the retrieved chunks and the candidate products are put into a prompt and sent to an LLM.

LLM backend (picked automatically, or force it with LLM_PROVIDER=gemini|ollama):
   - Gemini : set GEMINI_API_KEY      (optional GEMINI_MODEL, default "gemini-flash-latest")
   - Ollama : run `ollama serve`      (optional OLLAMA_MODEL, default "llama3.1",
                                       OLLAMA_HOST, default "http://localhost:11434")
If no backend is available the app still shows the retrieved styling tips.
"""
import os
import re
import time

import numpy as np
import pandas as pd
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel


def _load_dotenv(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    """Tiny .env reader (KEY=value per line), so API keys need not be typed into the terminal.
    Real environment variables win over the file. .env is git-ignored."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

GUIDE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "styling_guide.txt")

# Small Hinglish/Hindi -> catalog vocabulary map so queries like "shaadi ke liye kurta" work.
SYNONYMS = {
    "shaadi": "wedding ethnic",
    "shadi": "wedding ethnic",
    "wedding": "ethnic wedding",
    "festive": "ethnic festive",
    "tyohar": "ethnic festive",
    "office": "formal",
    "meeting": "formal",
    "interview": "formal",
    "gym": "sports",
    "workout": "sports",
    "running": "sports",
    "party": "party",
    "date": "party",
    "college": "casual",
    "daily": "casual",
    "jooti": "sandals flip flops",
    "juti": "sandals flip flops",
    "joote": "shoes",
    "jute": "shoes",
    "pant": "trousers",
    "pants": "trousers jeans",
    "tshirt": "tshirts",
    "t-shirt": "tshirts",
    "kapde": "",
    "sardi": "winter",
    "garmi": "summer",
    "nila": "blue",
    "neela": "blue",
    "kala": "black",
    "safed": "white",
    "lal": "red",
    "hara": "green",
    "peela": "yellow",
}


def expand_query(text):
    words = str(text).lower().replace(",", " ").split()
    return " ".join(SYNONYMS.get(w, w) for w in words)


# --------------------------------------------------------------------------- retrieval
def load_guide_chunks(path=GUIDE_PATH):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return [c.strip() for c in text.split("\n\n") if c.strip()]


def product_doc(row):
    parts = [row.get("gender"), row.get("baseColour"), row.get("articleType"),
             row.get("subCategory"), row.get("usage"), row.get("season")]
    return " ".join(str(p) for p in parts if pd.notna(p) and str(p) != "nan")


class Retriever:
    """TF-IDF retriever over the styling guide and the product catalog."""

    def __init__(self, catalog_df):
        self.chunks = load_guide_chunks()
        self.guide_vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self.guide_mat = self.guide_vec.fit_transform(self.chunks) if self.chunks else None

        self.catalog = catalog_df.reset_index(drop=True)
        docs = self.catalog.apply(product_doc, axis=1)
        self.cat_vec = TfidfVectorizer()
        self.cat_mat = self.cat_vec.fit_transform(docs)

    def guide(self, query, k=4):
        """Top-k styling guideline chunks for a query."""
        if self.guide_mat is None:
            return []
        q = self.guide_vec.transform([expand_query(query)])
        scores = linear_kernel(q, self.guide_mat)[0]
        top = np.argsort(scores)[::-1][:k]
        return [self.chunks[i] for i in top if scores[i] > 0]

    def catalog_search(self, query, gender=None, usage=None, k=6):
        """Top-k catalog rows for a free-text query, optionally filtered by gender / usage."""
        q = self.cat_vec.transform([expand_query(query)])
        scores = linear_kernel(q, self.cat_mat)[0]
        genders = self.catalog["gender"].astype(str).str.strip().to_numpy()
        usages = self.catalog["usage"].astype(str).str.strip().to_numpy()
        use_g, use_u = bool(gender and gender != "Any"), bool(usage and usage != "Any")
        ranked = []
        # Apply the filters, but relax the occasion first, then the gender, if nothing matches
        # (the catalog has no Boys/Girls Formal or Party items, for example).
        for need_g, need_u in ((use_g, use_u), (use_g, False), (False, False)):
            mask = np.ones(len(self.catalog), dtype=bool)
            if need_g:
                mask &= genders == gender
            if need_u:
                mask &= usages == usage
            masked = np.where(mask, scores, -1)
            ranked = [i for i in np.argsort(masked)[::-1][:500] if masked[i] > 0]
            if ranked:
                break
        scores = masked

        # Many products share identical metadata; show distinct kinds first, then fill up.
        picked, seen, rest = [], set(), []
        for i in ranked:
            doc = product_doc(self.catalog.iloc[i])
            if doc in seen:
                rest.append(i)
            else:
                seen.add(doc)
                picked.append(i)
            if len(picked) >= k:
                break
        picked += rest[: max(0, k - len(picked))]
        return self.catalog.iloc[picked[:k]]


# --------------------------------------------------------------------------- generation
def _provider():
    forced = os.environ.get("LLM_PROVIDER", "").lower()
    if forced in ("gemini", "ollama"):
        return forced
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    try:
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        requests.get(f"{host}/api/tags", timeout=1.5)
        return "ollama"
    except Exception:
        return None


def llm_status():
    """Short human readable description of the active LLM backend."""
    p = _provider()
    if p == "gemini":
        return f"Gemini ({os.environ.get('GEMINI_MODEL', 'gemini-flash-latest')})"
    if p == "ollama":
        return f"Ollama ({os.environ.get('OLLAMA_MODEL', 'llama3.1')})"
    return None


def ask_llm(prompt, system=None, timeout=35):
    """Returns (text, error). Exactly one of them is None."""
    p = _provider()
    try:
        if p == "gemini":
            body = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.4},
            }
            if system:
                body["systemInstruction"] = {"parts": [{"text": system}]}
            # Gemini often answers 503 "high demand" for a few seconds: retry, then try the next model.
            main = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
            fallbacks = os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-flash-lite-latest")
            models = [main] + [m.strip() for m in fallbacks.split(",") if m.strip() and m.strip() != main]
            last = None
            for model in models:
                r = None
                for attempt in range(2):
                    try:
                        r = requests.post(
                            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                            headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                            json=body, timeout=timeout,
                        )
                    except (requests.Timeout, requests.ConnectionError) as e:   # slow / dropped: try again
                        last = f"{model}: {type(e).__name__}"
                        r = None
                        continue
                    if r.status_code == 200:
                        try:
                            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip(), None
                        except (KeyError, IndexError):      # e.g. answer blocked by a safety filter
                            last = f"{model} returned no text"
                            break
                    last = f"{r.status_code} from {model}: {r.text[:200]}"
                    if r.status_code in (500, 502, 503, 504, 429):
                        time.sleep(1.5 * (attempt + 1))     # overloaded / rate limited: wait, retry
                        continue
                    break                                   # 400/401/403/404: retrying will not help
                if r is not None and r.status_code in (400, 401, 403):   # bad request / key problem: other models fail too
                    break
            return None, f"LLM call failed: {last}"
        if p == "ollama":
            host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            messages = ([{"role": "system", "content": system}] if system else []) + \
                       [{"role": "user", "content": prompt}]
            r = requests.post(
                f"{host}/api/chat",
                json={"model": os.environ.get("OLLAMA_MODEL", "llama3.1"),
                      "messages": messages, "stream": False,
                      "options": {"temperature": 0.4}},
                timeout=timeout,
            )
            r.raise_for_status()
            return r.json()["message"]["content"].strip(), None
        return None, "No LLM configured. Set GEMINI_API_KEY, or install and run Ollama."
    except Exception as e:  # network / quota / bad model name ...
        return None, f"LLM call failed: {e}"


SYSTEM_PROMPT = (
    "You are a friendly fashion stylist for an online store. "
    "Use ONLY the catalog items given to you; never invent products. "
    "Refer to items by their number. Use the styling guidelines when they apply. "
    "Keep answers short and practical. Reply in the same language as the user's question "
    "(English by default; Hinglish if the user writes Hinglish)."
)


def _items_block(title, rows):
    lines = [f"{title}:"]
    for n, (_, r) in enumerate(rows.iterrows(), 1):
        lines.append(f"  {n}. {product_doc(r)}")
    return "\n".join(lines)


def explain_outfit(query_item, filters, section_rows, guide_chunks):
    """Explain why the recommended items work with the uploaded item.

    section_rows: dict {"Bottoms": DataFrame, "Footwear": DataFrame}
    Item numbers restart per section, so the prompt names the section in every reference.
    """
    blocks = "\n".join(_items_block(t, rows) for t, rows in section_rows.items() if len(rows))
    tips = "\n".join(f"- {c}" for c in guide_chunks) or "- (none)"
    prompt = (
        f"The user uploaded an item that looks like: {product_doc(query_item)}.\n"
        f"Selected filters: gender={filters.get('gender')}, occasion={filters.get('usage')}.\n\n"
        f"Styling guidelines:\n{tips}\n\n"
        f"Candidate catalog items:\n{blocks}\n\n"
        "Task: build ONE complete outfit. Pick the single best item from each candidate list, "
        "refer to it as '<list name> #<number>', and give one short reason for each "
        "(colour match, occasion, season). Then add one extra styling tip. "
        "Maximum 6 lines."
    )
    return ask_llm(prompt, system=SYSTEM_PROMPT)


def answer_question(question, found_rows, guide_chunks, history=None, query_item=None):
    """Answer a free-text styling question using retrieved products + guidelines."""
    tips = "\n".join(f"- {c}" for c in guide_chunks) or "- (none)"
    items = _items_block("Catalog items found", found_rows) if len(found_rows) else \
        "Catalog items found: (none matched)"
    ctx = f"The user's uploaded item: {product_doc(query_item)}.\n" if query_item is not None else ""
    convo = ""
    if history:
        convo = "Recent conversation:\n" + "\n".join(f"{m['role']}: {m['content']}" for m in history[-4:]) + "\n\n"
    prompt = (
        f"{convo}{ctx}Styling guidelines:\n{tips}\n\n{items}\n\n"
        f"User question: {question}\n\n"
        "Answer using the catalog items above (refer to them by number). "
        "If nothing matched, say so and give a general tip from the guidelines. Maximum 6 lines."
    )
    return ask_llm(prompt, system=SYSTEM_PROMPT)


def answer_outfit_request(question, outfits, guide_chunks, occasion, gender, history=None, assumed_gender=False,
                          colours=None):
    """Explain complete outfits for a request like 'ethnic wear outfit for Diwali'.

    outfits: [{"Top": row, "Bottom": row, "Footwear": row}, ...] (already coordinated and suited
    to the occasion). The model only describes them; it does not pick or invent items.
    """
    tips = "\n".join(f"- {c}" for c in guide_chunks) or "- (none)"
    blocks = "\n".join(
        f"Outfit {n}: " + "; ".join(f"{role} = {product_doc(row)}" for role, row in o.items() if hasattr(row, "get"))
        + (" (a similar alternative, not exactly the garment the user asked for)" if o.get("similar") else "")
        for n, o in enumerate(outfits, 1))
    convo = ""
    if history:
        convo = "Recent conversation:\n" + "\n".join(f"{m['role']}: {m['content']}" for m in history[-4:]) + "\n\n"
    note = (" The user did not say the gender, so these are for " + str(gender) + "; mention briefly that they can "
            "ask for women's styles too.") if assumed_gender else ""
    colour_note = f"(The user asked for these colours: {', '.join(colours)}.) " if colours else ""
    prompt = (
        f"{convo}Styling guidelines:\n{tips}\n\n"
        f"The user wants a complete {occasion} outfit for {gender}.{note}\n"
        "(An outfit with a 'Main' piece is a hero look - saree, kurta set, lehenga or a men's kurta - styled "
        "with accessories such as dupatta, jewellery, clutch, jacket or watch.) "
        f"{colour_note}"
        "(For festive occasions the pieces were chosen to be bright, rich and eye-catching; say so "
        "when it applies, and do not describe them as plain.)\n"
        f"Ready-made outfits from our catalog (each is a full look, already suited to the occasion):\n{blocks}\n\n"
        f"User question: {question}\n\n"
        "Answer only this latest question; ignore earlier topics in the conversation unless it refers to them. "
        f"All {len(outfits)} outfits are shown to the user as pictures with their own caption box. Reply in "
        "EXACTLY this format, plain text, no markdown, no bullets:\n"
        "line 1: one friendly intro sentence (max 20 words);\n"
        f"then one line per outfit for ALL {len(outfits)} outfits, each starting 'Outfit N:' (N = 1.."
        f"{len(outfits)}), max 22 words, naming the pieces in plain words (e.g. 'rust kurta with beige "
        "churidar and sandals') and why they work (colour match, occasion); say it is a similar alternative "
        "when the outfit is marked so;\n"
        "last line: 'Tip: ' followed by one styling tip (accessories, fabric or fit).\n"
        "Never copy the catalog labels (words like Topwear, Bottomwear, Ethnic Summer, Casual Fall)."
    )
    return ask_llm(prompt, system=SYSTEM_PROMPT)


def split_outfit_reply(text, n_outfits):
    """Split the stylist's reply into (intro, {outfit number: note}, tip) so each outfit card can show
    its own note. Works with or without the exact format; text that does not fit goes to `intro`."""
    notes, tip, intro = {}, "", []
    for line in str(text or "").splitlines():
        line = line.strip().strip("*-• ").strip()
        if not line:
            continue
        m = re.match(r"(?i)^\**outfit\s*(\d+)\**\s*[:\-–.]\s*(.+)$", line)
        t = re.match(r"(?i)^\**(?:styling\s+)?tip\**\s*[:\-–]\s*(.+)$", line)
        if m and 1 <= int(m.group(1)) <= n_outfits:
            notes[int(m.group(1))] = m.group(2).strip().strip("*")
        elif t:
            tip = t.group(1).strip().strip("*")
        else:
            intro.append(line)
    return " ".join(intro), notes, tip