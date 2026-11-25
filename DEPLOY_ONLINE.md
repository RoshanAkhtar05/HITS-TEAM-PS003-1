# Put TATHYA-DF online (Render + Vercel)

This repository is preconfigured for a FastAPI backend on Render and a Vite frontend on Vercel. The backend uses a persistent Render disk for SQLite, uploaded evidence, and case workspaces. The Render `starter` service and disk are paid.

## 1. Push the source to GitHub

Create a GitHub repository and push this project folder. Do not upload `backend/.env`, `.venv`, `frontend/node_modules`, uploads, case data, or database files.

## 2. Deploy the backend on Render

1. In Render, choose **New → Blueprint** and connect the GitHub repository.
2. Render reads `render.yaml`; approve creation of `tathya-df-api`.
3. When asked for `CORS_ORIGINS`, enter the Vercel site origin after you create it, for example `https://your-site.vercel.app` (no trailing slash). You can update it later in the Render service environment settings.
4. Wait for the build and deployment. Copy the backend URL, e.g. `https://tathya-df-api.onrender.com`.
5. Check `https://YOUR-BACKEND-URL/docs` loads.

## 3. Deploy the frontend on Vercel

1. In Vercel, choose **Add New → Project** and import the same GitHub repository.
2. Set **Root Directory** to `frontend`.
3. Framework preset: **Vite**; Build Command: `npm run build`; Output Directory: `dist`.
4. Add Environment Variable: `VITE_API_BASE_URL` = your Render backend URL (e.g. `https://tathya-df-api.onrender.com`).
5. Deploy and copy the Vercel site URL.
6. Return to Render → Environment and set `CORS_ORIGINS` to that exact Vercel origin, then redeploy the backend.

## 4. Verify the live app

Open the Vercel URL. Create a synthetic demo case, upload the bundled sample files from `raw_data/`, process them, open the graph/timeline, and export the PDF. Do not upload real or sensitive case evidence to a public demo.

## Important

- The Render service and persistent disk in `render.yaml` are configured as a paid starter deployment. Confirm current provider pricing before creating resources.
- Keep `CORS_ORIGINS` restricted to your Vercel domain; do not use `*` with credentials.
- Do not add API keys or database passwords to GitHub.
- This is a demonstration prototype, not a hardened public forensic service. Before public use, add authentication, authorization, rate limits, secure evidence access, and operational monitoring.
- The app's optional Supabase/Neo4j/Redis/Gemini/Ollama integrations remain optional. The Render persistent disk is used for local SQLite and runtime evidence/workspace storage.
