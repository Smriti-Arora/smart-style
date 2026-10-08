import { useRef, useState } from "react";
import LookCard from "./LookCard.jsx";
import Skeletons from "./Skeletons.jsx";
import { matchUpload, warmTryOn } from "../api.js";
import { addRecents, lookKey } from "../history.js";

export default function Closet({ gender, occasion, onSaved, pinnedKeys, onTryOn, onOpen }) {
  const last = useRef(null);
  const [piece, setPiece] = useState(null);
  const [reply, setReply] = useState("");
  const [outfits, setOutfits] = useState([]);
  const [hits, setHits] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function send(file) {
    if (!file) return;
    last.current = file;
    const preview = URL.createObjectURL(file);
    setPiece({ preview, title: "Reading…", sub: "Matching colour, then finishing the look." });
    setBusy(true);
    setError("");
    setReply("");
    setOutfits([]);
    setHits([]);
    try {
      const data = await matchUpload(file, gender, occasion);
      setPiece({
        preview,
        title: `${data.colour} ${data.articleType}`,
        sub: `${data.gender} · ${data.occasion} · ${Math.round((data.confidence || 0) * 100)}%`,
      });
      setReply(data.reply || "");
      setOutfits(data.outfits || []);
      setHits(data.matches || []);
      (data.outfits || []).forEach((o) => warmTryOn(o.tryon));
      if (data.outfits?.length) {
        onSaved?.(
          addRecents(data.outfits, {
            query: `${data.colour} ${data.articleType}`.trim(),
            gender: data.gender || gender,
            occasion: data.occasion || occasion,
            source: "closet",
          })
        );
      }
    } catch (e) {
      setError(e.message || "Could not read that photo. Try again.");
    } finally {
      setBusy(false);
    }
  }

  function onDrop(e) {
    e.preventDefault();
    send(e.dataTransfer.files?.[0]);
  }

  return (
    <section className="wrap">
      <h2>Closet</h2>
      <p className="hint">Upload a t-shirt or top. We add a bottom and shoes for the gender and occasion above.</p>
      <div className="closet-row">
        <label className="drop" onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
          <input type="file" accept="image/jpeg,image/png,image/jpg" onChange={(e) => send(e.target.files[0])} />
          Drop a photo or browse
        </label>
        {piece ? (
          <div className="piece">
            <img src={piece.preview} alt={piece.title} />
            <div>
              <h3>{piece.title}</h3>
              <p>{piece.sub}</p>
            </div>
          </div>
        ) : null}
      </div>
      {busy ? (
        <>
          <p className="wait">Adding bottom and shoes…</p>
          <Skeletons n={3} />
        </>
      ) : null}
      {error ? (
        <p className="fail">
          {error}
          <button className="btn" type="button" onClick={() => send(last.current)}>
            Retry
          </button>
        </p>
      ) : null}
      {reply ? <p className="reply">{reply}</p> : null}
      {outfits.length ? (
        <div className="grid">
          {outfits.map((look) => (
            <LookCard
              key={look.image || look.n}
              look={look}
              query={`${piece?.title || reply}`}
              gender={gender}
              occasion={occasion}
              pinned={pinnedKeys?.has(lookKey(look))}
              onSaved={onSaved}
              onTryOn={onTryOn}
              onOpen={(opened) => onOpen?.(opened, outfits)}
            />
          ))}
        </div>
      ) : hits.length ? (
        <div className="thumbs">
          {hits.map((m) => (
            <img key={m.id} src={m.image} alt={m.caption} />
          ))}
        </div>
      ) : null}
    </section>
  );
}
