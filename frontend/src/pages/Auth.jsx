import { useEffect, useState } from "react";
import { checkEmail, getMeta, login, otpLogin, register, resetPassword, sendOtp, waitReady } from "../api.js";
import "./Auth.css";

function friendly(msg) {
  const m = (msg || "").toLowerCase();
  if (m.includes("already")) return "That email is already registered. Sign in or use OTP login instead.";
  if (m.includes("wrong") || m.includes("invalid")) return "Invalid credentials or verification code.";
  if (m.includes("valid email")) return "Please enter a valid email address.";
  if (m.includes("6 characters")) return "Password must be at least 6 characters long.";
  if (m.includes("name must")) return "Please enter your name.";
  return msg || "Operation failed. Please check your details.";
}

export default function Auth({ onAuth, start = "login" }) {
  const [mode, setMode] = useState(start); // "login" | "register" | "reset"
  const [loginMethod, setLoginMethod] = useState("password"); // "password" | "otp"

  const [name, setName] = useState("");
  const [email, setEmail] = useState(() => {
    try {
      return localStorage.getItem("ss_saved_email") || "";
    } catch {
      return "";
    }
  });
  const [password, setPassword] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(() => {
    try {
      return !!localStorage.getItem("ss_saved_email");
    } catch {
      return true;
    }
  });

  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [successCode, setSuccessCode] = useState("");
  const [emailExists, setEmailExists] = useState(false);
  const [busy, setBusy] = useState(false);
  const [otpSent, setOtpSent] = useState(false);
  const [timer, setTimer] = useState(0);

  const [shots, setShots] = useState([]);
  const [currentIdx, setCurrentIdx] = useState(0);

  // Load catalog showcase
  useEffect(() => {
    let active = true;
    waitReady()
      .then(() => getMeta())
      .then((meta) => {
        if (!active) return;
        const pool = meta.shots?.length ? meta.shots : meta.featured || [];
        setShots(pool);
        pool.forEach((s) => {
          if (s.image) {
            const im = new Image();
            im.src = s.image;
          }
        });
      })
      .catch(() => {});

    return () => {
      active = false;
    };
  }, []);

  // Smooth continuous photo crossfade interval
  useEffect(() => {
    if (shots.length < 2) return;
    const interval = setInterval(() => {
      setCurrentIdx((prev) => (prev + 1) % shots.length);
    }, 4000);
    return () => clearInterval(interval);
  }, [shots]);

  // Resend OTP countdown timer
  useEffect(() => {
    if (timer <= 0) return;
    const t = setInterval(() => setTimer((n) => n - 1), 1000);
    return () => clearInterval(t);
  }, [timer]);

  // Check email duplicacy during registration
  async function handleEmailBlur() {
    if (mode !== "register" || !email.trim() || !email.includes("@")) {
      setEmailExists(false);
      return;
    }
    try {
      const res = await checkEmail(email.trim());
      setEmailExists(!!res.exists);
    } catch {
      setEmailExists(false);
    }
  }

  // Request OTP for Login or Password Reset
  async function handleSendOtp(purpose = "login") {
    if (!email.trim() || !email.includes("@")) {
      setError("Please enter a valid email address first.");
      return;
    }
    setError("");
    setInfo("");
    setBusy(true);
    try {
      const res = await sendOtp(email.trim(), purpose);
      setOtpSent(true);
      setTimer(45);
      if (res.code) {
        setOtpCode(res.code); // Auto-fill code for instant developer & tester convenience
        setSuccessCode(`Verification code: ${res.code}`);
      } else {
        setInfo(`Verification code sent to ${email}`);
      }
    } catch (err) {
      setError(friendly(err.message));
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setInfo("");

    if (!email.trim()) {
      setError("Please enter your email.");
      return;
    }

    setBusy(true);
    try {
      let user = null;

      if (mode === "register") {
        if (name.trim().length < 2) {
          throw new Error("Please enter your name (at least 2 characters).");
        }
        if (password.length < 6) {
          throw new Error("Password must be at least 6 characters.");
        }
        user = await register(name.trim(), email.trim(), password);
      } else if (mode === "login") {
        if (loginMethod === "otp") {
          if (!otpCode.trim()) {
            throw new Error("Please enter the 6-digit verification code.");
          }
          user = await otpLogin(email.trim(), otpCode.trim(), name);
        } else {
          if (!password) {
            throw new Error("Please enter your password.");
          }
          user = await login(email.trim(), password);
        }
      } else if (mode === "reset") {
        if (!otpCode.trim()) {
          throw new Error("Please enter the verification code.");
        }
        if (password.length < 6) {
          throw new Error("New password must be at least 6 characters.");
        }
        user = await resetPassword(email.trim(), otpCode.trim(), password);
      }

      // Remember email
      try {
        if (rememberMe && email) {
          localStorage.setItem("ss_saved_email", email.trim().toLowerCase());
        } else {
          localStorage.removeItem("ss_saved_email");
        }
      } catch {
        /* storage unavailable */
      }

      if (user) {
        onAuth(user);
      }
    } catch (err) {
      setError(friendly(err.message));
    } finally {
      setBusy(false);
    }
  }

  const activeShot = shots[currentIdx] || null;

  return (
    <div className="auth-page-root">
      <div className="auth-content-wrapper">
        {/* Center Heading Section */}
        <div className="auth-heading-section">
          <div className="auth-sparkle-pill">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2L14.4 8.6L21 11L14.4 13.4L12 20L9.6 13.4L3 11L9.6 8.6L12 2Z" />
            </svg>
            Personalized Fashion Intelligence
          </div>
          <h1>
            Step into your <em>perfect look</em>.
          </h1>
          <p>
            Experience AI-curated outfits for festive celebrations, weddings, and everyday elegance. Try any look on your photo in seconds.
          </p>
        </div>

        <div className="auth-master-card">
          {/* Left Side: Dynamic Crossfade Showcase */}
          <div className="auth-visual-side">
            <div className="auth-image-stage">
              {shots.map((shot, idx) => (
                <img
                  key={shot.image || idx}
                  src={shot.image}
                  alt={shot.caption || shot.label || "Smart Style Look"}
                  className={`auth-crossfade-img ${idx === currentIdx ? "active" : ""}`}
                />
              ))}
            </div>

          <div className="auth-visual-overlay" />

          {/* Top Info */}
          <div className="auth-visual-top">
            <span className="auth-visual-pill">
              <span className="dot" />
              AI Haute Couture
            </span>
            {shots.length > 0 && (
              <span className="auth-visual-counter">
                {String(currentIdx + 1).padStart(2, "0")} / {String(shots.length).padStart(2, "0")}
              </span>
            )}
          </div>

          {/* Bottom Info */}
          <div className="auth-visual-bottom">
            {activeShot && (
              <>
                <span className="auth-visual-tag">{activeShot.label || "Exclusive Collection"}</span>
                <h3 className="auth-visual-title">
                  {activeShot.caption || activeShot.label || "Curated Occasion Styling"}
                </h3>
              </>
            )}

            {shots.length > 1 && (
              <div className="auth-visual-indicators">
                {shots.map((_, idx) => (
                  <div
                    key={idx}
                    className={`auth-indicator-bar ${idx === currentIdx ? "active" : ""}`}
                    onClick={() => setCurrentIdx(idx)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Side: Form Area */}
        <div className="auth-form-side">
          <div className="auth-form-inner">
            <div className="auth-brand-header">
              <span className="auth-logo-text">Smart Style</span>
              <h2>
                {mode === "reset"
                  ? "Reset Password"
                  : mode === "register"
                  ? "Create an account"
                  : "Welcome back"}
              </h2>
              <p>
                {mode === "reset"
                  ? "Enter your email, verify OTP code, and choose a new password."
                  : mode === "register"
                  ? "Save bespoke looks, manage your digital closet, and try on styles."
                  : "Sign in to access your curated looks, wardrobe, and try-on history."}
              </p>
            </div>

            {/* Mode Tabs (Sign In / Create Account) */}
            {mode !== "reset" ? (
              <div className="auth-tab-switch">
                <button
                  type="button"
                  className={`auth-tab-item ${mode === "login" ? "active" : ""}`}
                  onClick={() => {
                    setMode("login");
                    setError("");
                    setInfo("");
                    setEmailExists(false);
                  }}
                >
                  Sign In
                </button>
                <button
                  type="button"
                  className={`auth-tab-item ${mode === "register" ? "active" : ""}`}
                  onClick={() => {
                    setMode("register");
                    setError("");
                    setInfo("");
                  }}
                >
                  Create Account
                </button>
              </div>
            ) : (
              <div className="auth-tab-switch">
                <button
                  type="button"
                  className="auth-tab-item"
                  onClick={() => {
                    setMode("login");
                    setError("");
                    setInfo("");
                  }}
                >
                  ← Back to Sign In
                </button>
              </div>
            )}

            {/* Sign In Method Toggle: Password vs OTP Login */}
            {mode === "login" && (
              <div className="auth-method-toggle">
                <button
                  type="button"
                  className={`auth-method-btn ${loginMethod === "password" ? "active" : ""}`}
                  onClick={() => {
                    setLoginMethod("password");
                    setError("");
                  }}
                >
                  Password Login
                </button>
                <button
                  type="button"
                  className={`auth-method-btn ${loginMethod === "otp" ? "active" : ""}`}
                  onClick={() => {
                    setLoginMethod("otp");
                    setError("");
                  }}
                >
                  Sign in with OTP
                </button>
              </div>
            )}

            {/* Form */}
            <form className="auth-form-root" onSubmit={handleSubmit}>
              {/* Name field for Register or OTP auto-profile */}
              {mode === "register" && (
                <div className="auth-field-group">
                  <label htmlFor="user-name">Full Name</label>
                  <div className="auth-input-box">
                    <input
                      id="user-name"
                      type="text"
                      placeholder="e.g. Shiva"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      autoComplete="name"
                      required
                    />
                  </div>
                </div>
              )}

              {/* Email field */}
              <div className="auth-field-group">
                <label htmlFor="user-email">Email Address</label>
                <div className="auth-input-box">
                  <input
                    id="user-email"
                    type="email"
                    placeholder="name@example.com"
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      if (emailExists) setEmailExists(false);
                    }}
                    onBlur={handleEmailBlur}
                    autoComplete="email"
                    required
                  />
                  {/* Send OTP button directly in input box for OTP flows */}
                  {(loginMethod === "otp" || mode === "reset") && (
                    <button
                      type="button"
                      className="auth-input-action-btn"
                      onClick={() => handleSendOtp(mode === "reset" ? "reset" : "login")}
                      disabled={busy || timer > 0}
                    >
                      {timer > 0 ? `${timer}s` : otpSent ? "Resend" : "Send OTP"}
                    </button>
                  )}
                </div>
              </div>

              {/* Duplicacy Notice (if email already registered) */}
              {emailExists && mode === "register" && (
                <div className="auth-info-banner">
                  <span>This email is already registered.</span>
                  <button
                    type="button"
                    className="auth-info-banner-action"
                    onClick={() => {
                      setMode("login");
                      setEmailExists(false);
                    }}
                  >
                    Sign in instead →
                  </button>
                </div>
              )}

              {/* OTP Code Input (When in OTP mode or Reset mode) */}
              {(loginMethod === "otp" || mode === "reset") && (
                <div className="auth-field-group">
                  <label htmlFor="user-otp">6-Digit Verification Code</label>
                  <div className="auth-input-box">
                    <input
                      id="user-otp"
                      type="text"
                      placeholder="e.g. 842109"
                      maxLength={6}
                      value={otpCode}
                      onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ""))}
                      required
                    />
                  </div>
                </div>
              )}

              {/* Password Field (when using Password Login, Registration, or Setting New Password in Reset) */}
              {(loginMethod === "password" || mode === "register" || mode === "reset") && (
                <div className="auth-field-group">
                  <label htmlFor="user-password">
                    {mode === "reset" ? "New Password" : "Password"}
                  </label>
                  <div className="auth-input-box">
                    <input
                      id="user-password"
                      type={showPassword ? "text" : "password"}
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      autoComplete={mode === "register" || mode === "reset" ? "new-password" : "current-password"}
                      minLength={6}
                      required
                    />
                    <button
                      type="button"
                      className="auth-eye-toggle"
                      onClick={() => setShowPassword(!showPassword)}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                    >
                      {showPassword ? (
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                          <line x1="1" y1="1" x2="23" y2="23" />
                        </svg>
                      ) : (
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                          <circle cx="12" cy="12" r="3" />
                        </svg>
                      )}
                    </button>
                  </div>
                </div>
              )}

              {/* Remember Me & Forgot Password Links */}
              {mode === "login" && (
                <div className="auth-options-row">
                  <label className="auth-remember-check">
                    <input
                      type="checkbox"
                      checked={rememberMe}
                      onChange={(e) => setRememberMe(e.target.checked)}
                    />
                    <span>Remember me</span>
                  </label>
                  <button
                    type="button"
                    className="auth-inline-link"
                    onClick={() => {
                      setMode("reset");
                      setError("");
                      setInfo("");
                      setOtpSent(false);
                    }}
                  >
                    Forgot password?
                  </button>
                </div>
              )}

              {/* Success / OTP helper banner */}
              {successCode && (
                <div className="auth-success-banner">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                    <polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                  <span>{successCode}</span>
                </div>
              )}

              {info && <div className="auth-info-banner"><span>{info}</span></div>}

              {/* Error banner */}
              {error && (
                <div className="auth-error-banner" role="alert">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                  <span>{error}</span>
                </div>
              )}

              {/* Primary Submit Button */}
              <button className="auth-btn-primary" type="submit" disabled={busy}>
                {busy ? (
                  <div className="auth-spinner-ring" />
                ) : mode === "reset" ? (
                  "Reset Password & Sign In"
                ) : mode === "register" ? (
                  "Create Account"
                ) : loginMethod === "otp" ? (
                  "Verify OTP & Sign In"
                ) : (
                  "Sign In"
                )}
              </button>
            </form>
          </div>

          <div className="auth-form-footer">
            <span>Encrypted Session • Smart Style AI Studio</span>
          </div>
        </div>
      </div>
    </div>
  </div>
);
}
