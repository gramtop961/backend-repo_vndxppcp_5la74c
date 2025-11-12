import os
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson.objectid import ObjectId
from typing import List, Optional, Dict, Any

from database import db, create_document, get_documents
from schemas import User, Child, Therapist, Parent, Session, Goal, ProgressNote, Donation, SignupRequest, LoginRequest

from passlib.context import CryptContext

# For PDF generation
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

# For email
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

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
    filt: Dict[str, Any] = {}
    if parent_id:
        # store relation as scalar id in array, so filter directly
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
    filt: Dict[str, Any] = {}
    if child_id:
        filt["child_id"] = child_id
    if therapist_id:
        filt["therapist_id"] = therapist_id
    sessions = get_documents("session", filt)
    for s in sessions:
        s["id"] = str(s.pop("_id"))
    return sessions


class GoalsProgressPayload(BaseModel):
    items: List[Dict[str, Any]]  # list of {goal_id, rating, comment}


@app.patch("/sessions/{session_id}/goals-progress")
def add_goals_progress(session_id: str, payload: GoalsProgressPayload):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    try:
        _id = to_obj_id(session_id)
    except HTTPException:
        raise
    # validate items structure minimally
    items = []
    for it in payload.items:
        if not it.get("goal_id"):
            raise HTTPException(status_code=400, detail="goal_id required")
        rating = it.get("rating")
        if rating is not None and (not isinstance(rating, int) or rating < 1 or rating > 5):
            raise HTTPException(status_code=400, detail="rating must be 1-5")
        items.append({
            "goal_id": it.get("goal_id"),
            "rating": rating,
            "comment": it.get("comment")
        })
    res = db["session"].update_one({"_id": _id}, {"$push": {"goals_progress": {"$each": items}}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"updated": True, "count": len(items)}


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
    filt: Dict[str, Any] = {}
    if child_id:
        filt["child_id"] = child_id
    if donor_id:
        filt["donor_id"] = donor_id
    donations = get_documents("donation", filt)
    for d in donations:
        d["id"] = str(d.pop("_id"))
    return donations


@app.get("/donations/summary")
def donation_summary(child_id: Optional[str] = None, donor_id: Optional[str] = None):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    filt: Dict[str, Any] = {}
    if child_id:
        filt["child_id"] = child_id
    if donor_id:
        filt["donor_id"] = donor_id
    pipeline = [
        {"$match": filt},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
    ]
    agg = list(db["donation"].aggregate(pipeline))
    total = agg[0]["total"] if agg else 0
    count = agg[0]["count"] if agg else 0
    return {"total": total, "count": count}


# Weekly reports
@app.get("/reports/weekly")
def weekly_report(parent_id: str):
    """Return a simple weekly summary for a parent's children: sessions and goals progress counts."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    # find children for this parent
    children = list(db["child"].find({"parent_ids": parent_id}))
    child_ids = [str(c["_id"]) for c in children]
    sessions = list(db["session"].find({"child_id": {"$in": child_ids}}))
    goals = list(db["goal"].find({"child_id": {"$in": child_ids}}))
    # basic aggregation
    report_children = []
    for c in children:
        cid = str(c["_id"])
        csessions = [s for s in sessions if s.get("child_id") == cid]
        cgoals = [g for g in goals if g.get("child_id") == cid]
        progress_items = sum([len(s.get("goals_progress", [])) for s in csessions])
        report_children.append({
            "child_id": cid,
            "name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
            "sessions": len(csessions),
            "goals": len(cgoals),
            "progress_updates": progress_items,
        })
    return {
        "parent_id": parent_id,
        "children": report_children,
        "total_sessions": sum(x["sessions"] for x in report_children),
        "total_progress_updates": sum(x["progress_updates"] for x in report_children),
    }


# Weekly report PDF
@app.get("/reports/weekly.pdf")
def weekly_report_pdf(parent_id: str):
    # Reuse aggregation to get data
    data = weekly_report(parent_id)

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    title = "Weekly Therapy Report"
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, height - 20 * mm, title)

    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, height - 27 * mm, f"Parent ID: {data['parent_id']}")
    c.drawString(20 * mm, height - 32 * mm, f"Total Sessions: {data['total_sessions']}")
    c.drawString(20 * mm, height - 37 * mm, f"Progress Updates: {data['total_progress_updates']}")

    y = height - 50 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Children Summary")
    y -= 6 * mm
    c.setFont("Helvetica", 10)

    for ch in data["children"]:
        if y < 20 * mm:
            c.showPage()
            y = height - 20 * mm
        line = f"- {ch['name']} | Sessions: {ch['sessions']} | Goals: {ch['goals']} | Updates: {ch['progress_updates']}"
        c.drawString(20 * mm, y, line)
        y -= 6 * mm

    c.showPage()
    c.save()
    pdf = buffer.getvalue()
    buffer.close()
    headers = {"Content-Disposition": "inline; filename=weekly_report.pdf"}
    return Response(content=pdf, media_type="application/pdf", headers=headers)


class WeeklyEmailRequest(BaseModel):
    parent_id: str
    to_email: EmailStr


@app.post("/notifications/email/weekly-report")
def email_weekly_report(payload: WeeklyEmailRequest):
    data = weekly_report(payload.parent_id)

    # SMTP configuration from environment
    host = os.getenv("EMAIL_HOST")
    port = int(os.getenv("EMAIL_PORT", "587"))
    user = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    sender = os.getenv("EMAIL_FROM", user or "noreply@example.com")

    if not host or not user or not password:
        raise HTTPException(status_code=501, detail="Email not configured on server")

    # Create email
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = payload.to_email
    msg["Subject"] = "Weekly Therapy Report"

    html_body = f"""
    <h2>Weekly Therapy Report</h2>
    <p>Total Sessions: {data['total_sessions']}</p>
    <p>Total Progress Updates: {data['total_progress_updates']}</p>
    <ul>
        {''.join([f"<li>{ch['name']}: {ch['sessions']} sessions, {ch['goals']} goals, {ch['progress_updates']} updates</li>" for ch in data['children']])}
    </ul>
    """
    msg.attach(MIMEText(html_body, "html"))

    # Attach PDF
    # Generate PDF bytes
    pdf_resp = weekly_report_pdf(payload.parent_id)
    pdf_bytes = pdf_resp.body if hasattr(pdf_resp, 'body') else pdf_resp
    part = MIMEApplication(pdf_bytes, _subtype="pdf")
    part.add_header('Content-Disposition', 'attachment', filename='weekly_report.pdf')
    msg.attach(part)

    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(sender, [payload.to_email], msg.as_string())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)[:200]}")

    return {"sent": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
