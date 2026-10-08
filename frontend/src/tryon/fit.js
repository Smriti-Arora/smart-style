const VISION = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs";
const WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm";
const MODEL =
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task";

export async function loadPose() {
  const { PoseLandmarker, FilesetResolver } = await import(/* @vite-ignore */ VISION);
  const fileset = await FilesetResolver.forVisionTasks(WASM);
  const opts = (delegate) => ({
    baseOptions: { modelAssetPath: MODEL, delegate },
    runningMode: "VIDEO",
    numPoses: 1,
  });
  try {
    return await PoseLandmarker.createFromOptions(fileset, opts("GPU"));
  } catch {
    return await PoseLandmarker.createFromOptions(fileset, opts("CPU"));
  }
}

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const mid = (a, b) => ({
  x: (a.x + b.x) / 2,
  y: (a.y + b.y) / 2,
  z: ((a.z || 0) + (b.z || 0)) / 2,
});
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

function points(lm, W, H, mirror) {
  const P = (i) => ({
    x: (mirror ? 1 - lm[i].x : lm[i].x) * W,
    y: lm[i].y * H,
    z: mirror ? -(lm[i].z || 0) : lm[i].z || 0,
    v: lm[i].visibility ?? 1,
  });
  return {
    sl: P(11),
    sr: P(12),
    hl: P(23),
    hr: P(24),
    kl: P(25),
    kr: P(26),
    al: P(27),
    ar: P(28),
    nose: P(0),
  };
}

function frame(B) {
  const sm = mid(B.sl, B.sr);
  const hips = Math.min(B.hl.v, B.hr.v) > 0.35;
  const ankles = Math.min(B.al.v, B.ar.v) > 0.35;
  const hm = hips ? mid(B.hl, B.hr) : { x: sm.x, y: sm.y + dist(B.sl, B.sr) * 1.8, z: sm.z };
  const am = ankles ? mid(B.al, B.ar) : { x: hm.x, y: hm.y + dist(sm, hm) * 1.55, z: hm.z };
  const km = Math.min(B.kl.v, B.kr.v) > 0.3 ? mid(B.kl, B.kr) : { x: hm.x, y: (hm.y + am.y) / 2, z: hm.z };
  const shoulderW = Math.max(dist(B.sl, B.sr), hips ? dist(B.hl, B.hr) * 0.95 : 0, 40);
  const hipW = Math.max(hips ? dist(B.hl, B.hr) : 0, shoulderW * 0.92);
  const downx = am.x - sm.x;
  const downy = am.y - sm.y;
  const dlen = Math.hypot(downx, downy) || 1;
  const neck =
    B.nose.v > 0.35
      ? { x: B.nose.x * 0.28 + sm.x * 0.72, y: B.nose.y * 0.28 + sm.y * 0.72 }
      : { x: sm.x - (downx / dlen) * shoulderW * 0.22, y: sm.y - (downy / dlen) * shoulderW * 0.22 };
  return { sm, hm, am, km, neck, shoulderW, hipW, hips, ankles };
}

function clipBody(ctx, B, F, kind) {
  const pad = F.shoulderW * 0.18;
  ctx.beginPath();
  ctx.moveTo(F.neck.x, F.neck.y);
  ctx.lineTo(B.sl.x - pad, B.sl.y);
  if (kind === "top") {
    ctx.lineTo(B.hl.x - pad * 0.7, F.hm.y + F.hipW * 0.15);
    ctx.lineTo(B.hr.x + pad * 0.7, F.hm.y + F.hipW * 0.15);
  } else {
    ctx.lineTo(B.hl.x - pad, F.hm.y);
    ctx.lineTo(B.al.x - pad * 0.4, F.am.y);
    ctx.lineTo(B.ar.x + pad * 0.4, F.am.y);
    ctx.lineTo(B.hr.x + pad, F.hm.y);
  }
  ctx.lineTo(B.sr.x + pad, B.sr.y);
  ctx.closePath();
  ctx.clip();
}

function drawWorn(ctx, g, B, F) {
  if (!g.on || !g.img?.complete || !g.img.naturalWidth) return;
  let ax, ay, ang, boxW, boxH;
  if (g.kind === "bottom") {
    if (!F.hips) return;
    ax = F.hm.x;
    ay = F.hm.y;
    ang = Math.atan2(B.hr.y - B.hl.y, B.hr.x - B.hl.x);
    boxW = F.hipW * 1.35;
    boxH = F.ankles ? F.am.y - F.hm.y : F.hipW * 2.1;
  } else if (g.kind === "top") {
    ax = F.sm.x;
    ay = F.neck.y;
    ang = Math.atan2(B.sr.y - B.sl.y, B.sr.x - B.sl.x);
    boxW = F.shoulderW * 1.55;
    boxH = (F.hm.y - F.neck.y) * 1.15;
  } else if (g.kind === "long") {
    ax = F.sm.x;
    ay = F.neck.y;
    ang = Math.atan2(B.sr.y - B.sl.y, B.sr.x - B.sl.x);
    boxW = F.shoulderW * 1.55;
    boxH = (F.km.y - F.neck.y) * 1.02;
  } else {
    ax = F.sm.x;
    ay = F.neck.y;
    ang = Math.atan2(B.sr.y - B.sl.y, B.sr.x - B.sl.x);
    boxW = Math.max(F.shoulderW * 1.7, F.hipW * 1.55);
    boxH = (F.am.y - F.neck.y) * 1.02;
  }
  ctx.save();
  clipBody(ctx, B, F, g.kind);
  ctx.translate(ax, ay);
  ctx.rotate(ang);
  ctx.globalAlpha = 0.94;
  ctx.drawImage(g.img, -boxW / 2, 0, boxW, boxH);
  ctx.restore();
}

export function drawTryOn(ctx, src, landmarks, garments, mirror) {
  const W = src.videoWidth || src.naturalWidth || src.width;
  const H = src.videoHeight || src.naturalHeight || src.height;
  if (!W || !H) return { ok: false, reason: "no-frame" };
  if (ctx.canvas.width !== W || ctx.canvas.height !== H) {
    ctx.canvas.width = W;
    ctx.canvas.height = H;
  }
  ctx.clearRect(0, 0, W, H);
  ctx.save();
  if (mirror) {
    ctx.translate(W, 0);
    ctx.scale(-1, 1);
  }
  ctx.drawImage(src, 0, 0, W, H);
  ctx.restore();

  const lm = landmarks && landmarks[0];
  if (!lm) return { ok: false, reason: "no-body" };
  if (Math.min(lm[11].visibility ?? 1, lm[12].visibility ?? 1) < 0.45) {
    return { ok: false, reason: "shoulders" };
  }
  const B = points(lm, W, H, mirror);
  const F = frame(B);
  const bodyH = Math.max(24, F.am.y - F.neck.y);
  const span = Math.abs(B.sl.x - B.sr.x);
  const dz = Math.abs((B.sl.z || 0) - (B.sr.z || 0));
  if (bodyH / H < 0.32) return { ok: false, reason: "far" };
  if (span / W < 0.1 || (dz > 0.42 && span / W < 0.16)) return { ok: false, reason: "side" };
  if (!F.hips && garments.some((g) => g.on && (g.kind === "bottom" || g.kind === "full"))) {
    return { ok: false, reason: "hips" };
  }
  for (const kind of ["full", "long", "bottom", "top"]) {
    for (const g of garments) {
      if (g.kind === kind) drawWorn(ctx, g, B, F);
    }
  }
  return { ok: true };
}

export function captureFrame(video) {
  if (!video.videoWidth) return "";
  const c = document.createElement("canvas");
  c.width = video.videoWidth;
  c.height = video.videoHeight;
  const x = c.getContext("2d");
  x.save();
  x.translate(c.width, 0);
  x.scale(-1, 1);
  x.drawImage(video, 0, 0);
  x.restore();
  return c.toDataURL("image/jpeg", 0.92);
}
