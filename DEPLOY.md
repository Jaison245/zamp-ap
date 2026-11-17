# Deploying Zamp AP to Render

The whole app is **one Docker image**: it builds the React UI and serves it
together with the FastAPI API on a single port. Render reads `render.yaml`
(a Blueprint) and does the rest.

> Repo: `https://github.com/Jaison245/zamp-ap`

## 1. Deploy (one time, ~2 min of clicks + ~5 min build)

1. Go to **https://dashboard.render.com** and sign in with **GitHub**
   (use the same `Jaison245` account).
2. Click **New +** → **Blueprint**.
3. Pick the **`zamp-ap`** repository → **Connect**.
4. Render detects `render.yaml` and shows one web service, `zamp-ap`
   (Docker, Free plan). Click **Apply** / **Create**.
5. Wait for the build. First build ≈ 4–7 min (installs Python deps + builds the
   UI). When the status is **Live**, open the URL it gives you, e.g.
   `https://zamp-ap.onrender.com`.

That URL is your judge-clickable live link. It serves the UI at `/` and the API
under `/api`.

## 2. (Optional) Turn on real Claude extraction

By default the app runs in **mock mode** — deterministic, free, and perfect for a
reliable demo (the pipeline, decisions, and UI are all 100% real; only the
PDF-reading step is replaced by a ground-truth stand-in).

To use the real model instead:

1. Render dashboard → the `zamp-ap` service → **Environment**.
2. Add a variable: `ANTHROPIC_API_KEY` = your key → **Save**.
   (The service redeploys automatically.)
3. The health badge in the app's sidebar will flip from `mock` to `claude`.

`EXTRACTOR` is already set to `auto`, so the app uses Claude whenever a key is
present and falls back to mock when it isn't.

## 3. Good to know

- **Free tier sleeps after ~15 min idle.** The first click after a nap takes
  ~50s to wake, then it's fast. Before you share the link with a judge (or start
  your recording), open it once yourself to warm it up.
- **Storage is ephemeral.** `app.db` and uploaded PDFs reset on each deploy/restart.
  That's fine — the app reloads all master data on boot, and **Data & rules →
  Reset demo data** gives you a clean slate any time.
- **Health check:** Render pings `/api/health`; it returns `{"status":"ok"}`.
- **Updating:** push to `main` and Render auto-redeploys (`autoDeploy: true`).

## 4. Local run (for the recording, no Docker needed)

```bash
.venv/Scripts/python.exe -m uvicorn backend.main:app --port 8077
```
Open http://localhost:8077.
