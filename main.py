import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson.objectid import ObjectId
from typing import List, Optional

from database import db, create_document, get_documents
from schemas import User, Child, Therapist, Parent, Session, Goal, ProgressNote, Donation, SignupRequest, LoginRequest

from passlib.context import CryptContext

app = FastAPI(title="Therapy Center API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@app.get("/")
def read_root():
    return {"message": "Therapy Center Backend Running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "Unknown"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response


# Utility helpers
class IdModel(BaseModel):
    id: str


def to_obj_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id format")


# Authentication
@app.post("/auth/signup")
def auth_signup(payload: SignupRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    # Check username or email uniqueness
    existing = db["user"].find_one({"$or": [{"username": payload.username}, {"email": payload.email}]})
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already exists")
    password_hash = pwd_context.hash(payload.password)
    user_doc = {
        "name": payload.name,
        "email": payload.email,
        "username": payload.username,
        "password_hash": password_hash,
        "role": payload.role,
        "is_active": True,
    }
    new_id = db["user"].insert_one(user_doc).inserted_id
    return {"id": str(new_id), "name": payload.name, "role": payload.role}


@app.post("/auth/login")
def auth_login(payload: LoginRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    user = db["user"].find_one({"username": payload.username})
    if not user or not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not pwd_context.verify(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Return basic session-less info (no JWT for simplicity)
    return {
        "id": str(user["_id"]),
        "name": user.get("name"),
        "role": user.get("role"),
        "email": user.get("email"),
        "username": user.get("username"),
    }


# Users
@app.post("/users")
def create_user(user: User):
    user_id = create_document("user", user)
    return {"id": user_id}


@app.get("/users")
def list_users(role: Optional[str] = None):
    filt = {"role": role} if role else {}
    users = get_documents("user", filt)
    sanitized = []
    for u in users:
        u["id"] = str(u.pop("_id"))
        u.pop("password_hash", None)
        sanitized.append(u)
    return sanitized


# Children
@app.post("/children")
def create_child(child: Child):
    child_id = create_document("child", child)
    return {"id": child_id}


@app.get("/children")
def list_children(parent_id: Optional[str] = None, therapist_id: Optional[str] = None):
    filt = {}
    if parent_id:
        filt["parent_ids"] = parent_id
    if therapist_id:
        filt["therapist_ids"] = therapist_id
    children = get_documents("child", filt)
    for c in children:
        c["id"] = str(c.pop("_id"))
    return children


# Goals
@app.post("/goals")
def create_goal(goal: Goal):
    goal_id = create_document("goal", goal)
    return {"id": goal_id}


@app.get("/goals")
def list_goals(child_id: str):
    goals = get_documents("goal", {"child_id": child_id})
    for g in goals:
        g["id"] = str(g.pop("_id"))
    return goals


# Sessions
@app.post("/sessions")
def create_session(session: Session):
    session_id = create_document("session", session)
    return {"id": session_id}


@app.get("/sessions")
def list_sessions(child_id: Optional[str] = None, therapist_id: Optional[str] = None):
    filt = {}
    if child_id:
        filt["child_id"] = child_id
    if therapist_id:
        filt["therapist_id"] = therapist_id
    sessions = get_documents("session", filt)
    for s in sessions:
        s["id"] = str(s.pop("_id"))
    return sessions


# Progress notes
@app.post("/progress-notes")
def create_progress_note(note: ProgressNote):
    note_id = create_document("progressnote", note)
    return {"id": note_id}


@app.get("/progress-notes")
def list_progress_notes(child_id: str):
    notes = get_documents("progressnote", {"child_id": child_id})
    for n in notes:
        n["id"] = str(n.pop("_id"))
    return notes


# Donations
@app.post("/donations")
def create_donation(donation: Donation):
    donation_id = create_document("donation", donation)
    return {"id": donation_id}


@app.get("/donations")
def list_donations(child_id: Optional[str] = None, donor_id: Optional[str] = None):
    filt = {}
    if child_id:
        filt["child_id"] = child_id
    if donor_id:
        filt["donor_id"] = donor_id
    donations = get_documents("donation", filt)
    for d in donations:
        d["id"] = str(d.pop("_id"))
    return donations


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
