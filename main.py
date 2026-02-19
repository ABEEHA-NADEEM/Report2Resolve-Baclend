from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
from dotenv import load_dotenv
import os
import uuid
from schemas import IssueCreate

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)


@app.get("/")
def home():
    return {"ok": True}


@app.get("/categories")
def get_categories():
    res = supabase.table("categories").select("category_id, category_name").execute()
    return res.data


@app.get("/departments")
def get_departments():
    res = supabase.table("departments").select("department_id, department_name").execute()
    return res.data


@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        file_name  = f"{uuid.uuid4()}-{file.filename}"
        supabase.storage.from_("issue-images").upload(
            file_name,
            file_bytes,
            {"content-type": file.content_type}
        )
        public_url = supabase.storage.from_("issue-images").get_public_url(file_name)
        return {"url": public_url}
    except Exception as e:
        return {"error": str(e)}


@app.post("/create-issue")
def create_issue(issue: IssueCreate):
    try:
        issue_data = supabase.table("issue").insert({
            "title":             issue.title,
            "description":       issue.description,
            "category_id":       issue.category_id,
            "department_id":     issue.department_id,
            "location_id":       issue.location_id,
            "user_id":           issue.user_id,
            "current_status_id": issue.current_status_id,
        }).execute()

        issue_id = issue_data.data[0]["issue_id"]

        supabase.table("issue_history").insert({
            "issue_id":   issue_id,
            "status_id":  issue.current_status_id,
            "updated_by": None,
            "remarks":    issue.remarks,
        }).execute()

        for img_url in issue.images:
            supabase.table("issue_image").insert({
                "issue_id":  issue_id,
                "image_url": img_url,
            }).execute()

        return {"ok": True, "issue_id": issue_id}

    except Exception as e:
        return {"error": str(e)}