import LookCard from "./LookCard.jsx";
import Skeletons from "./Skeletons.jsx";
import { lookKey } from "../history.js";

function Grid({ looks, query, gender, occasion, pinnedKeys, onSaved, onTryOn, onOpen }) {
  if (!looks.length) return null;
  return (
    <div className="grid">
      {looks.map((look) => (
        <LookCard
          key={look.image || look.n}
          look={look}
          query={query}
          gender={gender}
          occasion={occasion}
          pinned={pinnedKeys?.has(lookKey(look))}
          onSaved={onSaved}
          onTryOn={onTryOn}
          onOpen={onOpen}
        />
      ))}
    </div>
  );
}

export default function Results({ session, onClose, onRetry, onSaved, onTryOn, onOpen, gender, occasion, pinnedKeys }) {
  if (!session) return null;
  const outfits = session.outfits || [];
  const exact = outfits.filter((o) => !o.similar);
  const closest = outfits.filter((o) => o.similar);
  return (
    <div className="sheet" role="dialog" aria-label="Your looks">
      <div className="sheet-head">
        <div>
          <p className="you">{session.query}</p>
          <h2>Your looks</h2>
        </div>
        <button className="btn ghost" type="button" onClick={onClose}>
          Close
        </button>
      </div>
      {session.reply && !session.failed ? <p className="reply">{session.reply}</p> : null}
      {session.waiting ? (
        <>
          <p className="wait">Finding looks…</p>
          <Skeletons n={3} />
        </>
      ) : null}
      {session.failed ? (
        <p className="fail">
          {session.reply || "Could not finish that."}
          {onRetry ? (
            <button className="btn" type="button" onClick={onRetry}>
              Retry
            </button>
          ) : null}
        </p>
      ) : null}
      <Grid
        looks={exact}
        query={session.query}
        gender={gender}
        occasion={occasion}
        pinnedKeys={pinnedKeys}
        onSaved={onSaved}
        onTryOn={onTryOn}
        onOpen={onOpen}
      />
      {closest.length ? (
        <>
          <h3 className="subhead">Closest alternatives</h3>
          <p className="hint">Same vibe, not the exact piece you asked for.</p>
          <Grid
            looks={closest}
            query={session.query}
            gender={gender}
            occasion={occasion}
            pinnedKeys={pinnedKeys}
            onSaved={onSaved}
            onTryOn={onTryOn}
            onOpen={onOpen}
          />
        </>
      ) : null}
      {session.images?.length ? (
        <div className="thumbs">
          {session.images.map((im) => (
            <img key={im.id || im.image} src={im.image} alt={im.caption} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
