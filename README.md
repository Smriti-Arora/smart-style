# Smart Style

AI fashion stylist: CLIP catalog search, occasion outfits, Gemini chat, closet complete-look, and webcam try-on.

**Frontend:** React (Vite) in `frontend/`, built to `frontend/dist/`  
**Backend:** FastAPI in `server.py` — one URL: http://127.0.0.1:8000/

## Run locally

Python 3.11+, the existing `myenv`, Node.js (only if you need to rebuild the UI), and these files next to this README:

- `df_with_labels.pkl`
- `clip_embeddings.npy`
- `images/`

```bat
copy .env.example .env
REM put GEMINI_API_KEY in .env

run.bat
```

Or:

```bat
cd frontend
npm install
npm run build
cd ..
myenv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/ — create an account, then the stylist opens. First boot loads CLIP (~30–60s).

## Environment

| Variable | Required | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | for chat answers | Gemini key. Without it, catalog + tips still work. |
| `TRYON_ENABLED` | no, local default `1` | `0` skips SegFormer / try-on (use this on a small host). |
| `AUTH_REQUIRED` | no, default `1` | `0` skips login. Accounts live in SQLite (`data/smart_style.db`). |

`.env` is git-ignored. Never put keys in source.

## Docker

Needs Docker Desktop, the two data files, `images/`, and `.env`.

```bash
docker compose up --build
```

App: http://localhost:8000  
Health: http://localhost:8000/health

## Demo prompts

- `outfit for women for diwali`
- `lehenga for wedding`
- `karwa chauth outfit`
- `diwali outfit for men`
- `blue casual jeans for men`
