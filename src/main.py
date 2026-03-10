from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
import os, tempfile, time
import httpx
from groq import Groq
from dotenv import load_dotenv
from collections import defaultdict
from src.rag import get_context

load_dotenv()

app = FastAPI()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

request_counts = defaultdict(list)
RATE_LIMIT = 30
RATE_WINDOW = 60

def check_rate_limit(ip: str):
    now = time.time()
    request_counts[ip] = [t for t in request_counts[ip] if now - t < RATE_WINDOW]
    if len(request_counts[ip]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")
    request_counts[ip].append(now)

interview_sessions = {}

# ── LLM with fallback chain: Groq → Gemini → OpenRouter ──
async def call_llm(messages: list, max_tokens: int = 200) -> str:
    # 1. Try Groq
    if groq_client:
        try:
            res = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=max_tokens
            )
            return res.choices[0].message.content
        except Exception as e:
            if "rate_limit" not in str(e).lower() and "429" not in str(e):
                raise e
            print("Groq LLM limit hit, trying Gemini...")

    # 2. Try Google Gemini
    if GOOGLE_API_KEY:
        try:
            async with httpx.AsyncClient() as http:
                # Convert messages for Gemini format
                system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
                contents = []
                for m in messages:
                    if m["role"] == "system":
                        continue
                    role = "user" if m["role"] == "user" else "model"
                    contents.append({"role": role, "parts": [{"text": m["content"]}]})
                if not contents:
                    contents = [{"role": "user", "parts": [{"text": "Hello"}]}]

                payload = {
                    "contents": contents,
                    "generationConfig": {"maxOutputTokens": max_tokens}
                }
                if system_msg:
                    payload["systemInstruction"] = {"parts": [{"text": system_msg}]}

                r = await http.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GOOGLE_API_KEY}",
                    json=payload,
                    timeout=30.0
                )
                if r.status_code == 200:
                    data = r.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                print(f"Gemini error: {r.status_code} {r.text}")
        except Exception as e:
            print(f"Gemini failed: {e}")

    # 3. Try OpenRouter
    if OPENROUTER_API_KEY:
        try:
            async with httpx.AsyncClient() as http:
                r = await http.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "meta-llama/llama-3.3-70b-instruct:free",
                        "messages": messages,
                        "max_tokens": max_tokens
                    },
                    timeout=30.0
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
                print(f"OpenRouter error: {r.status_code}")
        except Exception as e:
            print(f"OpenRouter failed: {e}")

    raise HTTPException(status_code=503, detail="All LLM providers exhausted")


# ── STT with fallback: Groq Whisper → Deepgram ──
async def transcribe(audio_content: bytes, filename: str) -> str:
    # 1. Groq Whisper
    if groq_client:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
                tmp.write(audio_content)
                tmp_path = tmp.name
            with open(tmp_path, "rb") as f:
                result = groq_client.audio.transcriptions.create(
                    file=(filename, f.read()),
                    model="whisper-large-v3-turbo",
                    response_format="text",
                    language="en"
                )
            os.unlink(tmp_path)
            return result
        except Exception as e:
            print(f"Groq STT failed: {e}")

    # 2. Deepgram
    if DEEPGRAM_API_KEY:
        try:
            async with httpx.AsyncClient() as http:
                r = await http.post(
                    "https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true&language=en",
                    headers={
                        "Authorization": f"Token {DEEPGRAM_API_KEY}",
                        "Content-Type": "audio/webm"
                    },
                    content=audio_content,
                    timeout=20.0
                )
                if r.status_code == 200:
                    return r.json()["results"]["channels"][0]["alternatives"][0]["transcript"]
        except Exception as e:
            print(f"Deepgram STT failed: {e}")

    raise HTTPException(status_code=503, detail="All STT providers exhausted")


# ── TTS with fallback chain: Groq Orpheus → ElevenLabs → Browser signal ──
async def synthesize(text: str):
    # 1. Groq Orpheus
    if groq_client:
        try:
            response = groq_client.audio.speech.create(
                model="canopylabs/orpheus-v1-english",
                voice="daniel",
                input=text[:500],
                response_format="wav"
            )
            return response.read(), "audio/wav"
        except Exception as e:
            print(f"Groq TTS failed: {e}")

    # 2. ElevenLabs
    if ELEVENLABS_API_KEY:
        try:
            async with httpx.AsyncClient() as http:
                r = await http.post(
                    "https://api.elevenlabs.io/v1/text-to-speech/onwK4e9ZLuTAKqWW03F9",
                    headers={
                        "xi-api-key": ELEVENLABS_API_KEY,
                        "Content-Type": "application/json"
                    },
                    json={
                        "text": text[:500],
                        "model_id": "eleven_turbo_v2",
                        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
                    },
                    timeout=15.0
                )
                if r.status_code == 200:
                    return r.content, "audio/mpeg"
        except Exception as e:
            print(f"ElevenLabs TTS failed: {e}")

    return None, None


SKILL_PROMPTS = {
    "dsa": """You are a senior DSA interviewer. Structure the interview exactly as follows:

PHASE 1 - INTRODUCTION (first 2 exchanges):
- Warmly greet the candidate. Introduce yourself as Alex.
- Ask them to introduce themselves and their background
- Ask about their experience with data structures and algorithms

PHASE 2 - CODING PROBLEMS (next 4-5 exchanges):
- Start with an easy problem, then medium, then hard
- ALWAYS first ask the candidate to explain their approach before coding
- If the approach is correct, say "Great approach! Now go ahead and code it in the editor."
- If the approach is unclear or wrong, probe: "What is the time complexity?", "Can you think of a more optimal approach?"
- Do NOT let them code until the approach is solid
- After they submit code, review it: check correctness, complexity, edge cases
- Ask follow-up optimization questions

PHASE 3 - BEHAVIORAL (last 2-3 exchanges):
- Ask about a challenging technical problem they solved
- Wrap up and give brief honest feedback

Keep each response to 2-3 sentences. Ask one thing at a time.""",

    "system_design": """You are a principal engineer conducting a system design interview. Introduce yourself as Alex.

PHASE 1 - INTRODUCTION (first 2 exchanges):
- Greet warmly, introduce as Alex
- Ask them to describe the most complex system they've built

PHASE 2 - DESIGN PROBLEMS (next 5-6 exchanges):
- Give a design problem
- Guide: requirements → high level → deep dive → scaling
- Probe on: databases, caching, load balancing, fault tolerance
- Ask "why" for every major decision

PHASE 3 - CLOSE (last 2 exchanges):
- Ask about a difficult technical trade-off they made
- Close with feedback

Keep responses to 2-3 sentences. Ask one question at a time.""",

    "behavioral": """You are an experienced HR interviewer. Introduce yourself as Alex.

PHASE 1 - INTRODUCTION (first 2 exchanges):
- Warmly welcome, introduce as Alex
- Ask them to walk through their background

PHASE 2 - BEHAVIORAL (next 5-6 exchanges):
- Use STAR method: Situation, Task, Action, Result
- Cover: leadership, conflict, failure & learning, teamwork
- Probe deeper: "What was YOUR specific contribution?"

PHASE 3 - CLOSE (last 2 exchanges):
- Ask about career goals
- Close with feedback

Keep responses to 2-3 sentences. Ask one question at a time.""",
}

def build_company_prompt(company: str, role: str, context: str) -> str:
    return f"""You are a senior {role} interviewer at {company}. Your name is Alex.

--- REAL {company.upper()} INTERVIEW EXPERIENCES ---
{context}
--- END ---

PHASE 1 - INTRODUCTION & RESUME (exchanges 1-3):
- Introduce yourself as Alex, senior {role} interviewer at {company}
- Ask candidate to introduce themselves
- Ask resume-based questions: past projects, tech stack, scale
- Ask why they want to join {company}

PHASE 2 - CODING ROUNDS (exchanges 4-8):
- Ask problems {company} is KNOWN to ask for {role}
- ALWAYS ask for approach FIRST before coding
- If approach correct: "Good. Go ahead and implement it in the code editor."
- If vague: probe on complexity, edge cases, optimization
- After code submitted: review correctness, complexity, style

PHASE 3 - BEHAVIORAL & FIT (exchanges 9-11):
- Ask behavioral questions {company} focuses on
- Amazon = Leadership Principles, Microsoft = growth mindset

PHASE 4 - CLOSE (exchange 12):
- Give honest constructive feedback

Rules: 2-3 sentences max per response. ONE question at a time."""


@app.post("/api/start-interview")
async def start_interview(request: Request):
    check_rate_limit(request.client.host)
    body = await request.json()
    mode = body.get("mode", "behavioral")
    company = (body.get("company") or "").lower()
    role = body.get("role", "SDE")
    user_name = body.get("user_name", "")

    session_id = str(time.time())

    if mode == "company" and company:
        context = get_context(company, f"{role} interview questions {company} coding behavioral", n=8)
        system_prompt = build_company_prompt(company.capitalize(), role, context)
    else:
        system_prompt = SKILL_PROMPTS.get(mode, SKILL_PROMPTS["behavioral"])

    if user_name:
        system_prompt += f"\n\nThe candidate's name is {user_name}. Use their name naturally."

    interview_sessions[session_id] = {
        "messages": [{"role": "system", "content": system_prompt}],
        "mode": mode,
        "company": company,
        "role": role,
        "user_name": user_name,
        "exchange_count": 0,
        "start_time": time.time()
    }

    ai_message = await call_llm(interview_sessions[session_id]["messages"], max_tokens=150)
    interview_sessions[session_id]["messages"].append({"role": "assistant", "content": ai_message})
    return {"session_id": session_id, "message": ai_message}


@app.post("/api/transcribe")
async def transcribe_audio(request: Request, audio: UploadFile = File(...)):
    check_rate_limit(request.client.host)
    content = await audio.read()
    text = await transcribe(content, audio.filename or "rec.webm")
    return {"text": text}


@app.post("/api/respond")
async def get_response(request: Request):
    check_rate_limit(request.client.host)
    body = await request.json()
    session_id = body.get("session_id")
    user_message = body.get("message", "")
    code = body.get("code", "")

    if not session_id or session_id not in interview_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = interview_sessions[session_id]
    full_message = user_message
    if code.strip():
        full_message += f"\n\n[Candidate submitted code]:\n```\n{code}\n```\nReview: correctness, time/space complexity, edge cases, style. Then continue."

    session["messages"].append({"role": "user", "content": full_message})
    session["exchange_count"] += 1
    count = session["exchange_count"]

    if session["mode"] == "company" and count % 3 == 0:
        context = get_context(session["company"], user_message, n=3)
        if context:
            session["messages"].append({
                "role": "system",
                "content": f"Relevant context from real interview experiences:\n{context}"
            })

    stage = "introduction" if count <= 3 else "technical" if count <= 8 else "behavioral" if count <= 11 else "closing"
    ai_message = await call_llm(session["messages"], max_tokens=200)
    session["messages"].append({"role": "assistant", "content": ai_message})
    return {"message": ai_message, "stage": stage, "exchange_count": count}


@app.post("/api/synthesize")
async def synthesize_speech(request: Request):
    check_rate_limit(request.client.host)
    body = await request.json()
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")

    audio_bytes, media_type = await synthesize(text)
    if audio_bytes:
        return StreamingResponse(iter([audio_bytes]), media_type=media_type)

    # Signal frontend to use browser TTS
    raise HTTPException(status_code=503, detail="tts_unavailable")


@app.get("/")
async def serve_index():
    return FileResponse("public/index.html")

app.mount("/", StaticFiles(directory="public"), name="static")