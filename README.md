---
title: Ai Interviewer
emoji: 📈
colorFrom: green
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
---

Live App Link: https://elprofessor15-ai-interviewer.hf.space/

## Google sign-in and saved interviews

Google sign-in is optional. Without it, interviews continue to work anonymously. To enable saved per-user history in the Hugging Face Space, add these values under Space Settings -> Variables and secrets:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `SESSION_SECRET` (a long random value)
- `DATABASE_PATH=/data/ai_interviewer.db`

In Google Cloud OAuth credentials, add this authorized redirect URI:

`https://elprofessor15-ai-interviewer.hf.space/auth/callback`

Enable persistent storage for the Space and mount it at `/data`; otherwise the SQLite database is local to the running container and can be lost when the Space restarts. Never commit OAuth secrets or API keys to this repository.

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference
