import { useEffect, useRef, useState } from "react";
import { chat, createTryOn, getMe, getMeta, logout, waitReady, warmTryOn } from "./api.js";
import { addRecents, loadHistory, lookKey, setHistoryUser } from "./history.js";
import Closet from "./components/Closet.jsx";
import History from "./components/History.jsx";
import LookDetail from "./components/LookDetail.jsx";
import Results from "./components/Results.jsx";
import Skeletons from "./components/Skeletons.jsx";
import Auth from "./pages/Auth.jsx";
import TryOn from "./pages/TryOn.jsx";

function pageFromPath() {
  const p = window.location.pathname;
  if (p.startsWith("/tryon/")) return "";
  if (p === "/closet") return "closet";
  if (p === "/history") return "history";
  return "looks";
}

const tryonToken = window.location.pathname.startsWith("/tryon/")
  ? window.location.pathname.split("/")[2]
  : "";

export default function App() {
  if (tryonToken) return <TryOn token={tryonToken} onSaved={() => {}} />;
  const [gate, setGate] = useState({ loading: true, required: true, user: null });
  const [meta, setMeta] = useState(null);
  const [page, setPage] = useState(pageFromPath);
  const [gender, setGender] = useState("Any");
  const [occasion, setOccasion] = useState("Any");
  const [q, setQ] = useState("");
  const [chatHistory, setChatHistory] = useState([]);
  const [session, setSession] = useState(null);
  const [saved, setSaved] = useState([]);
  const [fitting, setFitting] = useState(null);
  const [detail, setDetail] = useState(null);
  const lastAsk = useRef(null);
  const catalogOk = meta && !meta.error;

  useEffect(() => {
    getMe()
      .then((data) => {
        const user = data.user || null;
        setHistoryUser(user?.id);
        setSaved(loadHistory());
        setGate({ loading: false, required: !!data.required, user });
      })
      .catch(() => setGate({ loading: false, required: true, user: null }));
  }, []);

  function loadCatalog() {
    setMeta(null);
    waitReady()
      .then(() => getMeta())
      .then(setMeta)
      .catch((e) =>
        setMeta({
          genders: ["Any"],
          occasions: ["Any"],
          featured: [],
          suggestions: [],
          error: e.message || "Catalog failed to load.",
        })
      );
  }

  useEffect(() => {
    if (gate.loading || (gate.required && !gate.user)) return;
    loadCatalog();
  }, [gate.loading, gate.required, gate.user]);

  useEffect(() => {
    (meta?.featured || []).forEach((f) => warmTryOn(f.tryon));
  }, [meta]);

  useEffect(() => {
    const onPop = () => setPage(pageFromPath());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  function go(next) {
    setPage(next);
    const path = next === "looks" ? "/" : `/${next}`;
    if (window.location.pathname !== path) window.history.pushState({ page: next }, "", path);
  }

  async function ask(text, filters) {
    const question = (text || q).trim();
    if (!question) return;
    const g = filters?.gender ?? gender;
    const o = filters?.occasion ?? occasion;
    if (filters?.gender) setGender(filters.gender);
    if (filters?.occasion) setOccasion(filters.occasion);
    lastAsk.current = { question, filters };
    setQ("");
    go("looks");
    setSession({ query: question, waiting: true, failed: false, reply: "", outfits: [], images: [] });
    try {
      const data = await chat(question, g, o, chatHistory);
      setSession({
        query: question,
        waiting: false,
        failed: false,
        reply: data.reply || "",
        outfits: data.outfits || [],
        images: data.images || [],
      });
      setChatHistory((h) => [
        ...h,
        { role: "user", content: question },
        { role: "assistant", content: data.reply || "" },
      ]);
      (data.outfits || []).forEach((x) => warmTryOn(x.tryon));
      if (data.outfits?.length) {
        setSaved(addRecents(data.outfits, { query: question, gender: g, occasion: o, source: "looks" }));
      }
    } catch (e) {
      setSession({
        query: question,
        waiting: false,
        failed: true,
        reply: e.message || "Could not finish that. Try again.",
        outfits: [],
        images: [],
      });
    }
  }

  async function startTryOn(pieces, metaInfo = {}) {
    const data = await createTryOn(pieces);
    setFitting({
      token: data.token,
      query: metaInfo.query || "",
      gender: metaInfo.gender || gender,
      occasion: metaInfo.occasion || occasion,
    });
  }

  function openLook(look, extras) {
    const pool = extras || session?.outfits || meta?.featured || [];
    const similar = pool.filter((x) => (x.image || x.n) !== (look.image || look.n)).slice(0, 4);
    setDetail({
      look,
      similar,
      extras: pool,
      query: look.query || session?.query || look.prompt || look.label,
    });
  }

  function signedIn(user) {
    setHistoryUser(user.id);
    setSaved(loadHistory());
    setGate({ loading: false, required: gate.required, user });
    go("looks");
  }

  async function signOut() {
    await logout().catch(() => {});
    setHistoryUser(null);
    setSaved([]);
    setSession(null);
    setFitting(null);
    setDetail(null);
    setChatHistory([]);
    setGate({ loading: false, required: gate.required, user: null });
    go("looks");
  }

  const featured = meta?.featured || [];
  const pinnedKeys = new Set(saved.filter((x) => x.pinned).map((x) => x.key));
  const pinnedCount = pinnedKeys.size;

  if (gate.loading) {
    return (
      <div className="auth">
        <header className="nav">
          <span className="logo">Smart Style</span>
        </header>
        <p className="wrap hint">Connecting…</p>
      </div>
    );
  }
  if (gate.required && !gate.user) {
    const start = window.location.pathname === "/register" ? "register" : "login";
    return <Auth onAuth={signedIn} start={start} />;
  }

  return (
    <>
      <header className="nav">
        <a
          className="logo"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            go("looks");
          }}
        >
          Smart Style
        </a>
        <nav>
          <button className={page === "looks" ? "on" : ""} type="button" onClick={() => go("looks")}>
            Looks
          </button>
          <button className={page === "closet" ? "on" : ""} type="button" onClick={() => go("closet")}>
            Closet
          </button>
          <button className={page === "history" ? "on" : ""} type="button" onClick={() => go("history")}>
            History{pinnedCount ? ` (${pinnedCount})` : ""}
          </button>
        </nav>
        <div className="account">
          <span className={"status " + (meta?.llm ? "on" : catalogOk ? "off" : "")}>
            {!meta ? "Loading catalog…" : meta.error ? "Catalog failed" : meta.llm ? "Stylist live" : "Catalog only"}
          </span>
          {gate.user ? (
            <>
              <span className="who">{gate.user.name}</span>
              <button className="link" type="button" onClick={signOut}>
                Sign out
              </button>
            </>
          ) : null}
        </div>
      </header>

      <section className="bar">
        <label>
          Gender
          <select value={gender} onChange={(e) => setGender(e.target.value)}>
            {(meta?.genders || ["Any"]).map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        </label>
        <label>
          Occasion
          <select value={occasion} onChange={(e) => setOccasion(e.target.value)}>
            {(meta?.occasions || ["Any"]).map((o) => (
              <option key={o}>{o}</option>
            ))}
          </select>
        </label>
        <form
          className="ask"
          onSubmit={(e) => {
            e.preventDefault();
            ask(q);
          }}
        >
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={catalogOk ? "Lehenga, Karwa look, Diwali kurta…" : "Catalog loading…"}
            disabled={!catalogOk}
          />
          <button type="submit" disabled={!catalogOk}>
            Ask
          </button>
        </form>
      </section>

      <div className="chips">
        {(meta?.suggestions || []).map((s) => (
          <button key={s.prompt} type="button" disabled={!catalogOk} onClick={() => ask(s.prompt)}>
            {s.label.replace(" · ", " / ")}
          </button>
        ))}
      </div>

      {page === "looks" && !session ? (
        <section className="wrap">
          <h2>Looks</h2>
          {meta?.error ? (
            <p className="fail">
              {meta.error}
              <button className="btn" type="button" onClick={loadCatalog}>
                Retry
              </button>
            </p>
          ) : !meta ? (
            <>
              <p className="wait">Loading catalog… you can stay here, or sign out if you want.</p>
              <Skeletons n={4} className="edits" />
            </>
          ) : (
            <div className="edits">
              {featured.map((f) => (
                <figure key={f.label} className="tile">
                  <button type="button" className="look-pic" onClick={() => openLook(f, featured)}>
                    <img src={f.image} alt={f.caption} />
                  </button>
                  <figcaption>
                    <strong>{f.label}</strong>
                    <span>{f.caption}</span>
                  </figcaption>
                  <div className="acts">
                    <button className="btn" type="button" onClick={() => ask(f.prompt || `${f.label} look`)}>
                      Style
                    </button>
                    {f.tryon?.length ? (
                      <button
                        className="btn ghost"
                        type="button"
                        onClick={async (e) => {
                          const btn = e.currentTarget;
                          btn.disabled = true;
                          btn.textContent = "Opening…";
                          try {
                            await startTryOn(f.tryon, { query: f.label, gender, occasion });
                          } catch {
                            /* keep label */
                          } finally {
                            btn.disabled = false;
                            btn.textContent = "Try on";
                          }
                        }}
                      >
                        Try on
                      </button>
                    ) : null}
                  </div>
                </figure>
              ))}
            </div>
          )}
        </section>
      ) : null}

      {page === "looks" && session ? (
        <Results
          session={session}
          onClose={() => setSession(null)}
          onRetry={() => lastAsk.current && ask(lastAsk.current.question, lastAsk.current.filters)}
          onSaved={setSaved}
          onTryOn={startTryOn}
          onOpen={(look) => openLook(look, session.outfits)}
          gender={gender}
          occasion={occasion}
          pinnedKeys={pinnedKeys}
        />
      ) : null}

      {page === "closet" ? (
        <Closet
          gender={gender}
          occasion={occasion}
          onSaved={setSaved}
          pinnedKeys={pinnedKeys}
          onTryOn={startTryOn}
          onOpen={(look, extras) => openLook(look, extras)}
        />
      ) : null}
      {page === "history" ? (
        <History
          items={saved}
          onChange={setSaved}
          onRestyle={(look) => ask(look.query, { gender: look.gender, occasion: look.occasion })}
          onTryOn={startTryOn}
          onOpen={(look) => openLook(look, saved)}
        />
      ) : null}

      {detail ? (
        <LookDetail
          look={detail.look}
          similar={detail.similar}
          query={detail.query}
          gender={gender}
          occasion={occasion}
          pinned={pinnedKeys.has(lookKey(detail.look))}
          onClose={() => setDetail(null)}
          onSaved={setSaved}
          onTryOn={startTryOn}
          onRestyle={(look) => {
            setDetail(null);
            ask(look.query || look.prompt || detail.query, { gender: look.gender, occasion: look.occasion });
          }}
          onOpen={(look) => openLook(look, detail.extras)}
        />
      ) : null}

      {fitting ? (
        <TryOn
          token={fitting.token}
          query={fitting.query}
          gender={fitting.gender}
          occasion={fitting.occasion}
          embedded
          onClose={() => setFitting(null)}
          onSaved={setSaved}
        />
      ) : null}
    </>
  );
}
