"""Smart Style. Run: myenv\\Scripts\\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000"""
import os

os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import json
import secrets
import threading
import time

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import auth
from engine import Engine

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "frontend", "dist")

app = FastAPI(title="Smart Style")
_ASSETS = os.path.join(DIST, "assets")
if os.path.isdir(_ASSETS):
    app.mount("/assets", StaticFiles(directory=_ASSETS), name="assets")

_engine = None
_engine_error = None


def _boot_engine():
    global _engine, _engine_error
    try:
        print("Loading catalog and CLIP (first boot ~1 minute)...")
        _engine = Engine()
        print("Ready.")
    except Exception as exc:
        _engine_error = str(exc)
        print("Catalog failed:", exc)


def engine() -> Engine:
    if _engine_error:
        raise HTTPException(503, "Catalog failed to load. Restart the server.")
    if _engine is None:
        raise HTTPException(503, "Catalog is still loading")
    return _engine


def react_index():
    page = os.path.join(DIST, "index.html")
    if not os.path.isfile(page):
        raise HTTPException(503, "React build missing. From frontend/ run: npm install && npm run build")
    return FileResponse(page, headers={"Cache-Control": "no-store"})


class ChatIn(BaseModel):
    question: str
    gender: str = "Any"
    occasion: str = "Any"
    history: list = []


class TryOnIn(BaseModel):
    tryon: list


class AuthIn(BaseModel):
    email: str
    password: str = ""
    name: str = ""


class SendOtpIn(BaseModel):
    email: str
    purpose: str = "login"


class OtpLoginIn(BaseModel):
    email: str
    code: str
    name: str = ""


class ResetPasswordIn(BaseModel):
    email: str
    code: str
    password: str


def current_user(request: Request):
    user = auth.user_for(request.cookies.get(auth.COOKIE))
    if user:
        return user
    if not auth.AUTH_REQUIRED:
        return None
    raise HTTPException(401, "Sign in required")


def _set_session(response: Response, token: str):
    response.set_cookie(
        auth.COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=auth.SESSION_DAYS * 86400,
        path="/",
    )


@app.on_event("startup")
def _boot():
    auth.init_db()
    threading.Thread(target=_boot_engine, daemon=True, name="clip-boot").start()


@app.get("/", response_class=HTMLResponse)
@app.get("/closet", response_class=HTMLResponse)
@app.get("/history", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
@app.get("/register", response_class=HTMLResponse)
def home():
    return react_index()


@app.get("/health")
def health():
    return {"ok": True, "catalog": _engine is not None}


@app.get("/api/ready")
def ready():
    return {"catalog": _engine is not None, "error": _engine_error or ""}


@app.get("/api/auth/me")
def auth_me(request: Request):
    user = auth.user_for(request.cookies.get(auth.COOKIE))
    return {"user": user, "required": auth.AUTH_REQUIRED}


@app.get("/api/auth/check-email")
def auth_check_email(email: str = ""):
    exists = auth.check_email_exists(email)
    return {"exists": exists}


@app.post("/api/auth/send-otp")
def auth_send_otp(body: SendOtpIn):
    try:
        code = auth.generate_otp(body.email, body.purpose)
        print(f"[AUTH OTP] Sent OTP to {body.email} (purpose: {body.purpose}): {code}")
        return {"ok": True, "message": f"Verification code sent to {body.email}", "code": code}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/auth/otp-login")
def auth_otp_login(body: OtpLoginIn, response: Response):
    try:
        token, user = auth.verify_otp_login(body.email, body.code, body.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _set_session(response, token)
    return user


@app.post("/api/auth/reset-password")
def auth_reset_password(body: ResetPasswordIn, response: Response):
    try:
        token, user = auth.reset_password_with_otp(body.email, body.code, body.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _set_session(response, token)
    return user


@app.post("/api/auth/register")
def auth_register(body: AuthIn, response: Response):
    try:
        user = auth.register(body.name, body.email, body.password)
        token, user = auth.login(body.email, body.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _set_session(response, token)
    return user


@app.post("/api/auth/login")
def auth_login(body: AuthIn, response: Response):
    try:
        token, user = auth.login(body.email, body.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _set_session(response, token)
    return user


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    auth.logout(request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/meta")
def meta():
    return engine().meta()


@app.post("/api/chat")
def chat(body: ChatIn, _user=Depends(current_user)):
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(400, "Empty question")
    return engine().chat(q, body.gender, body.occasion, body.history)


@app.post("/api/match")
async def match(
    file: UploadFile = File(...),
    gender: str = Form("Any"),
    occasion: str = Form("Any"),
    _user=Depends(current_user),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")
    return engine().match_upload(raw, gender, occasion)


@app.get("/api/product/{pid}")
def product_img(pid: str):
    data = engine().product_jpeg(pid)
    if not data:
        raise HTTPException(404)
    return Response(data, media_type="image/jpeg")


@app.get("/api/outfit/{name}")
def outfit_img(name: str):
    data = engine().outfit_jpeg(name)
    if not data:
        raise HTTPException(404)
    return Response(data, media_type="image/png")


_TRYONS = {}
TRYON_DIR = os.path.join(HERE, "tryon_sessions")
os.makedirs(TRYON_DIR, exist_ok=True)
TRYON_TTL = 60 * 60 * 48


def _tryon_path(token):
    return os.path.join(TRYON_DIR, f"{token}.json")


def _save_tryon(token, pieces):
    _TRYONS[token] = pieces
    with open(_tryon_path(token), "w", encoding="utf-8") as f:
        json.dump({"tryon": pieces, "ts": time.time()}, f)


def _load_tryon(token):
    if token in _TRYONS:
        return _TRYONS[token]
    path = _tryon_path(token)
    if not os.path.isfile(path):
        return None
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() - float(data.get("ts") or 0) > TRYON_TTL:
        try:
            os.remove(path)
        except OSError:
            pass
        return None
    pieces = data.get("tryon") or []
    _TRYONS[token] = pieces
    return pieces


@app.post("/api/tryon")
def tryon_prep(body: TryOnIn, _user=Depends(current_user)):
    token = secrets.token_hex(8)
    _save_tryon(token, body.tryon)
    return {"token": token, "url": f"/tryon/{token}"}


@app.post("/api/tryon/warm")
def tryon_warm(body: TryOnIn, _user=Depends(current_user)):
    engine().prepare_garments(body.tryon)
    return {"ok": True}


@app.get("/api/tryon/{token}")
def tryon_data(token: str):
    pieces = _load_tryon(token)
    if pieces is None:
        raise HTTPException(404, "Try-on expired. Go back and tap Try on again.")
    return {"garments": engine().prepare_garments(pieces)}


@app.get("/tryon/{token}", response_class=HTMLResponse)
def tryon_page(token: str):
    if _load_tryon(token) is None:
        raise HTTPException(404, "Try-on expired. Go back and tap Try on again.")
    return react_index()
