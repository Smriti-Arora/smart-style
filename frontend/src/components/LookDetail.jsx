import { lookKey, lookTitle, pinLook, togglePin } from "../history.js";

export default function LookDetail({
  look,
  similar = [],
  query,
  gender,
  occasion,
  pinned,
  onClose,
  onSaved,
  onTryOn,
  onRestyle,
  onOpen,
}) {
  if (!look) return null;
  const title = lookTitle({ ...look, query: look.query || query });

  async function onTry(e) {
    const btn = e.currentTarget;
    if (!look.tryon?.length || !onTryOn) return;
    btn.disabled = true;
    btn.textContent = "Opening…";
    try {
      await onTryOn(look.tryon, { query: query || look.query, gender, occasion, look });
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

  return (
    <div className="detail" role="dialog" aria-label={title} onClick={onClose}>
      <div className="detail-card" onClick={(e) => e.stopPropagation()}>
        <button className="btn ghost detail-x" type="button" onClick={onClose}>
          Close
        </button>
        <img className="detail-photo" src={look.image} alt={look.caption || title} />
        <div className="detail-meta">
          <p className="you">{look.query || query}</p>
          <h2>
            {title}
            {look.similar ? <span className="badge">closest</span> : null}
          </h2>
          {look.note || look.caption ? <p className="reply">{look.note || look.caption}</p> : null}
          {look.items?.length ? (
            <ul>
              {look.items.map((it, i) => (
                <li key={i}>
                  <span className="dot" style={{ background: it.hex }} />
                  {it.role} · {it.name} {it.colour}
                </li>
              ))}
            </ul>
          ) : null}
          <div className="actions">
            {look.tryon?.length && onTryOn ? (
              <button className="btn" type="button" onClick={onTry}>
                Try on
              </button>
            ) : null}
            {onRestyle && (look.query || look.prompt || query) ? (
              <button className="btn ghost" type="button" onClick={() => onRestyle(look)}>
                Restyle
              </button>
            ) : null}
            {onSaved ? (
              <button className={"btn ghost" + (pinned ? " on" : "")} type="button" onClick={onSave}>
                {pinned ? "Saved" : "Save"}
              </button>
            ) : null}
          </div>
          {similar.length ? (
            <>
              <h3 className="subhead">Similar looks</h3>
              <div className="thumbs">
                {similar.map((s) => (
                  <button
                    key={s.image || s.n || s.label}
                    type="button"
                    className="thumb-btn"
                    onClick={() => onOpen?.(s)}
                  >
                    <img src={s.image} alt={s.caption || lookTitle(s)} />
                  </button>
                ))}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
