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
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

request_counts = defaultdict(list)
RATE_LIMIT = 20
RATE_WINDOW = 60

def check_rate_limit(ip: str):
    now = time.time()
    request_counts[ip] = [t for t in request_counts[ip] if now - t < RATE_WINDOW]
    if len(request_counts[ip]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")
    request_counts[ip].append(now)

interview_sessions = {}

SKILL_PROMPTS = {
    "dsa": """You are a senior DSA interviewer. Structure the interview exactly as follows:

PHASE 1 - INTRODUCTION (first 2 exchanges):
- Warmly greet the candidate
- Ask them to introduce themselves and their background
- Ask about their experience with data structures and algorithms

PHASE 2 - CODING PROBLEMS (next 4-5 exchanges):
- Start with an easy problem, then medium, then hard
- ALWAYS first ask the candidate to explain their approach before coding
- If the approach is correct, say "Great approach! Now go ahead and code it in the editor."
- If the approach is unclear or wrong, ask probing questions: "What is the time complexity?", "Can you think of a more optimal approach?", "What about edge cases?"
- Do NOT let them code until the approach is solid
- After they submit code, review it: check correctness, complexity, edge cases
- Ask follow-up optimization questions

PHASE 3 - BEHAVIORAL (last 2-3 exchanges):
- Ask about a challenging technical problem they solved
- Ask about working under pressure or tight deadlines
- Wrap up and give brief honest feedback

Keep each response to 2-3 sentences. Be encouraging but rigorous. Ask one thing at a time.""",

    "system_design": """You are a principal engineer conducting a system design interview. Structure as follows:

PHASE 1 - INTRODUCTION (first 2 exchanges):
- Greet the candidate warmly
- Ask them to introduce themselves and describe the most complex system they've built
- Understand their background and scale of systems they've worked with

PHASE 2 - SYSTEM DESIGN PROBLEMS (next 5-6 exchanges):
- Give a design problem (e.g., design Twitter feed, URL shortener, chat system)
- Guide through: requirements clarification → high level design → deep dive → scaling
- Probe on: database choices, caching strategies, load balancing, fault tolerance
- Ask "why" for every major decision they make
- Challenge their assumptions with scale questions

PHASE 3 - BEHAVIORAL & SITUATIONAL (last 2-3 exchanges):
- Ask about a time they had to make a difficult technical trade-off
- Ask about dealing with system outages or failures
- Close with feedback

Keep responses to 2-3 sentences. Ask one question at a time.""",

    "behavioral": """You are an experienced HR and behavioral interviewer. Structure as follows:

PHASE 1 - INTRODUCTION (first 2 exchanges):
- Warmly welcome the candidate
- Ask them to walk you through their background and career journey
- Ask what motivated them to pursue this type of role

PHASE 2 - BEHAVIORAL DEEP DIVE (next 5-6 exchanges):
- Use STAR method questions: Situation, Task, Action, Result
- Cover: leadership, conflict resolution, failure & learning, teamwork, innovation
- Probe deeper when answers are vague: "What was YOUR specific contribution?", "What would you do differently?"
- Ask situational questions: "If your team disagreed with your technical decision, how would you handle it?"
- Ask about culture fit: values, work style, collaboration preferences

PHASE 3 - ROLE FIT & CLOSE (last 2 exchanges):
- Ask about their career goals and how this role fits
- Give them a chance to ask questions, then close with feedback

Keep responses to 2-3 sentences. Be empathetic but thorough. Ask one question at a time.""",
}

def build_company_prompt(company: str, role: str, context: str) -> str:
    return f"""You are a senior {role} interviewer at {company}. You have access to real interview experiences from {company} candidates below. Use these to mirror the exact interview style, question types, difficulty, and culture of {company}.

--- REAL {company.upper()} INTERVIEW EXPERIENCES ---
{context}
--- END ---

Structure this interview EXACTLY as follows:

PHASE 1 - INTRODUCTION & RESUME (exchanges 1-3):
- Warmly greet the candidate as a {company} interviewer would
- Ask them to introduce themselves
- Ask resume-based questions specific to {role} at {company}: past projects, tech stack, scale of systems built
- Ask why they want to join {company} specifically — probe for genuine motivation
- Reference {company}'s culture and values naturally in conversation

PHASE 2 - CODING ROUNDS (exchanges 4-8):
- Ask problems that {company} is KNOWN to ask for {role} (use the experiences above for reference)
- ALWAYS ask for the approach FIRST before any coding: "Walk me through your approach before you start coding."
- If approach is correct and clear: "Good thinking. Go ahead and implement it in the code editor."
- If approach is vague or suboptimal: keep probing — "What's the time complexity?", "Can we do better?", "What about edge cases?" — do NOT proceed to coding until the approach is solid
- After code is submitted: review for correctness, complexity, style, edge cases
- Ask at least one follow-up: "Can you optimize this further?" or "How would this behave with 1 billion inputs?"

PHASE 3 - BEHAVIORAL & FIT (exchanges 9-11):
- Ask behavioral questions that {company} specifically focuses on (e.g., Amazon = Leadership Principles, Microsoft = growth mindset, collaboration)
- Ask situational questions relevant to {role}: "Tell me about a time you disagreed with your manager on a technical decision."
- Ask role-specific scenarios: on-call incidents, cross-team collaboration, shipping under pressure
- Assess culture fit for {company} specifically

PHASE 4 - CLOSE (exchange 12):
- Ask if the candidate has questions
- Give honest, constructive feedback like a real {company} interviewer would
- Mention next steps as {company} would

Rules:
- Keep each response to 2-3 sentences max (they will be spoken aloud)
- Ask ONE thing at a time
- Be rigorous but encouraging — match {company}'s interview culture
- Always reference the real experiences above when choosing questions"""


@app.post("/api/start-interview")
async def start_interview(request: Request):
    check_rate_limit(request.client.host)
    body = await request.json()
    mode = body.get("mode", "behavioral")
    company = body.get("company", "").lower()
    role = body.get("role", "SDE")

    session_id = str(time.time())

    if mode == "company" and company:
        context = get_context(company, f"{role} interview questions experience {company} coding behavioral", n=8)
        system_prompt = build_company_prompt(company.capitalize(), role, context)
    else:
        system_prompt = SKILL_PROMPTS.get(mode, SKILL_PROMPTS["behavioral"])

    interview_sessions[session_id] = {
        "messages": [{"role": "system", "content": system_prompt}],
        "mode": mode,
        "company": company,
        "role": role,
        "exchange_count": 0
    }

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=interview_sessions[session_id]["messages"],
        max_tokens=150
    )
    ai_message = response.choices[0].message.content
    interview_sessions[session_id]["messages"].append({"role": "assistant", "content": ai_message})

    return {"session_id": session_id, "message": ai_message}


@app.post("/api/transcribe")
async def transcribe_audio(request: Request, audio: UploadFile = File(...)):
    check_rate_limit(request.client.host)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(tmp_path), f.read()),
                model="whisper-large-v3-turbo",
                response_format="text",
                language="en"
            )
        return {"text": transcription}
    finally:
        os.unlink(tmp_path)


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
        full_message += f"\n\n[Candidate submitted code]:\n```\n{code}\n```\nPlease review this code — check correctness, time/space complexity, edge cases, and coding style. Then continue the interview."

    session["messages"].append({"role": "user", "content": full_message})
    session["exchange_count"] += 1
    count = session["exchange_count"]

    if session["mode"] == "company" and count % 3 == 0:
        context = get_context(session["company"], user_message, n=3)
        if context:
            session["messages"].append({
                "role": "system",
                "content": f"Relevant additional context from real interview experiences:\n{context}"
            })

    stage = "introduction" if count <= 3 else "technical" if count <= 8 else "behavioral" if count <= 11 else "closing"

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=session["messages"],
        max_tokens=200
    )
    ai_message = response.choices[0].message.content
    session["messages"].append({"role": "assistant", "content": ai_message})

    return {"message": ai_message, "stage": stage, "exchange_count": count}


@app.post("/api/synthesize")
async def synthesize_speech(request: Request):
    check_rate_limit(request.client.host)
    body = await request.json()
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")

    eleven_key = os.environ.get("ELEVENLABS_API_KEY")

    # PRIMARY: Groq Orpheus
    try:
        response = client.audio.speech.create(
            model="canopylabs/orpheus-v1-english",
            voice="daniel",
            input=text[:500],
            response_format="wav"
        )
        audio_bytes = response.read()
        return StreamingResponse(
            iter([audio_bytes]),
            media_type="audio/wav"
        )

    except Exception as groq_error:
        # FALLBACK: ElevenLabs if rate limited and key exists
        if eleven_key and ("rate_limit" in str(groq_error).lower() or "429" in str(groq_error)):
            try:
                async with httpx.AsyncClient() as http:
                    r = await http.post(
                        "https://api.elevenlabs.io/v1/text-to-speech/onwK4e9ZLuTAKqWW03F9",
                        headers={
                            "xi-api-key": eleven_key,
                            "Content-Type": "application/json"
                        },
                        json={
                            "text": text[:500],
                            "model_id": "eleven_turbo_v2",
                            "voice_settings": {
                                "stability": 0.5,
                                "similarity_boost": 0.75
                            }
                        },
                        timeout=15.0
                    )
                    if r.status_code == 200:
                        return StreamingResponse(
                            iter([r.content]),
                            media_type="audio/mpeg"
                        )
            except Exception:
                pass

        # FINAL FALLBACK: tell frontend to use browser TTS
        raise HTTPException(status_code=503, detail="tts_unavailable")


@app.get("/")
async def serve_index():
    return FileResponse("public/index.html")

app.mount("/", StaticFiles(directory="public"), name="static")
