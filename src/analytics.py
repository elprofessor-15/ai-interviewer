import json
import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("GROQ_API_KEY", "")
client = Groq(api_key=api_key) if api_key else None
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")

def analyze_interview(session: dict) -> dict:
    messages = session.get("messages", [])
    mode = session.get("mode", "general")
    company = session.get("company", "")
    role = session.get("role", "SDE")

    # Build transcript
    transcript = ""
    for m in messages:
        if m["role"] == "user":
            transcript += f"CANDIDATE: {m['content']}\n\n"
        elif m["role"] == "assistant":
            transcript += f"INTERVIEWER: {m['content']}\n\n"

    if not transcript.strip():
      return {"error": "No interview answers were recorded."}
    if not client:
      return {"error": "Feedback is unavailable because no LLM provider is configured."}

    prompt = f"""You are an exacting but supportive interview coach analyzing a {mode} interview for a {role} role{' at ' + company.capitalize() if company else ''}.

Here is the full interview transcript:
---
{transcript[:6000]}
---

Analyze evidence from the candidate's actual answers. Do not praise generic traits or invent details. Return ONLY valid JSON with EXACTLY this structure:
{{
  "overall_score": <number 0-100>,
  "summary": "<2-3 sentence honest assessment naming the clearest evidence>",
  "strong_points": [
    {{"title": "<strength title>", "detail": "<specific example from interview>"}},
    {{"title": "<strength title>", "detail": "<specific example from interview>"}},
    {{"title": "<strength title>", "detail": "<specific example from interview>"}}
  ],
  "pain_points": [
    {{"title": "<weakness title>", "detail": "<specific example and why it matters>"}},
    {{"title": "<weakness title>", "detail": "<specific example and why it matters>"}},
    {{"title": "<weakness title>", "detail": "<specific example and why it matters>"}}
  ],
  "areas_of_improvement": [
    {{"title": "<area>", "action": "<specific actionable advice>"}},
    {{"title": "<area>", "action": "<specific actionable advice>"}},
    {{"title": "<area>", "action": "<specific actionable advice>"}}
  ],
  "skill_scores": {{
    "technical": <0-100>,
    "communication": <0-100>,
    "problem_solving": <0-100>,
    "confidence": <0-100>,
    "cultural_fit": <0-100>
  }},
  "hiring_verdict": "<Strong Hire | Hire | Maybe | No Hire>",
  "verdict_reason": "<one sentence explanation grounded in the transcript>",
  "next_steps": [
    "<a concrete practice exercise for this week>",
    "<a concrete practice exercise for the next interview>"
  ]
}}"""

    options = {
      "model": GROQ_MODEL,
      "messages": [{"role": "user", "content": prompt}],
      "max_tokens": 1200,
    }
    if GROQ_MODEL.startswith("openai/gpt-oss"):
      options["reasoning_effort"] = "low"
    response = client.chat.completions.create(**options)

    raw = response.choices[0].message.content.strip()
    # Strip markdown if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
      result = json.loads(raw)
      required = ["overall_score", "summary", "strong_points", "pain_points", "areas_of_improvement", "skill_scores", "hiring_verdict", "verdict_reason", "next_steps"]
      if not all(key in result for key in required):
        return {"error": "Feedback response was incomplete", "raw": raw}
      return result
    except Exception:
        return {"error": "Could not parse analysis", "raw": raw}