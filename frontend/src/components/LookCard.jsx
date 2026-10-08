import { lookKey, lookTitle, pinLook, timeAgo, togglePin } from "../history.js";

export default function LookCard({ look, query, gender, occasion, pinned, onSaved, onRestyle, onTryOn, onOpen }) {
  async function onTry(e) {
    const btn = e.currentTarget;
    if (!look.tryon?.length || !onTryOn) return;
    btn.disabled = true;
    btn.textContent = "Opening…";
    try {
      await onTryOn(look.tryon, { query: query || look.query, gender, occasion, look });
    } catch {
      /* overlay handles errors */
    } finally {
      btn.disabled = false;
      btn.textContent = "Try on";
    }
  }

  function onSave() {
    const next = pinned
      ? togglePin(look.key || lookKey(look))
      : pinLook(look, { query: query || look.query, gender, occasion, source: look.source });
    onSaved?.(next);
  }

  const when = timeAgo(look.savedAt);
  const bits = [when, look.gender && look.gender !== "Any" ? look.gender : gender !== "Any" ? gender : "", look.occasion && look.occasion !== "Any" ? look.occasion : occasion !== "Any" ? occasion : ""].filter(Boolean);

  return (
    <article className="look">
      <button type="button" className="look-pic" onClick={() => onOpen?.(look)}>
        <img src={look.image} alt={look.caption || lookTitle(look)} />
      </button>
      <div className="meta">
        <h3>
          {lookTitle({ ...look, query: look.query || query })}
          {look.similar ? <span className="badge">closest</span> : null}
          {pinned ? <span className="badge">saved</span> : null}
        </h3>
        {bits.length ? <p className="when">{bits.join(" · ")}</p> : null}
        <ul>
          {(look.items || []).map((it, i) => (
            <li key={i}>
              <span className="dot" style={{ background: it.hex }} />
              {it.role} · {it.name} {it.colour}
            </li>
          ))}
        </ul>
        {look.note ? <p className="note">{look.note}</p> : null}
      </div>
      <div className="actions">
        {look.tryon?.length && onTryOn ? (
          <button className="btn" type="button" onClick={onTry}>
            Try on
          </button>
        ) : null}
        {onRestyle && (look.query || query) ? (
          <button className="btn ghost" type="button" onClick={() => onRestyle(look)}>
            Restyle
          </button>
        ) : null}
        <button className={"btn ghost" + (pinned ? " on" : "")} type="button" onClick={onSave}>
          {pinned ? "Saved" : "Save"}
        </button>
      </div>
    </article>
  );
}
