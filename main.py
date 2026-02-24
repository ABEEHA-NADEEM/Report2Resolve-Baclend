from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
from dotenv import load_dotenv
import bcrypt
import os
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from schemas import IssueCreate, UserCreate, UserLogin, DepartmentSignup

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

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")

# Hard-coded status IDs from your database
SUBMITTED_STATUS_ID = "85b1cf02-9dde-43e2-82ad-0b3da3fcc6ac"
IN_PROGRESS_STATUS_ID = "88566c51-6593-4085-8486-88ac7fb15e1f"
RESOLVED_STATUS_ID = "b86fdd31-d162-41b0-8dc0-823e7f3596b3"
REJECTED_STATUS_ID = "5ade587e-e51a-4fd1-aa87-411d9268b3a4"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

def send_email(to_emails: list, subject: str, html: str):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = GMAIL_USER
        msg["To"]      = ", ".join(to_emails)
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, to_emails, msg.as_string())

        print(f"✅ Email sent to {to_emails}")
    except Exception as e:
        print(f"❌ Email failed: {e}")


# ─────────────────────────────────────────
@app.get("/")
def home():
    return {"ok": True}


# ─── CITIZEN SIGNUP ───────────────────────────────────────
@app.post("/signup")
def signup(user: UserCreate):
    try:
        existing = supabase.table("app_user").select("user_id").eq("email", user.email).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="Email already registered.")

        role = supabase.table("role").select("role_id").eq("role_name", "citizen").execute()
        if not role.data:
            raise HTTPException(status_code=500, detail="Citizen role not found.")
        role_id = role.data[0]["role_id"]

        hashed = hash_password(user.password)

        res = supabase.table("app_user").insert({
            "full_name":   user.full_name,
            "email":       user.email,
            "phone":       user.phone if user.phone else None,
            "password":    hashed,
            "role_id":     role_id,
            "role_name":   "citizen",
            "is_approved": True,
        }).execute()

        new_user = res.data[0]
        return {
            "ok":      True,
            "user_id": new_user["user_id"],
            "name":    new_user["full_name"],
            "email":   new_user["email"],
            "role":    "citizen",
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Signup error: {e}")
        return {"error": str(e)}


# ─── DEPARTMENT SIGNUP ─────────────────────────────────────
@app.post("/dept-signup")
def dept_signup(user: DepartmentSignup):
    try:
        existing = supabase.table("app_user").select("user_id").eq("email", user.email).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="Email already registered.")

        role = supabase.table("role").select("role_id").eq("role_name", "department").execute()
        if not role.data:
            raise HTTPException(status_code=500, detail="Department role not found.")
        role_id = role.data[0]["role_id"]

        hashed = hash_password(user.password)

        supabase.table("app_user").insert({
            "full_name":     user.full_name,
            "email":         user.email,
            "password":      hashed,
            "role_id":       role_id,
            "role_name":     "department",
            "department_id": user.department_id,
            "is_approved":   False,
        }).execute()

        return {"ok": True, "message": "Signup request sent. Wait for admin approval."}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Dept signup error: {e}")
        return {"error": str(e)}


# ─── UNIFIED LOGIN ─────────────────────────────────────────
@app.post("/login")
def login(user: UserLogin):
    try:
        res = supabase.table("app_user").select("*, role(role_name)").eq("email", user.email).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="No account found with this email.")

        db_user = res.data[0]

        if not verify_password(user.password, db_user["password"]):
            raise HTTPException(status_code=401, detail="Incorrect password.")

        role_name = db_user["role"]["role_name"]
        if role_name == "department" and not db_user["is_approved"]:
            raise HTTPException(status_code=403, detail="Account not approved yet. Contact admin.")

        return {
            "ok":            True,
            "user_id":       db_user["user_id"],
            "name":          db_user["full_name"],
            "email":         db_user["email"],
            "role":          role_name,
            "department_id": db_user.get("department_id"),
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {e}")
        return {"error": str(e)}


# ─── ADMIN: PENDING APPROVALS ──────────────────────────────
@app.get("/admin/pending-approvals")
def pending_approvals():
    try:
        res = supabase.table("app_user").select(
            "user_id, full_name, email, department_id, created_at, role(role_name)"
        ).eq("is_approved", False).execute()
        return res.data
    except Exception as e:
        print(f"Pending approvals error: {e}")
        return {"error": str(e)}


# ─── ADMIN: APPROVE ────────────────────────────────────────
@app.post("/admin/approve/{user_id}")
def approve_user(user_id: str):
    try:
        supabase.table("app_user").update(
            {"is_approved": True}
        ).eq("user_id", user_id).execute()
        return {"ok": True, "message": "User approved."}
    except Exception as e:
        print(f"Approve error: {e}")
        return {"error": str(e)}


# ─── ADMIN: REJECT ─────────────────────────────────────────
@app.delete("/admin/reject/{user_id}")
def reject_user(user_id: str):
    try:
        supabase.table("app_user").delete().eq("user_id", user_id).execute()
        return {"ok": True, "message": "User rejected and removed."}
    except Exception as e:
        print(f"Reject error: {e}")
        return {"error": str(e)}


# ─── ADMIN: ALL ISSUES ─────────────────────────────────────
@app.get("/admin/all-issues")
def all_issues():
    try:
        res = supabase.table("issue").select(
            "issue_id, title, description, created_at, user_id, current_status_id"
        ).order("created_at", desc=True).execute()
        
        issues = res.data
        
        # Manually fetch status for each issue
        for issue in issues:
            if issue.get("current_status_id"):
                status_res = supabase.table("issue_status").select(
                    "status_name"
                ).eq("status_id", issue["current_status_id"]).execute()
                
                if status_res.data:
                    issue["issue_status"] = {"status_name": status_res.data[0]["status_name"]}
                else:
                    issue["issue_status"] = {"status_name": "Unknown"}
            else:
                issue["issue_status"] = {"status_name": "Unknown"}
        
        return issues
        
    except Exception as e:
        print(f"Admin all issues error: {e}")
        return {"error": str(e)}


# ─── CITIZEN: GET MY ISSUES ────────────────────────────────
@app.get("/my-issues/{user_id}")
def my_issues(user_id: str):
    try:
        print(f"📥 Fetching issues for user_id: {user_id}")
        
        res = supabase.table("issue").select(
            "issue_id, title, description, created_at, current_status_id"
        ).eq("user_id", user_id).order("created_at", desc=True).execute()
        
        print(f"✅ Found {len(res.data)} issues")
        
        issues = res.data
        
        # Manually fetch status for each issue
        for issue in issues:
            if issue.get("current_status_id"):
                status_res = supabase.table("issue_status").select(
                    "status_name"
                ).eq("status_id", issue["current_status_id"]).execute()
                
                if status_res.data:
                    status_name = status_res.data[0]["status_name"]
                    issue["issue_status"] = {"status_name": status_name}
                    print(f"  Issue '{issue['title']}' → Status: {status_name}")
                else:
                    issue["issue_status"] = {"status_name": "Unknown"}
                    print(f"  Issue '{issue['title']}' → Status: Unknown (no match)")
            else:
                issue["issue_status"] = {"status_name": "Unknown"}
                print(f"  Issue '{issue['title']}' → No current_status_id")
        
        return issues
        
    except Exception as e:
        print(f"❌ My issues error: {e}")
        return {"error": str(e)}


# ─── DEPARTMENT: GET ISSUES BY TAB ─────────────────────────
@app.get("/dept/issues/{department_id}")
def dept_issues(department_id: str, tab: str = "active"):
    try:
        print(f"📥 Fetching issues for department: {department_id}, tab: {tab}")

        query = supabase.table("issue").select(
            "issue_id, title, description, created_at, user_id, current_status_id"
        ).eq("department_id", department_id)

        if tab == "resolved":
            query = query.eq("current_status_id", RESOLVED_STATUS_ID)
        elif tab == "rejected":
            query = query.eq("current_status_id", REJECTED_STATUS_ID)
        else:
            # Active = everything except resolved and rejected
            query = query.not_.in_("current_status_id", [RESOLVED_STATUS_ID, REJECTED_STATUS_ID])

        res = query.order("created_at", desc=True).execute()
        
        issues = res.data
        
        # Manually fetch status for each issue
        for issue in issues:
            if issue.get("current_status_id"):
                status_res = supabase.table("issue_status").select(
                    "status_name"
                ).eq("status_id", issue["current_status_id"]).execute()
                
                if status_res.data:
                    issue["issue_status"] = {"status_name": status_res.data[0]["status_name"]}
                else:
                    issue["issue_status"] = {"status_name": "Unknown"}
            else:
                issue["issue_status"] = {"status_name": "Unknown"}
        
        print(f"✅ Returning {len(issues)} issues for tab '{tab}'")
        return issues

    except Exception as e:
        print(f"❌ Dept issues error: {e}")
        return {"error": str(e)}


# ─── DEPARTMENT: UPDATE ISSUE STATUS ──────────────────────
@app.post("/dept/update-status/{issue_id}")
def update_issue_status(issue_id: str, body: dict):
    try:
        print(f"📝 Updating issue {issue_id} to status_id: {body['status_id']}")
        
        supabase.table("issue").update({
            "current_status_id": body["status_id"],
        }).eq("issue_id", issue_id).execute()

        supabase.table("issue_history").insert({
            "issue_id":   issue_id,
            "status_id":  body["status_id"],
            "updated_by": body.get("updated_by"),
            "remarks":    body.get("remarks", "Status updated by department"),
        }).execute()

        # ── Email citizen about status update ──
        try:
            issue_row = supabase.table("issue").select(
                "title, user_id"
            ).eq("issue_id", issue_id).execute()

            if issue_row.data and issue_row.data[0]["user_id"]:
                citizen = supabase.table("app_user").select(
                    "email, full_name"
                ).eq("user_id", issue_row.data[0]["user_id"]).execute()

                if citizen.data:
                    status_row = supabase.table("issue_status").select(
                        "status_name"
                    ).eq("status_id", body["status_id"]).execute()

                    status_name   = status_row.data[0]["status_name"] if status_row.data else "Updated"
                    citizen_email = citizen.data[0]["email"]
                    citizen_name  = citizen.data[0]["full_name"]
                    issue_title   = issue_row.data[0]["title"]

                    html = f"""
                        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                            <h2 style="color: #3b82f6;">📋 Issue Status Updated</h2>
                            <p>Hi <strong>{citizen_name}</strong>,</p>
                            <p>Your issue <strong>"{issue_title}"</strong> has been updated to <strong>{status_name}</strong>.</p>
                            <br/>
                            <a href="http://localhost:3000/dashboard"
                               style="background:#3b82f6; color:white; padding:10px 24px;
                                      text-decoration:none; border-radius:6px; display:inline-block;">
                                View Dashboard →
                            </a>
                            <br/><br/>
                            <small style="color:#999;">Report2Resolve — Civic Issue Reporting System</small>
                        </div>
                    """
                    send_email([citizen_email], f"Issue Update: {issue_title}", html)
        except Exception as notify_err:
            print(f"Citizen notify error: {notify_err}")

        print(f"✅ Issue {issue_id} updated successfully")
        return {"ok": True}

    except Exception as e:
        print(f"❌ Update status error: {e}")
        return {"error": str(e)}


# ─── GET ALL STATUSES ──────────────────────────────────────
@app.get("/statuses")
def get_statuses():
    try:
        res = supabase.table("issue_status").select("status_id, status_name").execute()
        return res.data
    except Exception as e:
        print(f"Get statuses error: {e}")
        return {"error": str(e)}


# ─── CATEGORIES & DEPARTMENTS ──────────────────────────────
@app.get("/categories")
def get_categories():
    try:
        res = supabase.table("categories").select("category_id, category_name").execute()
        return res.data
    except Exception as e:
        print(f"Get categories error: {e}")
        return {"error": str(e)}

@app.get("/departments")
def get_departments():
    try:
        res = supabase.table("departments").select("department_id, department_name").execute()
        return res.data
    except Exception as e:
        print(f"Get departments error: {e}")
        return {"error": str(e)}


# ─── UPLOAD IMAGE ──────────────────────────────────────────
@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        file_name  = f"{uuid.uuid4()}-{file.filename}"
        supabase.storage.from_("issue-images").upload(
            file_name, file_bytes, {"content-type": file.content_type}
        )
        public_url = supabase.storage.from_("issue-images").get_public_url(file_name)
        return {"url": public_url}
    except Exception as e:
        print(f"Upload image error: {e}")
        return {"error": str(e)}


# ─── CREATE ISSUE (ALWAYS STARTS AS "SUBMITTED") ──────────────────────────────────────
@app.post("/create-issue")
def create_issue(issue: IssueCreate):
    try:
        print(f"📝 Creating new issue: {issue.title}")
        print(f"🔵 Setting initial status to: Submitted ({SUBMITTED_STATUS_ID})")
        
        # ALWAYS use "Submitted" status for new issues
        issue_data = supabase.table("issue").insert({
            "title":             issue.title,
            "description":       issue.description,
            "category_id":       issue.category_id,
            "department_id":     issue.department_id,
            "location_id":       issue.location_id,
            "user_id":           issue.user_id,
            "current_status_id": SUBMITTED_STATUS_ID,  # 🔥 ALWAYS "Submitted"
        }).execute()

        issue_id = issue_data.data[0]["issue_id"]

        # Record in history with "Submitted" status
        supabase.table("issue_history").insert({
            "issue_id":   issue_id,
            "status_id":  SUBMITTED_STATUS_ID,  # 🔥 ALWAYS "Submitted"
            "updated_by": None,
            "remarks":    "Issue submitted by citizen",
        }).execute()

        # Save images
        for img_url in issue.images:
            supabase.table("issue_image").insert({
                "issue_id":  issue_id,
                "image_url": img_url,
            }).execute()

        # ── Send Email to Department ──
        try:
            dept = supabase.table("departments").select(
                "department_name, contact_email"
            ).eq("department_id", issue.department_id).execute()

            dept_name  = dept.data[0]["department_name"]
            dept_email = dept.data[0]["contact_email"]

            staff = supabase.table("app_user").select(
                "email"
            ).eq("department_id", issue.department_id).eq("is_approved", True).execute()

            recipients = [dept_email]
            for s in staff.data:
                if s["email"] not in recipients:
                    recipients.append(s["email"])

            if issue.user_id:
                citizen_res = supabase.table("app_user").select(
                    "full_name, email"
                ).eq("user_id", issue.user_id).execute()
                if citizen_res.data:
                    submitter_label = f"{citizen_res.data[0]['full_name']} ({citizen_res.data[0]['email']})"
                else:
                    submitter_label = "Registered User"
            else:
                submitter_label = "Guest (not logged in)"

            html = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #3b82f6;">🔔 New Issue Reported</h2>
                    <p>A new issue has been assigned to <strong>{dept_name}</strong>.</p>

                    <table style="width:100%; border-collapse:collapse; margin-top:10px;">
                        <tr style="background:#f0f4ff;">
                            <td style="padding:10px; border:1px solid #ddd; width:30%"><strong>Submitted By</strong></td>
                            <td style="padding:10px; border:1px solid #ddd;">{submitter_label}</td>
                        </tr>
                        <tr>
                            <td style="padding:10px; border:1px solid #ddd;"><strong>Title</strong></td>
                            <td style="padding:10px; border:1px solid #ddd;">{issue.title}</td>
                        </tr>
                        <tr style="background:#f0f4ff;">
                            <td style="padding:10px; border:1px solid #ddd;"><strong>Description</strong></td>
                            <td style="padding:10px; border:1px solid #ddd;">{issue.description}</td>
                        </tr>
                    </table>

                    <br/>
                    <p>Please login to your department portal to view and update this issue.</p>
                    <a href="http://localhost:3000/auth"
                       style="background:#3b82f6; color:white; padding:10px 24px;
                              text-decoration:none; border-radius:6px; display:inline-block;">
                        View Issue →
                    </a>
                    <br/><br/>
                    <small style="color:#999;">Report2Resolve — Civic Issue Reporting System</small>
                </div>
            """

            send_email(recipients, f"New Issue: {issue.title}", html)

        except Exception as email_err:
            print(f"Email error: {email_err}")

        print(f"✅ Issue created successfully with 'Submitted' status: {issue_id}")
        return {"ok": True, "issue_id": issue_id}

    except Exception as e:
        print(f"❌ Create issue error: {e}")
        return {"error": str(e)}