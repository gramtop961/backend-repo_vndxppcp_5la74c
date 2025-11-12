"""
Database Schemas for Therapy Center App

Each Pydantic model represents a MongoDB collection.
Collection name is the lowercase of the class name.
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, EmailStr

RoleType = Literal["admin", "therapist", "parent", "donor"]

class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    role: RoleType = Field(..., description="User role")
    phone: Optional[str] = Field(None, description="Phone number")
    is_active: bool = Field(True, description="Active user flag")
    username: Optional[str] = Field(None, description="Unique username for login")
    password_hash: Optional[str] = Field(None, description="Hashed password (bcrypt)")

class Parent(BaseModel):
    user_id: str = Field(..., description="Reference to user _id")
    address: Optional[str] = Field(None)

class Therapist(BaseModel):
    user_id: str = Field(..., description="Reference to user _id")
    specialization: Optional[str] = Field(None)
    certifications: Optional[List[str]] = Field(default_factory=list)

class Child(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: Optional[str] = Field(None, description="YYYY-MM-DD")
    parent_ids: List[str] = Field(default_factory=list, description="List of parent user_ids")
    therapist_ids: List[str] = Field(default_factory=list, description="Assigned therapist user_ids")
    diagnosis: Optional[str] = None

class Goal(BaseModel):
    child_id: str = Field(..., description="Reference to child _id")
    title: str
    description: Optional[str] = None
    target_metric: Optional[str] = Field(None, description="e.g., 80% independence")
    status: Literal["active", "paused", "completed"] = "active"

class Session(BaseModel):
    child_id: str
    therapist_id: str
    date: str = Field(..., description="YYYY-MM-DD")
    duration_minutes: int = Field(..., ge=0)
    notes: Optional[str] = None
    goals_progress: Optional[List[dict]] = Field(
        default_factory=list,
        description="List of {goal_id, rating (1-5), comment}"
    )

class ProgressNote(BaseModel):
    child_id: str
    therapist_id: str
    note: str
    visibility: Literal["center", "parents", "therapists", "donors", "public"] = "parents"

class Donation(BaseModel):
    donor_id: Optional[str] = Field(None, description="User id of donor if registered")
    child_id: Optional[str] = Field(None, description="Optional: specific child supported")
    amount: float = Field(..., ge=0)
    message: Optional[str] = None
    date: str = Field(..., description="YYYY-MM-DD")

# Auth auxiliary models (not collections)
class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    username: str
    password: str
    role: RoleType

class LoginRequest(BaseModel):
    username: str
    password: str
