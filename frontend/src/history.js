const MAX_RECENT = 30;
const MAX_PINNED = 40;
let account = "guest";

export function setHistoryUser(id) {
  account = id ? String(id) : "guest";
}

function storageKey() {
  return `smartstyle.history.${account}`;
}

export function lookKey(look) {
  if (look.key) return look.key;
  const ids = (look.tryon || []).map((t) => t.id).join("-");
  if (ids) return ids;
  const img = look.image || "";
  if (img && !String(img).startsWith("data:")) return img;
  return `look-${look.n || look.savedAt || Date.now()}`;
}

export function loadHistory() {
  try {
    const raw = JSON.parse(localStorage.getItem(storageKey()) || "[]");
    const rows = Array.isArray(raw) ? raw : raw.items || [];
    return rows.map((x) => ({
      ...x,
      key: x.key || lookKey(x),
      query: x.query || "",
      gender: x.gender || "Any",
      occasion: x.occasion || "Any",
      source: x.source || "looks",
      pinned: !!x.pinned,
      savedAt: x.savedAt || 0,
    }));
  } catch {
    return [];
  }
}

function persist(items) {
  const pinned = items.filter((x) => x.pinned).slice(0, MAX_PINNED);
  const keys = new Set(pinned.map((x) => x.key));
  const recent = items.filter((x) => !x.pinned && !keys.has(x.key)).slice(0, MAX_RECENT);
  const next = [...pinned, ...recent];
  localStorage.setItem(storageKey(), JSON.stringify(next));
  return next;
}

function row(look, extra = {}) {
  const prev = extra.prev;
  return {
    ...look,
    key: lookKey(look),
    query: extra.query ?? look.query ?? prev?.query ?? "",
    gender: extra.gender ?? look.gender ?? prev?.gender ?? "Any",
    occasion: extra.occasion ?? look.occasion ?? prev?.occasion ?? "Any",
    source: extra.source ?? look.source ?? prev?.source ?? "looks",
    pinned: extra.pinned ?? prev?.pinned ?? false,
    savedAt: extra.savedAt ?? Date.now(),
  };
}

export function addRecents(looks, meta = {}) {
  let items = loadHistory();
  for (const look of looks || []) {
    const key = lookKey(look);
    const prev = items.find((x) => x.key === key);
    items = [row(look, { ...meta, prev, savedAt: Date.now() }), ...items.filter((x) => x.key !== key)];
  }
  return persist(items);
}

export function pinLook(look, meta = {}) {
  const items = loadHistory();
  const key = lookKey(look);
  const prev = items.find((x) => x.key === key);
  return persist([
    row(look, { ...meta, prev, pinned: true, savedAt: Date.now() }),
    ...items.filter((x) => x.key !== key),
  ]);
}

export function togglePin(key) {
  return persist(
    loadHistory().map((x) => (x.key === key ? { ...x, pinned: !x.pinned, savedAt: Date.now() } : x))
  );
}

export function removeLook(key) {
  return persist(loadHistory().filter((x) => x.key !== key));
}

export function clearRecents() {
  return persist(loadHistory().filter((x) => x.pinned));
}

export function timeAgo(ts) {
  if (!ts) return "";
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 45) return "Just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d ago`;
  return new Date(ts).toLocaleDateString();
}

export function lookTitle(look) {
  const q = (look.query || "").trim();
  if (q) return q.length > 48 ? `${q.slice(0, 46)}…` : q;
  return `Look ${look.n || ""}`.trim();
}
