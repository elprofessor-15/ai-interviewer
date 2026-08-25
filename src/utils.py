import os

# import json
import time
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv

load_dotenv()

uri = os.environ.get("MONGO_URI", "")

# Create one MongoDB client for the application.
client = MongoClient(uri, server_api=ServerApi("1"))

db = client["some_db"]

users_collection = db["users"]
interviews_collection = db["interviews"]


def mongo_connect():
    """
    Test the MongoDB connection.
    """
    try:
        client.admin.command("ping")
        print("Pinged your deployment. You successfully connected to MongoDB!")
        return True
    except Exception as e:
        print(f"MongoDB connection failed: {e}")
        return False


def upsert_user(google_sub, email, name="", picture=""):
    """
    Create a user if they don't exist.
    Otherwise update their information.

    Returns the user document.
    """

    now = time.time()

    users_collection.update_one(
        {"google_sub": google_sub},
        {
            "$set": {
                "email": email,
                "name": name,
                "picture": picture,
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            },
        },
        upsert=True,
    )

    user = users_collection.find_one(
        {"google_sub": google_sub},
        {
            "_id": 1,
            "google_sub": 1,
            "email": 1,
            "name": 1,
            "picture": 1,
        },
    )

    return user


def get_user(user_id):
    """
    Get a user by their MongoDB _id.
    """

    from bson import ObjectId

    try:
        user = users_collection.find_one(
            {"_id": ObjectId(user_id)},
            {
                "_id": 1,
                "google_sub": 1,
                "email": 1,
                "name": 1,
                "picture": 1,
            },
        )
    except Exception:
        return None

    return user


def get_user_by_google_sub(google_sub):
    """
    Get a user using their Google subject ID.
    """

    return users_collection.find_one({"google_sub": google_sub})


def save_interview(session_id, user_id, session, feedback=None):
    """
    Create or update an interview.
    """

    if not user_id:
        return

    transcript = [
        {
            "role": message["role"],
            "content": message["content"],
        }
        for message in session.get("messages", [])
        if message.get("role") in {"user", "assistant"}
    ]

    now = time.time()

    interview = {
        "user_id": user_id,
        "mode": session.get("mode", "behavioral"),
        "company": session.get("company", ""),
        "role": session.get("role", ""),
        "started_at": session.get("start_time", now),
        "ended_at": now if session.get("ended") else None,
        "transcript": transcript,
        "feedback": feedback,
        "updated_at": now,
    }

    interviews_collection.update_one(
        {"_id": session_id},
        {
            "$set": interview,
            "$setOnInsert": {
                "created_at": now,
            },
        },
        upsert=True,
    )


def list_interviews(user_id, limit=50):
    """
    Get all interviews belonging to a user.
    """

    limit = min(max(limit, 1), 100)

    cursor = (
        interviews_collection.find(
            {"user_id": user_id},
            {
                "_id": 1,
                "mode": 1,
                "company": 1,
                "role": 1,
                "started_at": 1,
                "ended_at": 1,
                "feedback": 1,
            },
        )
        .sort("started_at", -1)
        .limit(limit)
    )

    items = []

    for interview in cursor:
        items.append(
            {
                "id": interview["_id"],
                "mode": interview.get("mode", "behavioral"),
                "company": interview.get("company", ""),
                "role": interview.get("role", ""),
                "started_at": interview.get("started_at"),
                "ended_at": interview.get("ended_at"),
                "has_feedback": interview.get("feedback") is not None,
            }
        )

    return items


def get_interview(user_id, interview_id):
    """
    Get one interview belonging to a specific user.
    """

    interview = interviews_collection.find_one(
        {
            "_id": interview_id,
            "user_id": user_id,
        }
    )

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
