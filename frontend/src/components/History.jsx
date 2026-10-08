import { useMemo, useState } from "react";
import LookCard from "./LookCard.jsx";
import { clearRecents, removeLook } from "../history.js";

export default function History({ items, onChange, onRestyle, onTryOn, onOpen }) {
  const [tab, setTab] = useState("saved");
  const [q, setQ] = useState("");
  const saved = items.filter((x) => x.pinned);
  const recent = items.filter((x) => !x.pinned);
  const pool = tab === "saved" ? saved : recent;

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return pool;
    return pool.filter((look) => {
      const blob = [
        look.query,
        look.gender,
        look.occasion,
        look.source,
        ...(look.items || []).flatMap((it) => [it.role, it.name, it.colour]),
      ]
        .join(" ")
        .toLowerCase();
      return blob.includes(needle);
    });
  }, [pool, q]);

  return (
    <section className="wrap">
      <h2>History</h2>
      <p className="hint">Recent looks stay after you close results. Save the ones you want to keep.</p>
      <div className="hist-bar">
        <div className="tabs">
          <button className={tab === "saved" ? "on" : ""} type="button" onClick={() => setTab("saved")}>
            Saved{saved.length ? ` (${saved.length})` : ""}
          </button>
          <button className={tab === "recent" ? "on" : ""} type="button" onClick={() => setTab("recent")}>
            Recent{recent.length ? ` (${recent.length})` : ""}
          </button>
        </div>
        <input
          className="hist-search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search looks, colour, occasion…"
        />
        {tab === "recent" && recent.length ? (
          <button className="link" type="button" onClick={() => onChange(clearRecents())}>
            Clear recents
          </button>
        ) : null}
      </div>
      {!shown.length ? (
        <p className="hint">
          {q
            ? "No looks match that search."
            : tab === "saved"
              ? "Nothing saved yet. Open a look and tap Save."
              : "Style a look or upload a closet photo — it will show up here."}
        </p>
      ) : (
        <div className="grid">
          {shown.map((look) => (
            <div key={look.key} className="hist">
              <LookCard
                look={look}
                query={look.query}
                gender={look.gender}
                occasion={look.occasion}
                pinned={look.pinned}
                onSaved={onChange}
                onRestyle={onRestyle}
                onTryOn={onTryOn}
                onOpen={onOpen}
              />
              <button className="link" type="button" onClick={() => onChange(removeLook(look.key))}>
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
