from pydantic import BaseModel
from typing import Optional, List

class IssueCreate(BaseModel):
    title: str
    description: str           # ✅ correct field name from your DB
    category_id: str           # references categories(category_id)
    department_id: str         # ✅ was missing — required in your DB
    location_id: str           # references location(location_id)
    user_id: Optional[str] = None   # null for guest
    current_status_id: str     # references issue_status(status_id)
    remarks: str               # goes to issue_history, not issue table
    images: List[str] = []     # goes to issue_image table