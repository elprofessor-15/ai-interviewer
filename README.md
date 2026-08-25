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

## Clerk sign-in and saved interviews

Clerk sign-in is required by the React client. To enable verified user sessions and saved per-user history in the Hugging Face Space, add these values under Space Settings -> Variables and secrets:

- `CLERK_JWT_ISSUER` (the issuer URL from your Clerk instance)
- `CLERK_JWKS_URL` (your Clerk instance JWKS URL, usually `<issuer>/.well-known/jwks.json`)
- `MONGO_URI`
- `MONGO_DB_NAME=ai_interviewer`

The React build needs this client variable:

`VITE_CLERK_PUBLISHABLE_KEY`

Configure Google sign-in inside Clerk, not in this FastAPI server. Set `VITE_BACKEND_URL` only when the API is hosted on a different origin; leave it empty for the bundled same-origin Docker deployment. Never commit Clerk, MongoDB, or API secrets to this repository.

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference
