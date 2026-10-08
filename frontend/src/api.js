async function req(url, opts = {}, timeoutMs = 90000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { credentials: "include", signal: ctrl.signal, ...opts });
    let data = {};
    try {
      data = await res.json();
    } catch {
      data = {};
    }
    if (!res.ok) {
      const msg = data.detail || data.message || res.statusText || "Request failed";
      const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      if (res.status === 401) err.code = 401;
      if (res.status === 503) err.code = 503;
      throw err;
    }
    return data;
  } catch (e) {
    if (e.name === "AbortError") throw new Error("That took too long. Try again.");
    throw e;
  } finally {
    clearTimeout(t);
  }
}

export function getMe() {
  return req("/api/auth/me", {}, 15000);
}

export function getReady() {
  return req("/api/ready", {}, 10000);
}

export async function waitReady(onTick) {
  for (let i = 0; i < 80; i++) {
    const state = await getReady();
    onTick?.(state);
    if (state.error) throw new Error(state.error);
    if (state.catalog) return state;
    await new Promise((ok) => setTimeout(ok, 1500));
  }
  throw new Error("Catalog is taking too long. Refresh the page.");
}

export function login(email, password) {
  return req("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  }, 20000);
}

export function register(name, email, password) {
  return req("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
  }, 20000);
}

export function sendOtp(email, purpose = "login") {
  return req("/api/auth/send-otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, purpose }),
  }, 15000);
}

export function otpLogin(email, code, name = "") {
  return req("/api/auth/otp-login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code, name }),
  }, 20000);
}

export function resetPassword(email, code, password) {
  return req("/api/auth/reset-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code, password }),
  }, 20000);
}

export function checkEmail(email) {
  return req(`/api/auth/check-email?email=${encodeURIComponent(email)}`, {}, 10000);
}

export function logout() {
  return req("/api/auth/logout", { method: "POST" }, 10000);
}

export function getMeta() {
  return req("/api/meta");
}

export function chat(question, gender, occasion, history) {
  return req("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, gender, occasion, history }),
  });
}

export async function matchUpload(file, gender, occasion) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("gender", gender);
  fd.append("occasion", occasion);
  return req("/api/match", { method: "POST", body: fd });
}

export function createTryOn(pieces) {
  return req("/api/tryon", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tryon: pieces }),
  });
}

export function getTryOn(token) {
  return req(`/api/tryon/${token}`);
}

export function warmTryOn(pieces) {
  if (!pieces || !pieces.length) return;
  req("/api/tryon/warm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tryon: pieces }),
  }).catch(() => {});
}
