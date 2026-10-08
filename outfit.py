"""Outfit rules for the recommender (pure functions, no Streamlit).

Why this exists: ranking purely by visual similarity put flip flops / heels next to a men's t-shirt.
Footwear is therefore chosen by *type* for the occasion and gender, and only then ranked by similarity.
(The catalog's own `usage` label is too sparse on footwear to filter by: only ~23 Ethnic and 2 Party items.)
"""
import numpy as np
import pandas as pd

# Footwear article types that suit an occasion, best first. 'default' is used when gender is unknown.
FOOTWEAR_BY_OCCASION = {
    'Casual': {
        'Men': ['Casual Shoes', 'Sports Shoes'],
        'Women': ['Casual Shoes', 'Flats', 'Sports Shoes'],
        'default': ['Casual Shoes', 'Sports Shoes', 'Flats'],
    },
    'Formal': {
        'Men': ['Formal Shoes', 'Casual Shoes'],
        'Women': ['Heels', 'Flats', 'Formal Shoes'],
        'default': ['Formal Shoes', 'Heels', 'Flats'],
    },
    'Sports': {'default': ['Sports Shoes']},
    'Ethnic': {
        'Men': ['Formal Shoes', 'Sandals', 'Casual Shoes'],    # the catalog's men's "Sandals" are mostly sporty
        'Women': ['Flats', 'Heels', 'Sandals'],
        'default': ['Sandals', 'Flats', 'Heels', 'Casual Shoes'],
    },
    'Party': {
        'Men': ['Formal Shoes', 'Casual Shoes'],
        'Women': ['Heels', 'Flats'],
        'default': ['Heels', 'Formal Shoes', 'Flats', 'Casual Shoes'],
    },
    'Home': {   # the only occasion where flip flops are welcome
        'Men': ['Flip Flops', 'Casual Shoes'],
        'Women': ['Flip Flops', 'Flats', 'Casual Shoes'],
        'default': ['Flip Flops', 'Casual Shoes', 'Flats'],
    },
}

OCCASIONS = ['Casual', 'Formal', 'Sports', 'Ethnic', 'Party', 'Home']

# Occasion implied by the uploaded item when the user has not picked one.
OCCASION_BY_UPLOAD = {
    'Kurtas': 'Ethnic', 'Sarees': 'Ethnic',
    'Formal Shoes': 'Formal', 'Blazers': 'Formal',
    'Sports Shoes': 'Sports', 'Track Pants': 'Sports',
}


def infer_gender(similarity, genders, k=30, threshold=0.7, min_votes=10):
    """'Men' / 'Women' / None, by majority vote of the k most similar catalog items.

    Checked on the catalog itself: decides ~92% of the time and is ~97% right when it decides.
    """
    top = np.argsort(similarity)[::-1][:k]
    g = np.asarray(genders)[top]
    men, women = int((g == 'Men').sum()), int((g == 'Women').sum())
    votes = men + women
    if votes < min_votes or max(men, women) / votes < threshold:
        return None
    return 'Men' if men > women else 'Women'


def effective_occasion(usage_filter, uploaded_article_type):
    """The occasion to dress for: the sidebar choice, else implied by the upload, else Casual."""
    if usage_filter and usage_filter != 'Any' and usage_filter in FOOTWEAR_BY_OCCASION:
        return usage_filter
    return OCCASION_BY_UPLOAD.get(uploaded_article_type, 'Casual')


def _family(gender):
    """'M' for Men/Boys, 'F' for Women/Girls, else None (unknown / Unisex)."""
    return {'Men': 'M', 'Boys': 'M', 'Women': 'F', 'Girls': 'F'}.get(gender)


def footwear_pool(footwear, occasion, gender, min_items=5):
    """(rows, wanted_types, exact): footwear whose type suits the occasion/gender.

    `wanted_types` is ordered best first; score_pool() uses the order as a preference.
    `exact` is False when the catalog has too few such shoes (e.g. no heels for Girls), so the
    list was widened to everyday shoes/sandals. Flip flops only appear for the Home occasion.
    """
    options = FOOTWEAR_BY_OCCASION.get(occasion, FOOTWEAR_BY_OCCASION['Casual'])
    fam = _family(gender)
    wanted = options.get({'M': 'Men', 'F': 'Women'}.get(fam), options['default'])
    allow_flip = occasion == 'Home'
    base = footwear if allow_flip else footwear[footwear['articleType'] != 'Flip Flops']
    pool = base[base['articleType'].isin(wanted)]
    if len(pool) >= min_items:
        return pool, wanted, True
    # widen to everyday shoes first; sandals only if that is still not enough
    for extra in (('Casual Shoes',), ('Casual Shoes', 'Sandals')):
        widened = list(wanted) + [t for t in extra if t not in wanted]
        pool = base[base['articleType'].isin(widened)]
        if len(pool) >= min_items:
            return pool, widened, False
    return base, widened, False


# ----------------------------------------------------------------------------- tops / bottoms by occasion
# Garment types that suit an occasion, best first, for male ('M' = Men, Boys) and female ('F' = Women,
# Girls) catalogs. The catalog's own `usage` label is far too sparse to filter on (Boys/Girls have no
# Formal / Party / Home items at all; Women have a handful of Formal / Party ones).
GARMENT_TYPES = {
    'Topwear': {
        'Casual': {'M': ['Tshirts', 'Shirts', 'Sweatshirts', 'Jackets', 'Sweaters'],
                   'F': ['Tops', 'Tshirts', 'Shirts', 'Tunics', 'Kurtis', 'Sweatshirts', 'Jackets', 'Sweaters']},
        'Formal': {'M': ['Shirts', 'Blazers', 'Waistcoat', 'Sweaters', 'Jackets'],
                   'F': ['Shirts', 'Tops', 'Tunics', 'Blazers', 'Waistcoat', 'Kurtis', 'Sweaters', 'Jackets']},
        'Sports': {'M': ['Tshirts', 'Sweatshirts', 'Jackets', 'Rain Jacket'],
                   'F': ['Tshirts', 'Tops', 'Sweatshirts', 'Jackets']},
        'Party': {'M': ['Shirts', 'Blazers', 'Waistcoat', 'Nehru Jackets', 'Jackets', 'Tshirts'],
                  'F': ['Tops', 'Tunics', 'Kurtis', 'Shirts', 'Shrug', 'Blazers', 'Jackets']},
        'Ethnic': {'M': ['Kurtas', 'Nehru Jackets', 'Waistcoat'],
                   'F': ['Kurtas', 'Kurtis', 'Tunics', 'Lehenga Choli', 'Dupatta']},
        'Home': {'M': ['Tshirts', 'Sweatshirts', 'Shirts'],
                 'F': ['Tshirts', 'Tops', 'Tunics', 'Kurtis', 'Sweatshirts']},
    },
    'Bottomwear': {
        'Casual': {'M': ['Jeans', 'Shorts', 'Trousers', 'Capris'],
                   'F': ['Jeans', 'Capris', 'Shorts', 'Skirts', 'Leggings', 'Jeggings', 'Trousers']},
        'Formal': {'M': ['Trousers', 'Jeans'],
                   'F': ['Trousers', 'Skirts', 'Jeans']},
        'Sports': {'M': ['Track Pants', 'Shorts', 'Tracksuits', 'Capris'],
                   'F': ['Track Pants', 'Tights', 'Leggings', 'Shorts', 'Capris', 'Tracksuits']},
        'Party': {'M': ['Jeans', 'Trousers'],
                  'F': ['Skirts', 'Jeans', 'Jeggings', 'Trousers', 'Leggings']},
        'Ethnic': {'M': ['Churidar', 'Trousers'],
                   'F': ['Churidar', 'Salwar', 'Patiala', 'Salwar and Dupatta', 'Leggings', 'Trousers']},
        'Home': {'M': ['Track Pants', 'Shorts', 'Tracksuits', 'Capris'],
                 'F': ['Track Pants', 'Leggings', 'Capris', 'Shorts', 'Tights', 'Jeggings']},
    },
}


def garment_types(kind, occasion, gender):
    """Preferred articleTypes (best first) for `kind` ('Topwear'/'Bottomwear'), or None if unknown."""
    per_occ = GARMENT_TYPES.get(kind, {}).get(occasion)
    if per_occ is None:
        return None
    fam = _family(gender)
    if fam:
        return per_occ[fam]
    merged = []   # unknown gender: both lists, interleaved so the best of each comes first
    for a, b in zip(per_occ['M'] + [None] * 10, per_occ['F'] + [None] * 10):
        merged += [t for t in (a, b) if t and t not in merged]
    return merged


def garment_pool(items, kind, occasion, gender, min_items=5):
    """(rows, wanted_types, exact): tops/bottoms that suit the occasion, from `items` (one kind, one gender).

    Ethnic / Formal / Sports stay on the wanted types even if the pool is small, so jeans
    do not fill a festive or office ask. Other occasions may widen if the catalog is thin.
    """
    wanted = garment_types(kind, occasion, gender)
    if not wanted:
        return items, None, True
    pool = items[items['articleType'].isin(wanted)]
    if occasion in ('Ethnic', 'Formal', 'Sports') and len(pool) >= 1:
        return pool, wanted, True
    if len(pool) >= min_items:
        return pool, wanted, True
    return items, wanted, False


# ----------------------------------------------------------------------------- colour harmony
# Catalog colour names that map onto the ones CLIP detects (see detect.COLOURS).
COLOUR_ALIASES = {
    'Grey Melange': 'Grey', 'Steel': 'Grey', 'Charcoal': 'Grey', 'Silver': 'Grey',
    'Off White': 'White', 'Turquoise Blue': 'Teal', 'Sea Green': 'Green', 'Lime Green': 'Green',
    'Fluorescent Green': 'Green', 'Burgundy': 'Maroon', 'Coffee Brown': 'Brown', 'Taupe': 'Brown',
    'Mushroom Brown': 'Brown', 'Nude': 'Beige', 'Skin': 'Beige', 'Lavender': 'Purple', 'Mauve': 'Purple',
    'Magenta': 'Pink', 'Rose': 'Pink', 'Peach': 'Pink', 'Mustard': 'Yellow', 'Rust': 'Orange',
}
PLAIN_COLOURS = {'White', 'Grey', 'Beige', 'Cream', 'Black', 'Navy Blue', 'Khaki', 'Brown', 'Tan'}   # not 'flashy'
NEUTRALS = {'Black', 'White', 'Grey', 'Beige', 'Cream', 'Navy Blue', 'Khaki', 'Tan', 'Brown'}

# query colour -> partner colours, best first
PARTNERS = {
    'Black': ['White', 'Grey', 'Red', 'Blue', 'Beige', 'Pink', 'Yellow', 'Green'],
    'White': ['Blue', 'Black', 'Navy Blue', 'Grey', 'Beige', 'Khaki', 'Red', 'Olive', 'Brown', 'Green', 'Pink'],
    'Grey': ['Black', 'White', 'Navy Blue', 'Blue', 'Pink', 'Maroon'],
    'Navy Blue': ['White', 'Beige', 'Khaki', 'Grey', 'Cream', 'Tan', 'Pink', 'Brown', 'Blue'],
    'Blue': ['White', 'Black', 'Grey', 'Beige', 'Khaki', 'Navy Blue', 'Brown', 'Tan'],
    'Red': ['Black', 'White', 'Navy Blue', 'Grey', 'Beige', 'Blue'],
    'Maroon': ['Beige', 'White', 'Grey', 'Navy Blue', 'Black', 'Cream', 'Khaki'],
    'Green': ['White', 'Beige', 'Khaki', 'Black', 'Navy Blue', 'Grey', 'Brown'],
    'Olive': ['White', 'Beige', 'Khaki', 'Black', 'Navy Blue', 'Brown', 'Tan', 'Cream'],
    'Brown': ['Beige', 'White', 'Cream', 'Navy Blue', 'Khaki', 'Blue', 'Olive', 'Tan'],
    'Beige': ['Navy Blue', 'White', 'Brown', 'Olive', 'Black', 'Maroon', 'Blue', 'Green'],
    'Khaki': ['Navy Blue', 'White', 'Black', 'Olive', 'Brown', 'Maroon', 'Blue', 'Green'],
    'Cream': ['Navy Blue', 'Brown', 'Olive', 'Maroon', 'Black', 'Blue', 'Khaki'],
    'Tan': ['Navy Blue', 'White', 'Blue', 'Black', 'Olive', 'Cream'],
    'Pink': ['Grey', 'White', 'Navy Blue', 'Black', 'Beige', 'Blue'],
    'Yellow': ['Navy Blue', 'White', 'Grey', 'Black', 'Blue', 'Khaki'],
    'Purple': ['White', 'Grey', 'Black', 'Beige', 'Navy Blue'],
    'Orange': ['Navy Blue', 'White', 'Blue', 'Black', 'Grey', 'Khaki'],
    'Teal': ['White', 'Black', 'Grey', 'Beige', 'Navy Blue', 'Khaki'],
}


def _canon(colour):
    c = str(colour).strip()
    return COLOUR_ALIASES.get(c, c)


def harmony(query_colour, item_colour):
    """0..1 - how well two colours go together in one outfit (tonal and clashing pairs score low)."""
    q, c = _canon(query_colour), _canon(item_colour)
    if c == q:
        return 0.6 if q in NEUTRALS else 0.45          # head-to-toe same colour
    partners = PARTNERS.get(q, [])
    if c in partners:
        return max(0.7, 1.0 - 0.04 * partners.index(c))
    if c in NEUTRALS:
        return 0.55
    return 0.45 if q in NEUTRALS else 0.15              # two non-neutrals that are not known partners


def score_pool(pool, query_colour, occasion, wanted_types=None, is_footwear=False):
    """Recommendation score per row of `pool` (higher is better).

    Colour harmony (from the catalog's baseColour label, not from pixels) and occasion fit decide;
    visual similarity is only a small tie-break. Footwear also prefers earlier entries of `wanted_types`.
    """
    sim = pool['similarity'].to_numpy()
    span = sim.max() - sim.min()
    sim_norm = (sim - sim.min()) / span if span > 0 else np.zeros_like(sim)
    harm = pool['baseColour'].map(lambda c: harmony(query_colour, c)).to_numpy()

    if wanted_types:
        rank = pool['articleType'].map({t: i for i, t in enumerate(wanted_types)}).fillna(len(wanted_types)).to_numpy()
        if is_footwear:
            type_pref = np.clip(1.0 - 0.25 * rank, 0.1, 1.0)
            total = 0.45 * type_pref + 0.45 * harm + 0.10 * sim_norm
        else:   # tops / bottoms: type + colour first; usage is only a nudge
            type_pref = np.clip(1.0 - 0.22 * rank, 0.05, 1.0)
            occ = (pool['usage'] == occasion).to_numpy().astype(float)
            total = 0.42 * harm + 0.38 * type_pref + 0.12 * occ + 0.08 * sim_norm
    else:
        occ = (pool['usage'] == occasion).to_numpy().astype(float)
        total = 0.60 * harm + 0.30 * occ + 0.10 * sim_norm
    return pd.Series(total, index=pool.index)


def pick_diverse(rows_sorted, k, max_per_type=3, max_per_colour=2):
    """Top-k rows (already sorted best first), varied in articleType and colour.

    Three passes: both caps, then only the type cap, then no caps - so a narrow pool still
    returns k items instead of coming back short.
    """
    types = rows_sorted['articleType'].tolist()
    colours = ([_canon(c) for c in rows_sorted['baseColour']] if 'baseColour' in rows_sorted
               else rows_sorted['articleType'].tolist())
    index = rows_sorted.index.tolist()
    chosen = []
    for type_cap, colour_cap in ((max_per_type, max_per_colour), (max_per_type, None), (None, None)):
        t_count, c_count = {}, {}
        chosen = []
        for i, t, c in zip(index, types, colours):
            if type_cap is not None and t_count.get(t, 0) >= type_cap:
                continue
            if colour_cap is not None and c_count.get(c, 0) >= colour_cap:
                continue
            t_count[t] = t_count.get(t, 0) + 1
            c_count[c] = c_count.get(c, 0) + 1
            chosen.append(i)
            if len(chosen) == k:
                return rows_sorted.loc[chosen]
    return rows_sorted.loc[chosen]


# ----------------------------------------------------------------------------- chat: "outfit for Diwali"
import re

OCCASION_WORDS = {
    'Ethnic': ['diwali', 'deepawali', 'shaadi', 'shadi', 'wedding', 'festive', 'festival', 'tyohar', 'ethnic',
               'puja', 'pooja', 'eid', 'navratri', 'garba', 'dandiya', 'karwa', 'chauth', 'sangeet', 'mehndi', 'haldi', 'traditional', 'rakhi', 'holi'],
    'Party': ['party', 'date', 'club', 'birthday', 'cocktail', 'reception', 'newyear'],
    'Formal': ['office', 'formal', 'interview', 'meeting', 'business', 'corporate', 'presentation'],
    'Sports': ['gym', 'workout', 'running', 'sports', 'sport', 'jogging', 'yoga', 'cricket', 'football', 'training'],
    'Home': ['home', 'ghar', 'lounge', 'loungewear', 'homewear'],
    'Casual': ['casual', 'college', 'daily', 'outing', 'movie', 'shopping', 'travel', 'trip', 'hangout'],
}
GENDER_WORDS = {
    'Men': ['men', 'man', 'mens', 'male', 'gents', 'guys', 'ladka', 'ladke', 'boyfriend', 'husband', 'him'],
    'Women': ['women', 'woman', 'womens', 'female', 'ladies', 'lady', 'ladki', 'ladkiyon', 'girlfriend', 'wife', 'her'],
    'Boys': ['boy', 'boys', 'beta'],
    'Girls': ['girl', 'girls', 'beti'],
}
OUTFIT_WORDS = {'outfit', 'outfits', 'look', 'pehnu', 'pehnun', 'pehnu', 'pehnoon', 'pehne', 'pehno', 'wear',
                'styling', 'combination', 'combo'}


# occasions where people dress up in bright, embroidered, shiny clothes
FESTIVE_WORDS = {'diwali', 'deepawali', 'shaadi', 'shadi', 'wedding', 'festive', 'festival', 'tyohar', 'navratri',
                 'sangeet', 'mehndi', 'haldi', 'eid', 'reception', 'cocktail', 'garba', 'dandiya', 'karwa', 'karva',
                 'chauth', 'karwachauth', 'karvachauth', 'karwachouth', 'karvachouth', 'bridal', 'dulhan'}
# Karwa Chauth is for married women: red / maroon / pink saree or lehenga with gold jewellery
KARWA_WORDS = {'karwa', 'karva', 'chauth', 'karwachauth', 'karvachauth', 'karwachouth', 'karvachouth'}
KARWA_COLOURS = ['Red', 'Maroon', 'Magenta', 'Pink']

# a specific hero garment asked for in chat ("saree dikhao", "lehenga for shaadi")
GARMENT_WORDS = {
    'Saree': {'saree', 'sarees', 'sari', 'saris', 'saaree'},
    'Lehenga': {'lehenga', 'lehengas', 'lehnga', 'ghagra', 'choli', 'lehengacholi'},
    'Kurta Sets': {'anarkali', 'salwar', 'suit', 'suits', 'kurtaset', 'kurtasets', 'patiala'},
}
KID_WORDS = {'kid', 'kids', 'child', 'children', 'bachha', 'bacha', 'bachhe', 'bacche', 'baby', 'toddler', 'junior'}
# festive things people ask for that this catalog simply does not contain
NOT_IN_CATALOG = {'sherwani': 'sherwani', 'mojari': 'mojari', 'mojaris': 'mojari', 'jutti': 'jutti', 'juttis': 'jutti',
                  'juti': 'jutti', 'dhoti': 'dhoti', 'pagdi': 'pagdi', 'safa': 'safa', 'bandhgala': 'bandhgala',
                  'indowestern': 'indo-western'}
COLOUR_WORDS = {
    'Red': ['red', 'lal'], 'Maroon': ['maroon'], 'Pink': ['pink', 'gulabi'], 'Blue': ['blue', 'neela', 'nila'],
    'Green': ['green', 'hara'], 'Yellow': ['yellow', 'peela'], 'Black': ['black', 'kala'],
    'White': ['white', 'safed'], 'Orange': ['orange', 'kesari'], 'Purple': ['purple', 'baingani', 'jamuni'],
    'Gold': ['gold', 'golden', 'sunehri'],
}
HELP_WORDS = {'dedo', 'do', 'batao', 'bata', 'suggest', 'chahiye', 'chahie', 'ke', 'liye', 'for', 'kya',
              'dikhao', 'dikha', 'dikhaiye', 'show', 'dekhna', 'chahta', 'chahti'}


def parse_request(question, gender_filter='Any', usage_filter='Any'):
    """Understand a chat request.

    Returns {'outfit': bool, 'occasion', 'gender', 'festive', 'main', 'colours', 'missing'}:
    'ethnic wear outfit dedo diwali ke liye' -> outfit for Ethnic; 'saree dikhao' -> sarees
    (main='Saree'); 'karwachauth ke liye' -> a red / maroon / pink look for women; 'blue jeans for men'
    -> a plain product search (outfit False). `missing` lists asked-for items the catalog does not have
    (sherwani, mojari ...). The sidebar filters are used when the text does not say.
    """
    words = set(re.findall(r"[a-z]+", str(question).lower()))
    occasion = next((o for o, ws in OCCASION_WORDS.items() if words & set(ws)), None)
    gender = next((g for g, ws in GENDER_WORDS.items() if words & set(ws)), None)
    if gender in ('Boys', 'Girls') and not (words & KID_WORDS) and not (words & {'beta', 'beti'}):
        gender = 'Men' if gender == 'Boys' else 'Women'     # "boys" / "girls" usually means young men / women
    main = next((g for g, ws in GARMENT_WORDS.items() if words & ws), None)
    colours = [c for c, ws in COLOUR_WORDS.items() if words & set(ws)]
    missing = sorted({NOT_IN_CATALOG[w] for w in words if w in NOT_IN_CATALOG})
    karwa = bool(words & KARWA_WORDS)
    if main is None and 'kurta' in words and words & {'set', 'sets'}:
        main = 'Kurta Sets'
    if occasion is None and (karwa or words & {'bridal', 'dulhan'}):
        occasion = 'Ethnic'

    if main == 'Kurta Sets' and gender in ('Men', 'Boys'):
        main = None                                   # "suit" for men is not a salwar suit
    if main and occasion is None:
        occasion = 'Ethnic'
    if gender is None:
        if gender_filter in ('Men', 'Women', 'Boys', 'Girls'):
            gender = gender_filter
        elif main or karwa:
            gender = 'Women'
    if karwa and not colours:
        colours = list(KARWA_COLOURS)
    text_occasion = occasion
    outfit = bool(words & OUTFIT_WORDS) or (text_occasion is not None and bool(words & HELP_WORDS)) or bool(main)
    # a plain product search that merely mentions a garment is not an outfit request
    if outfit and not (words & OUTFIT_WORDS) and not text_occasion and not main:
        outfit = False
    if occasion is None and outfit and usage_filter in OCCASIONS:
        occasion = usage_filter
    festive = bool(words & FESTIVE_WORDS) or occasion == 'Party' or bool(main)
    return {'outfit': outfit, 'occasion': occasion, 'gender': gender, 'festive': festive,
            'main': main, 'colours': colours, 'missing': missing}


GOLDEN = {'Gold', 'Silver', 'Bronze', 'Copper', 'Multi', 'Maroon', 'Red', 'Magenta'}


def build_festive_boards(base, n, rng, gender='Women', main=None, colours=None):
    """Heavy festive looks as styling boards: the hero piece (saree / kurta set / lehenga for women,
    a kurta look for men; the whole look in one photo) plus accessories. Women: dupatta (with kurta
    sets), jewellery, clutch, footwear. Men: Nehru jacket / waistcoat (while the catalog has them),
    watch, footwear. Ranked by the CLIP "flashy" score and by the colours the user asked for.

    Returns [{'kind': 'board', 'Main': row, ...}] - fewer than n if the catalog runs out of that hero piece.
    """
    prefer = {_canon(c) for c in (colours or [])}

    def colour_narrow(pool):
        """Asked colour first; else partner colours (similar); else the whole pool (similar)."""
        if pool is None or pool.empty or not prefer:
            return pool, False
        hit = pool[pool['baseColour'].map(_canon).isin(prefer)]
        if len(hit) >= 1:
            return hit, False
        partners = set(prefer)
        for c in prefer:
            partners.update(PARTNERS.get(c, []))
        near = pool[pool['baseColour'].map(_canon).isin(partners)]
        if len(near) >= 1:
            return near, True
        return pool, True

    def best(pool, colour=None, wanted=None, glitter=False, used=(), prefer_colours=False, flash=0.6, dressy=0.0, avoid_looks=None):
        pool = pool[~pool.index.isin(used)]
        if avoid_looks:
            def _look_type(t):
                return 'Sandals' if t in ('Flats', 'Sandals') else t
            keys = pool['articleType'].map(_look_type).astype(str) + '|' + pool['baseColour'].map(_canon)
            slim = pool[~keys.isin(avoid_looks)]
            if len(slim) >= 1:
                pool = slim
        if pool.empty:
            return None
        sc = flash * pool['flashy'].to_numpy() + 0.15 * rng.random(len(pool))
        if colour is not None:
            sc = sc + 0.3 * pool['baseColour'].map(lambda c: harmony(colour, c)).to_numpy()
        if glitter:     # gold / silver finishes look festive
            sc = sc + 0.4 * pool['baseColour'].isin(GOLDEN).to_numpy()
        if prefer_colours:       # the hero piece: wanted colours up, plain white / grey / beige down
            if prefer:
                sc = sc + 1.2 * pool['baseColour'].map(_canon).isin(prefer).to_numpy()
            sc = sc - 0.4 * pool['baseColour'].map(_canon).isin(PLAIN_COLOURS).to_numpy()
        if wanted:
            rank = pool['articleType'].map({t: i for i, t in enumerate(wanted)}).fillna(len(wanted)).to_numpy()
            sc = sc + 0.4 * np.clip(1.0 - 0.3 * rank, 0.0, 1.0)
        if dressy and 'dressy' in pool:      # strappy heels / embellished sandals, not flip flops
            sc = sc + dressy * pool['dressy'].to_numpy()
        return pool.assign(score=sc).sort_values('score', ascending=False).iloc[0]

    shoes, shoe_wanted, _ = footwear_pool(base[base['masterCategory'] == 'Footwear'], 'Ethnic', gender)
    if gender == 'Women' and 'dressy' in shoes:
        smart = shoes[shoes['dressy'] >= 0.6]            # the catalog's "Flats" are often thong flip flops
        if len(smart) >= 10:
            shoes = smart
    if gender in ('Girls', 'Boys'):
        # kids: the catalog has no kids' kurtas / sarees, so use what festive kids' wear exists
        # (girls: dresses and lehenga choli; boys: kurta sets and kurtas) with footwear
        if gender == 'Girls':
            main_pools = {'Dresses': base[base['subCategory'] == 'Dress'],
                          'Lehenga': base[base['articleType'] == 'Lehenga Choli']}
        else:
            main_pools = {'Kurta Sets': base[base['articleType'] == 'Kurta Sets'],
                          'Kurtas': base[(base['subCategory'] == 'Topwear') & (base['articleType'] == 'Kurtas')]}
        kinds = list(main_pools)
        extras = (('Footwear', shoes, dict(wanted=shoe_wanted, flash=0.1)),)
    elif gender == 'Men':
        main_pools = {'Kurtas': base[(base['subCategory'] == 'Topwear') & (base['articleType'] == 'Kurtas')]}
        kinds = ['Kurtas']
        jackets = base[base['articleType'].isin(['Nehru Jackets', 'Waistcoat'])]
        watches = base[base['subCategory'] == 'Watches']
        extras = (('Jacket', jackets, dict(prefer_colours=False, flash=0.2)),
                  ('Watch', watches, dict(glitter=True, flash=0.2)),
                  ('Footwear', shoes, dict(wanted=shoe_wanted, flash=0.1)))
    else:
        main_pools = {
            'Saree': base[base['subCategory'] == 'Saree'],
            'Kurta Sets': base[base['articleType'] == 'Kurta Sets'],
            'Lehenga': base[base['articleType'] == 'Lehenga Choli'],
        }
        kinds = [main] if main in main_pools else ['Saree', 'Kurta Sets']
        dupattas = base[base['articleType'] == 'Dupatta']
        jewel = base[(base['subCategory'] == 'Jewellery') &
                     base['articleType'].isin(['Jewellery Set', 'Necklace and Chains', 'Earrings'])]
        bags = base[(base['subCategory'] == 'Bags') & (base['articleType'] == 'Clutches')]
        extras = (('Dupatta', dupattas, dict(flash=0.4)),
                  ('Jewellery', jewel, dict(glitter=True, wanted=['Jewellery Set', 'Necklace and Chains', 'Earrings'])),
                  ('Bag', bags, dict()),
                  ('Footwear', shoes, dict(wanted=shoe_wanted, flash=0.2, dressy=0.8)))

    boards, used, used_looks = [], set(), set()

    def fill(kind_list, similar=False):
        exhausted, i = set(), 0
        while len(boards) < n and len(exhausted) < len(kind_list):
            kind = kind_list[i % len(kind_list)]
            i += 1
            if kind in exhausted:
                continue
            hero_pool, colour_off = colour_narrow(main_pools[kind])
            hero = best(hero_pool, used=used, prefer_colours=True, flash=0.5)
            if hero is None:
                exhausted.add(kind)
                continue
            used.add(hero.name)
            board = {'kind': 'board', 'Main': hero}
            if similar or colour_off:
                board['similar'] = True
            for role, pool, kw in extras:
                if role == 'Dupatta' and kind in ('Saree', 'Lehenga', 'Kurta Sets'):
                    continue            # saree has its pallu; lehenga and kurta sets come with their own dupatta
                kw = dict(kw)
                if role in ('Dupatta', 'Footwear', 'Jacket'):
                    kw['colour'] = hero['baseColour']
                pick = best(pool, used=used, avoid_looks=used_looks, **kw)
                if pick is not None:
                    if role == 'Footwear' and gender == 'Women' and pick['articleType'] == 'Flats' \
                            and pick.get('dressy', 0) >= 0.6:
                        pick = pick.copy()
                        pick['articleType'] = 'Sandals'      # the catalog calls strappy dress sandals "Flats"
                    board[role] = pick
                    used.add(pick.name)
                    if role in ('Bag', 'Footwear', 'Jewellery', 'Watch'):
                        look_type = 'Sandals' if pick['articleType'] in ('Flats', 'Sandals') else pick['articleType']
                        used_looks.add(f"{look_type}|{_canon(pick['baseColour'])}")
            boards.append(board)

    fill(kinds)
    if gender == 'Women' and main and len(boards) < n:
        # the catalog has only a few of the asked-for piece (e.g. 2 lehengas): add similar festive
        # hero pieces and mark them, so the user still gets enough options
        similar = {'Lehenga': ['Saree', 'Kurta Sets'], 'Kurta Sets': ['Lehenga', 'Saree'],
                   'Saree': ['Lehenga', 'Kurta Sets']}.get(main, [])
        fill(similar, similar=True)
    return boards


def build_outfits(catalog, occasion, gender, n=2, seed=0, festive=False, boards_ok=True,
                  main=None, colours=None):
    """A list of `n` complete outfits: [{'Top': row, 'Bottom': row, 'Footwear': row}, ...].

    Tops are chosen for the occasion (garment type + the catalog's usage label, with a little
    randomness so repeated asks vary). For each top, the bottom and the footwear are then ranked by
    colour harmony with THAT top and by occasion fit; an item is never used in two outfits.
    """
    rng = np.random.default_rng(seed)
    base = catalog[catalog['gender'] == gender] if gender else catalog
    base = base.assign(similarity=0.0)

    if boards_ok and festive and gender in ('Women', 'Men', 'Girls', 'Boys') and occasion == 'Ethnic' and 'flashy' in base:
        # heavy festive looks: saree / kurta set / lehenga + accessories (women), kurta + jacket + watch (men)
        boards = build_festive_boards(base, n, rng, gender, main, colours)
        if len(boards) >= n or (main and gender == 'Women'):
            return boards[:n]          # a specific garment was asked for: do not pad with other things
        if boards:
            return boards + build_outfits(catalog, occasion, gender, n - len(boards), seed + 1, festive, False,
                                          colours=colours)

    def narrow(pool, wanted):
        """Ethnic / Formal asks are specific (kurta + churidar, shirt + trousers): use the best-ranked
        garment types alone when there are enough of them, instead of letting jeans etc. creep in."""
        if occasion in ('Ethnic', 'Formal') and wanted:
            for i in range(1, len(wanted) + 1):
                sub = pool[pool['articleType'].isin(wanted[:i])]
                if len(sub) >= n * 6:
                    return sub
        return pool

    def usable(pool):
        good = pool[pool['photo_ok']] if 'photo_ok' in pool else pool
        return good if len(good) >= n * 6 else pool

    tops, wanted, _ = garment_pool(base[base['subCategory'] == 'Topwear'], 'Topwear', occasion, gender)
    tops = usable(narrow(tops, wanted))
    if wanted:
        rank = tops['articleType'].map({t: i for i, t in enumerate(wanted)}).fillna(len(wanted)).to_numpy()
        type_pref = np.clip(1.0 - 0.15 * rank, 0.2, 1.0)
    else:
        type_pref = np.ones(len(tops))
    usage_hit = (tops['usage'] == occasion).to_numpy()
    if festive and 'flashy' in tops:
        # festive (Diwali, wedding, party): bright, embroidered, shiny pieces - not plain white / beige / grey
        dull = tops['baseColour'].map(_canon).isin(PLAIN_COLOURS).to_numpy()
        score = (0.25 * type_pref + 0.10 * usage_hit + 0.50 * tops['flashy'].to_numpy()
                 - 0.25 * dull + 0.10 * rng.random(len(tops)))
    else:
        score = 0.5 * type_pref + 0.3 * usage_hit + 0.2 * rng.random(len(tops))
    if colours:       # colours the user asked for ("red saree", Karwa Chauth ...)
        score = score + 0.6 * tops['baseColour'].map(_canon).isin({_canon(c) for c in colours}).to_numpy()
    top_rows = pick_diverse(tops.assign(score=score).sort_values('score', ascending=False), n)

    bottoms, b_wanted, _ = garment_pool(base[base['subCategory'] == 'Bottomwear'], 'Bottomwear', occasion, gender)
    bottoms = usable(narrow(bottoms, b_wanted))
    shoes, s_wanted, _ = footwear_pool(base[base['masterCategory'] == 'Footwear'], occasion, gender)
    shoes = usable(shoes)

    outfits, used, used_look = [], set(), set()
    for _, top in top_rows.iterrows():
        outfit = {'Top': top}
        for role, pool, wanted_types, is_shoe in (('Bottom', bottoms, b_wanted, False),
                                                  ('Footwear', shoes, s_wanted, True)):
            looks = pool['articleType'] + '|' + pool['baseColour'].astype(str)
            free = pool[~pool.index.isin(used) & ~looks.isin(used_look)]    # a new item AND a new look
            if free.empty:
                free = pool[~pool.index.isin(used)]
            if free.empty:
                free = pool
            if free.empty:
                outfit = None
                break
            sc = score_pool(free, top['baseColour'], occasion, wanted_types, is_footwear=is_shoe)
            if festive and 'flashy' in free:
                sc = sc + (0.08 if is_shoe else 0.25) * free['flashy']       # rich, decorated pieces
            if is_shoe and gender == 'Women' and occasion in ('Ethnic', 'Party', 'Formal') and 'dressy' in free:
                sc = sc + 0.5 * free['dressy']                               # heels / dressy sandals, no flip flops
            ranked = free.assign(score=sc).sort_values('score', ascending=False)
            pick = pick_diverse(ranked, 1).iloc[0]
            outfit[role] = pick
            used.add(pick.name)
            used_look.add(f"{pick['articleType']}|{pick['baseColour']}")
        if outfit:
            outfits.append(outfit)
    return outfits