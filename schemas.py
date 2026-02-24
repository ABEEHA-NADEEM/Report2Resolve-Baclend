from pydantic import BaseModel
from typing import Optional, List

class UserCreate(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None
    password: str

class DepartmentSignup(BaseModel):
    full_name: str
    email: str
    password: str
    department_id: str        # which department they belong to

class UserLogin(BaseModel):
    email: str
    password: str

class IssueCreate(BaseModel):
    title: str
    description: str
    category_id: str
    department_id: str
    location_id: str
    user_id: Optional[str] = None
    current_status_id: str
    remarks: str
    images: List[str] = []