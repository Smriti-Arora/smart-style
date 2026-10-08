import { useEffect, useRef, useState } from "react";
import { getTryOn } from "../api.js";
import { pinLook } from "../history.js";
import { captureFrame, drawTryOn, loadPose } from "../tryon/fit.js";

function scoreCam(label) {
  const s = (label || "").toLowerCase();
  if (/infrared|\bir\b|virtual|obs|droidcam|iriun/.test(s)) return -20;
  if (/integrated|webcam|hd|usb|logitech|laptop/.test(s)) return 10;
  return 0;
}

function snapshotJpeg(canvas) {
  const max = 720;
  const scale = Math.min(1, max / Math.max(canvas.width, canvas.height));
  const out = document.createElement("canvas");
  out.width = Math.round(canvas.width * scale);
  out.height = Math.round(canvas.height * scale);
  out.getContext("2d").drawImage(canvas, 0, 0, out.width, out.height);
  return out.toDataURL("image/jpeg", 0.72);
}

export default function TryOn({ token, onClose, onSaved, query, gender, occasion, embedded }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const poseRef = useRef(null);
  const garmentsRef = useRef([]);
  const stillRef = useRef(null);
  const modeRef = useRef("idle");
  const runRef = useRef(false);
  const lastTime = useRef(-1);

  const [status, setStatus] = useState("Loading garments…");
  const [ready, setReady] = useState(false);
  const [cams, setCams] = useState([]);
  const [camId, setCamId] = useState("");
  const [names, setNames] = useState([]);
  const [error, setError] = useState("");
  const [live, setLive] = useState(false);

  useEffect(() => {
    let gone = false;
    (async () => {
      try {
        const data = await getTryOn(token);
        if (gone) return;
        const loaded = await Promise.all(
          (data.garments || []).map(
            (g) =>
              new Promise((ok) => {
                const img = new Image();
                img.onload = () => ok({ ...g, on: true, img });
                img.onerror = () => ok({ ...g, on: true, img: null });
                img.src = g.png;
              })
          )
        );
        garmentsRef.current = loaded.filter((g) => g.img);
        setNames(garmentsRef.current.map((g) => ({ name: g.name, on: true })));
        setStatus("Loading body tracking…");
        poseRef.current = await loadPose();
        if (gone) return;
        setReady(true);
        setStatus("Start camera, then Take photo. Or upload a full-length photo.");
      } catch (e) {
        setError(e.message || "Try-on expired. Go back and tap Try on again.");
      }
    })();
    return () => {
      gone = true;
      stopCam();
    };
  }, [token]);

  function paint(src, landmarks, mirror) {
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    const r = drawTryOn(ctx, src, landmarks, garmentsRef.current, mirror);
    if (r.reason === "no-body") setStatus("No body found. Face the camera. Shoulders and hips should be in frame.");
    else if (r.reason === "shoulders") setStatus("Shoulders not visible. Step back so both shoulders show.");
    else if (r.reason === "far") setStatus("You are too far. Step closer so your body fills the frame.");
    else if (r.reason === "side") setStatus("Turn to face the camera. Side photos do not fit well.");
    else if (r.reason === "hips") setStatus("Hips not visible. Step back so the full outfit can sit on you.");
    else if (r.ok) setStatus("Clothes fitted on you");
  }

  function loop() {
    if (!runRef.current) return;
    const video = videoRef.current;
    const pose = poseRef.current;
    if (pose && video && video.readyState >= 2 && video.currentTime !== lastTime.current) {
      lastTime.current = video.currentTime;
      const res = pose.detectForVideo(video, performance.now());
      paint(video, res.landmarks, true);
    }
    requestAnimationFrame(loop);
  }

  function stopCam() {
    runRef.current = false;
    setLive(false);
    const v = videoRef.current;
    if (v?.srcObject) {
      v.srcObject.getTracks().forEach((t) => t.stop());
      v.srcObject = null;
    }
  }

  async function listCams() {
    const all = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
    all.sort((a, b) => scoreCam(b.label) - scoreCam(a.label));
    setCams(all);
    return all;
  }

  async function startCam() {
    try {
      if (!poseRef.current) {
        setStatus("Body tracking is still loading…");
        return;
      }
      stopCam();
      stillRef.current = null;
      modeRef.current = "camera";
      await poseRef.current.setOptions({ runningMode: "VIDEO" });
      const devices = await listCams().catch(() => []);
      const picked = camId || devices[0]?.deviceId;
      const tries = [];
      if (picked) tries.push({ video: { deviceId: { exact: picked } }, audio: false });
      tries.push({ video: { facingMode: "user" }, audio: false });
      tries.push({ video: true, audio: false });
      let stream = null;
      let last = null;
      for (const spec of tries) {
        try {
          stream = await navigator.mediaDevices.getUserMedia(spec);
          break;
        } catch (e) {
          last = e;
        }
      }
      if (!stream) throw last || new Error("no camera");
      const video = videoRef.current;
      video.srcObject = stream;
      video.muted = true;
      await video.play().catch(() => {});
      if (video.readyState < 2) {
        await new Promise((ok, bad) => {
          const t = setTimeout(() => bad(new Error("camera opened but no frames")), 8000);
          video.onloadeddata = () => {
            clearTimeout(t);
            ok();
          };
        });
      }
      await listCams().catch(() => {});
      if (!video.videoWidth) throw new Error("camera opened but no frames");
      runRef.current = true;
      setLive(true);
      setStatus("Camera on. Stand in frame, then tap Take photo.");
      loop();
    } catch (e) {
      const busy = e.name === "NotReadableError" || /start video source|in use|busy/i.test(e.message || "");
      const denied = e.name === "NotAllowedError" || e.name === "SecurityError";
      setStatus(
        denied
          ? "Camera blocked. Allow camera in the address bar, or Take photo / upload."
          : busy
            ? "Camera is busy. Close Zoom/Teams and other tabs, then Start camera again."
            : `Camera not available: ${e.message || e.name}. Use Take photo or upload.`
      );
    }
  }

  async function takePhoto() {
    const video = videoRef.current;
    if (!video?.videoWidth) {
      await startCam();
      setStatus("Camera started. Tap Take photo again.");
      return;
    }
    const url = captureFrame(video);
    if (!url) return;
    stopCam();
    const img = new Image();
    img.onload = async () => {
      stillRef.current = img;
      modeRef.current = "photo";
      await poseRef.current.setOptions({ runningMode: "IMAGE" });
      const res = poseRef.current.detect(img);
      paint(img, res.landmarks, false);
    };
    img.src = url;
  }

  async function useFile(file) {
    if (!file) return;
    if (!poseRef.current) {
      setStatus("Body tracking is still loading…");
      return;
    }
    stopCam();
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = async () => {
      stillRef.current = img;
      modeRef.current = "photo";
      await poseRef.current.setOptions({ runningMode: "IMAGE" });
      const res = poseRef.current.detect(img);
      paint(img, res.landmarks, false);
    };
    img.src = url;
  }

  function toggle(name) {
    garmentsRef.current = garmentsRef.current.map((g) => (g.name === name ? { ...g, on: !g.on } : g));
    setNames(garmentsRef.current.map((g) => ({ name: g.name, on: g.on })));
    if (modeRef.current === "photo" && stillRef.current && poseRef.current) {
      const res = poseRef.current.detect(stillRef.current);
      paint(stillRef.current, res.landmarks, false);
    }
  }

  function saveShot() {
    const c = canvasRef.current;
    if (!c || !c.width) return;
    const file = c.toDataURL("image/png");
    const a = document.createElement("a");
    a.href = file;
    a.download = "tryon.png";
    a.click();
    if (onSaved) {
      try {
        const next = pinLook(
          {
            key: `tryon-${Date.now()}`,
            n: "tryon",
            image: snapshotJpeg(c),
            query: query || "Try-on snapshot",
            items: names.filter((g) => g.on).map((g) => ({ role: "Worn", name: g.name, colour: "", hex: "#CFCFCF" })),
            source: "tryon",
          },
          { query: query || "Try-on snapshot", gender, occasion, source: "tryon" }
        );
        onSaved(next);
        setStatus("Saved to History");
      } catch {
        setStatus("Saved the file. History is full — remove an old look.");
      }
    }
  }

  function close() {
    stopCam();
    if (onClose) onClose();
    else window.location.href = "/";
  }

  if (error) {
    return (
      <div className={"tryon" + (embedded ? " overlay" : "")}>
        <header className="nav">
          <a className="logo" href="/" onClick={(e) => { e.preventDefault(); close(); }}>Smart Style</a>
          <button className="btn ghost" type="button" onClick={close}>Close</button>
        </header>
        <p className="wrap hint">{error}</p>
      </div>
    );
  }

  return (
    <div className={"tryon" + (embedded ? " overlay" : "")}>
      <header className="nav">
        <a className="logo" href="/" onClick={(e) => { e.preventDefault(); close(); }}>Smart Style</a>
        <strong>Try on</strong>
        <button className="btn ghost" type="button" onClick={close}>Close</button>
      </header>
      <div className="bar">
        <button className="btn" type="button" onClick={startCam} disabled={!ready}>
          {live ? "Restart camera" : "Start camera"}
        </button>
        <select value={camId} onChange={(e) => setCamId(e.target.value)}>
          {cams.map((c) => (
            <option key={c.deviceId} value={c.deviceId}>
              {c.label || "Camera"}
            </option>
          ))}
        </select>
        <button className="btn" type="button" onClick={takePhoto} disabled={!ready}>
          Take photo
        </button>
        <label className="btn ghost">
          Upload photo
          <input type="file" accept="image/*" capture="user" hidden onChange={(e) => useFile(e.target.files[0])} />
        </label>
        <button className="btn ghost" type="button" onClick={saveShot}>
          {onSaved ? "Save to History" : "Save"}
        </button>
        <span className="status">{status}</span>
      </div>
      <div className="chips">
        {names.map((g) => (
          <button key={g.name} type="button" className={g.on ? "on" : ""} onClick={() => toggle(g.name)}>
            {g.name}
          </button>
        ))}
      </div>
      <div className="stage-wrap">
        <video ref={videoRef} playsInline muted autoPlay className="offscreen" />
        <canvas ref={canvasRef} className="stage" />
      </div>
      <p className="hint wrap">Face the camera. Stand so shoulders and hips show, then Take photo. Side or far shots will not fit. Save to History keeps the snapshot.</p>
    </div>
  );
}
