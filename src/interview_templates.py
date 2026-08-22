"""Compact interview templates and stage guidance."""

BASE_TEMPLATE = """You are Alex, a realistic {role} interviewer{company_phrase}.
Interview plan: {plan}
Candidate context: {resume_context}
Rules: start with a warm introduction question; ask one clear question at a time; use the candidate's answer before choosing the next question; never invent resume details; keep replies to 2-3 natural sentences; probe vague claims with one specific follow-up; be supportive but honest.
Current stage: {stage}
Stage objective: {stage_objective}
"""

PLANS = {
    "behavioral": "introduction and background -> resume/project deep dive -> STAR questions on leadership, conflict, failure, teamwork -> goals and close",
    "dsa": "introduction and experience -> approach-first coding problem -> implementation review and optimization -> technical reflection and close",
    "system_design": "introduction and systems experience -> requirements -> high-level design -> deep dive on data, scaling and reliability -> trade-offs and close",
    "company": "introduction and resume -> company-specific technical questions -> behavioral and culture fit -> feedback and close",
}

STAGE_OBJECTIVES = {
    "introduction": "Ask the candidate to introduce themselves, then connect the next question to their background or resume.",
    "technical": "Explore one technical claim or problem at a time. Ask for reasoning before accepting an answer or code.",
    "behavioral": "Use STAR follow-ups and ask for the candidate's specific contribution, measurable result, and lesson learned.",
    "closing": "Ask one final reflection or goal question, then keep the response concise and constructive.",
}


def build_interview_template(mode, role, company="", resume_context="", stage="introduction"):
    mode = mode if mode in PLANS else "behavioral"
    company_phrase = f" at {company}" if company else ""
    context = resume_context or "No resume provided; learn the candidate's background through questions."
    return BASE_TEMPLATE.format(
        role=role,
        company_phrase=company_phrase,
        plan=PLANS[mode],
        resume_context=context,
        stage=stage,
        stage_objective=STAGE_OBJECTIVES[stage],
    )


def stage_for_exchange(exchange_count):
    if exchange_count <= 3:
        return "introduction"
    if exchange_count <= 8:
        return "technical"
    if exchange_count <= 11:
        return "behavioral"
    return "closing"


def compact_messages(session):
    """Keep prompts small while retaining the latest conversational context."""
    messages = session["messages"]
    system = messages[0]
    recent = messages[-8:]
    if recent and recent[0] is system:
        return messages
    return [system] + recent
