"""MongoDB persistence for authenticated users and interview sessions."""

import os
import time

from bson import ObjectId
from pymongo import MongoClient
from pymongo.server_api import ServerApi

MONGO_URI = os.environ.get("MONGO_URI", "")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "ai_interviewer")
_client = MongoClient(MONGO_URI, server_api=ServerApi("1"), connect=False) if MONGO_URI else None
_db = _client[MONGO_DB_NAME] if _client is not None else None
_users = _db["users"] if _db is not None else None
_interviews = _db["interviews"] if _db is not None else None
_session_cache = {}
SESSION_CACHE_TTL = 30


def init_db():
    if _db is None:
        return
    _users.create_index("auth_sub", unique=True)
    _interviews.create_index([("user_id", 1), ("started_at", -1)])


def _require_db():
    if not _db:
        raise RuntimeError("MONGO_URI is not configured")


def _public_user(user):
    return {
        "id": str(user["_id"]),
        "auth_sub": user.get("auth_sub", ""),
        "email": user.get("email", ""),
        "name": user.get("name", ""),
        "picture": user.get("picture", ""),
    }


def upsert_user(auth_sub, email, name="", picture=""):
    _require_db()
    now = time.time()
    _users.update_one(
        {"auth_sub": auth_sub},
        {
            "$set": {"email": email, "name": name, "picture": picture, "updated_at": now},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return _public_user(_users.find_one({"auth_sub": auth_sub}))


def get_user(user_id):
    if _db is None or not user_id:
        return None
    try:
        user = _users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None
    return _public_user(user) if user else None


def save_interview(session_id, user_id, session, feedback=None):
    _require_db()
    if not user_id:
        return
    transcript = [
        {"role": message["role"], "content": message["content"]}
        for message in session.get("messages", [])
        if message.get("role") in {"user", "assistant"}
    ]
    now = time.time()
    _interviews.update_one(
        {"_id": session_id},
        {
            "$set": {
                "user_id": user_id,
                "mode": session.get("mode", "behavioral"),
                "company": session.get("company", ""),
                "role": session.get("role", ""),
                "started_at": session.get("start_time", now),
                "ended_at": now if session.get("ended") else None,
                "transcript": transcript,
                "feedback": feedback,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    _session_cache.pop(user_id, None)


def list_interviews(user_id, limit=50):
    _require_db()
    now = time.time()
    cached = _session_cache.get(user_id)
    if cached and now - cached["created_at"] < SESSION_CACHE_TTL:
        return cached["items"]
    items = []
    projection = {"mode": 1, "company": 1, "role": 1, "started_at": 1, "ended_at": 1, "feedback": 1}
    cursor = _interviews.find({"user_id": user_id}, projection).sort("started_at", -1).limit(min(max(limit, 1), 100))
    for interview in cursor:
        items.append({
            "id": interview["_id"],
            "mode": interview.get("mode", "behavioral"),
            "company": interview.get("company", ""),
            "role": interview.get("role", ""),
            "started_at": interview.get("started_at"),
            "ended_at": interview.get("ended_at"),
            "has_feedback": interview.get("feedback") is not None,
        })
    _session_cache[user_id] = {"created_at": now, "items": items}
    return items


def get_interview(user_id, interview_id):
    _require_db()
    interview = _interviews.find_one({"_id": interview_id, "user_id": user_id})
    if not interview:
        return None
    return {
        "id": interview["_id"],
        "mode": interview.get("mode", "behavioral"),
        "company": interview.get("company", ""),
        "role": interview.get("role", ""),
        "started_at": interview.get("started_at"),
        "ended_at": interview.get("ended_at"),
        "transcript": interview.get("transcript", []),
        "feedback": interview.get("feedback"),
    }


init_db()
