import os
import re
from datetime import datetime
from fastapi import FastAPI, Request, Header
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow.utils._workflow_hitl_utils import (
    create_request_input_response,
    has_request_input_function_call,
    get_request_input_interrupt_ids,
)
from google.genai import types

from app.agent import root_agent
from app.config import HORMONE_ACTIVITIES
from app.database import (
    register_user,
    authenticate_user,
    save_daily_log,
    save_coach_note,
    get_user_logs,
    verify_coach_credentials,
    get_user_email,
    get_user_by_email
)

app = FastAPI(title="Peri-Meter AI - Hormonal Balance Motivator")

# Initialize ADK runtime services
session_service = InMemorySessionService()
runner = Runner(agent=root_agent, session_service=session_service, app_name="perimeter_agent")

# In-memory store for UI to track active agent runs
active_sessions = {}
pending_reviews = {}

class SubmitQuizPayload(BaseModel):
    user_id: int
    name: str
    age: int
    gender: str
    perimenopause_status: str
    answers: dict[str, list[str]]
    date: str = None

class CoachReviewPayload(BaseModel):
    coach_note: str

class RegisterPayload(BaseModel):
    username: str
    password: str
    email: str
    name: str
    age: int
    gender: str
    perimenopause_status: str

class LoginPayload(BaseModel):
    username: str
    password: str

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    # Renders the HTML template containing the UI and Coach Portal
    return HTMLResponse(content=INDEX_HTML_TEMPLATE)

class ForgotPasswordPayload(BaseModel):
    email: str

@app.post("/api/auth/register")
async def handle_register(payload: RegisterPayload):
    # Validation rules
    # Username: Max 8 characters
    if len(payload.username) > 8:
        return JSONResponse(status_code=400, content={"error": "Username must be at most 8 characters long."})
    
    # Password: 8 characters, combination of alphabets, numbers, and special characters !, @, # only
    password_pattern = r"^(?=.*[a-zA-Z])(?=.*[0-9])(?=.*[!@#])[a-zA-Z0-9!@#]{8}$"
    if not re.match(password_pattern, payload.password):
        return JSONResponse(status_code=400, content={"error": "Password must be exactly 8 characters long, containing a combination of alphabets, numbers, and only !, @, # as special characters."})

    res = register_user(
        username=payload.username,
        password=payload.password,
        email=payload.email,
        name=payload.name,
        age=payload.age,
        gender=payload.gender,
        perimenopause_status=payload.perimenopause_status
    )
    if res["success"]:
        return JSONResponse(content={"success": True, "user_id": res["user_id"]})
    return JSONResponse(status_code=400, content={"error": res["error"]})

@app.post("/api/auth/login")
async def handle_login(payload: LoginPayload):
    res = authenticate_user(payload.username, payload.password)
    if res["success"]:
        return JSONResponse(content={"success": True, "user": res["user"]})
    return JSONResponse(status_code=400, content={"error": res["error"]})

@app.post("/api/auth/forgot-password")
async def handle_forgot_password(payload: ForgotPasswordPayload):
    user = get_user_by_email(payload.email)
    if not user:
        return JSONResponse(status_code=400, content={"error": "Email not found."})
    
    # Simulate sending email
    email_body = f"""Hi {user['username']},

Here are your Peri-Meter AI login credentials:
Username: {user['username']}
Password: {user['password']}

Please log in using these details.

Be well,
The Peri-Meter AI Team"""
    
    # Save/log the email
    log_file_path = os.path.join(os.path.dirname(__file__), "email_logs.txt")
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write("========================================\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"To: {user['email']}\n")
        f.write("Subject: Your Peri-Meter AI Login Credentials\n")
        f.write("----------------------------------------\n")
        f.write(email_body + "\n")
        f.write("========================================\n\n")
        
    print(f"EMAIL SENT TO {user['email']} containing credentials.")
    return JSONResponse(content={"success": True})

@app.get("/api/logs")
async def handle_get_logs(user_id: int):
    logs = get_user_logs(user_id)
    return JSONResponse(content=logs)

@app.get("/api/hormones")
async def get_hormone_questions():
    # Helper to return the quiz configuration to the frontend
    questions_data = {}
    for hormone, data in HORMONE_ACTIVITIES.items():
        questions_data[hormone] = {
            "question": data["question"],
            "options": [opt["text"] for opt in data["options"]]
        }
    return JSONResponse(content=questions_data)

@app.post("/api/submit")
async def submit_quiz(payload: SubmitQuizPayload):
    try:
        user_id = payload.user_id
        # Create a new session
        session = session_service.create_session_sync(user_id="user_uid", app_name="perimeter_agent")
        session_id = session.id
        
        user_message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=payload.model_dump_json())]
        )
        
        # Run ADK workflow
        events = list(
            runner.run(
                new_message=user_message,
                user_id="user_uid",
                session_id=session_id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )
        
        # Check for HITL Interruption
        interrupted = False
        interrupt_id = None
        for event in events:
            if has_request_input_function_call(event):
                interrupted = True
                ids = get_request_input_interrupt_ids(event)
                if ids:
                    interrupt_id = ids[0]
                    break
        
        # Extract date from payload, default to today
        date_str = payload.date if payload.date else datetime.now().strftime("%Y-%m-%d")

        if interrupted and interrupt_id:
            # Workflow is suspended waiting for coach input
            pending_reviews[session_id] = {
                "session_id": session_id,
                "user_id": user_id,
                "name": payload.name,
                "age": payload.age,
                "gender": payload.gender,
                "interrupt_id": interrupt_id,
                "answers": payload.answers,
                "date": date_str
            }
            active_sessions[session_id] = {"status": "pending_coach_review"}
            return JSONResponse(content={
                "status": "pending_coach_review",
                "session_id": session_id,
                "message": "Your score is under 50. A Health Coach will review your report shortly to provide personalized encouragement!"
            })
            
        # If not interrupted, it completed (either ineligible or score >= 50)
        final_report = None
        for event in reversed(events):
            if event.output and isinstance(event.output, dict) and "score" in event.output:
                final_report = event.output
                break
                
        if final_report:
            final_report["date"] = date_str
            active_sessions[session_id] = {
                "status": "completed",
                "data": final_report
            }
            
            # Save daily log to database
            if final_report.get("eligible", False):
                save_daily_log(
                    user_id=user_id,
                    date=date_str,
                    score=final_report["score"],
                    answers=payload.answers,
                    jokes=final_report["jokes"],
                    girl_talk=final_report["girl_talk"]
                )
            
            return JSONResponse(content={
                "status": "completed",
                "session_id": session_id,
                "data": final_report
            })
            
        return JSONResponse(status_code=500, content={"error": "Workflow did not return a valid report"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/status/{session_id}")
async def get_session_status(session_id: str):
    if session_id in active_sessions:
        return JSONResponse(content=active_sessions[session_id])
    return JSONResponse(status_code=404, content={"error": "Session not found"})

def send_email_alert(to_email: str, user_name: str, coach_note: str):
    subject = "Your Peri-Meter AI Health Coach Review is Ready!"
    body = (
        f"Hi {user_name},\n\n"
        f"Your health coach has reviewed your daily wellness activities and left the following encouragement:\n\n"
        f"\"{coach_note}\"\n\n"
        f"Please log in to the Peri-Meter AI portal to view your score, daily wellness suggestions, and calendar update.\n\n"
        f"Be well,\n"
        f"The Peri-Meter AI Team"
    )
    log_entry = (
        f"========================================\n"
        f"Timestamp: {datetime.now().isoformat()}\n"
        f"To: {to_email}\n"
        f"Subject: {subject}\n"
        f"----------------------------------------\n"
        f"{body}\n"
        f"========================================\n\n"
    )
    # Print to console
    print(f"EMAIL SENT TO {to_email}:\n{log_entry}")
    
    # Save to file
    log_path = os.path.join(os.path.dirname(__file__), "email_logs.txt")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(log_entry)

@app.get("/api/pending")
async def get_pending_reviews(
    x_coach_username: str = Header(None),
    x_coach_password: str = Header(None)
):
    if not x_coach_username or not x_coach_password or not verify_coach_credentials(x_coach_username, x_coach_password):
        return JSONResponse(status_code=403, content={"error": "Forbidden: Health coach access required."})
    return JSONResponse(content=list(pending_reviews.values()))

@app.post("/api/coach-review/{session_id}")
async def submit_coach_review(
    session_id: str,
    payload: CoachReviewPayload,
    x_coach_username: str = Header(None),
    x_coach_password: str = Header(None)
):
    if not x_coach_username or not x_coach_password or not verify_coach_credentials(x_coach_username, x_coach_password):
        return JSONResponse(status_code=403, content={"error": "Forbidden: Health coach access required."})
        
    if session_id not in pending_reviews:
        return JSONResponse(status_code=404, content={"error": "Session review not found"})
        
    review_info = pending_reviews[session_id]
    interrupt_id = review_info["interrupt_id"]
    user_id = review_info["user_id"]
    
    try:
        # Create resume response message using coach note
        response_part = create_request_input_response(interrupt_id, {"coach_note": payload.coach_note})
        resume_message = types.Content(role="user", parts=[response_part])
        
        # Resume run
        events = list(
            runner.run(
                new_message=resume_message,
                user_id="user_uid",
                session_id=session_id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )
        
        # Extract date from the review session info (supports yesterday logging)
        date_str = review_info.get("date", datetime.now().strftime("%Y-%m-%d"))

        # Clean up from pending list
        pending_reviews.pop(session_id)
        
        # Extract finalized report by searching backwards and verifying 'score' is present
        final_report = None
        for event in reversed(events):
            if event.output and isinstance(event.output, dict) and "score" in event.output:
                final_report = event.output
                break
                
        if final_report:
            active_sessions[session_id] = {
                "status": "completed",
                "data": final_report
            }
            
            # Save daily log and coach note to database
            save_daily_log(
                user_id=user_id,
                date=date_str,
                score=final_report["score"],
                answers=review_info["answers"],
                jokes=final_report["jokes"],
                girl_talk=final_report["girl_talk"]
            )
            save_coach_note(user_id, date_str, payload.coach_note)
            
            # Send email alert to user
            user_email = get_user_email(user_id)
            if user_email:
                send_email_alert(user_email, review_info["name"], payload.coach_note)
            
            return JSONResponse(content={
                "status": "completed",
                "session_id": session_id,
                "data": final_report
            })
            
        return JSONResponse(status_code=500, content={"error": "Failed to resume and finalize report"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/status/{session_id}")
async def get_session_status(session_id: str):
    if session_id not in active_sessions:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    return JSONResponse(content=active_sessions[session_id])

# ----------------- HTML & CSS Pastel Template -----------------
INDEX_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Peri-Meter AI - Hormonal Balance Motivator</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-lavender: #f5f3ff;
            --card-peach: #fff7ed;
            --accent-mint: #f0fdf4;
            --accent-mint-hover: #dcfce7;
            --mint-text: #166534;
            --accent-rose: #fff1f2;
            --accent-rose-hover: #ffe4e6;
            --rose-text: #9f1239;
            --text-dark: #374151;
            --text-muted: #6b7280;
            --pastel-purple: #c084fc;
            --pastel-orange: #fb923c;
            --pastel-green: #4ade80;
            --pastel-red: #f87171;
            --font-family: 'Outfit', sans-serif;
        }

        body {
            font-family: var(--font-family);
            background-color: var(--bg-lavender);
            color: var(--text-dark);
            margin: 0;
            padding: 0;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        header {
            width: 100%;
            background: linear-gradient(135deg, #fdfbf7, #f5f3ff);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            padding: 1.5rem 0;
            text-align: center;
            border-bottom: 2px solid #e9d5ff;
            position: relative;
        }

        header h1 {
            margin: 0;
            font-weight: 700;
            font-size: 2.2rem;
            background: linear-gradient(45deg, #a855f7, #f97316);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        header p {
            margin: 0.2rem 0 0 0;
            color: var(--text-muted);
            font-weight: 400;
        }

        .user-profile-badge {
            position: absolute;
            right: 2rem;
            top: 50%;
            transform: translateY(-50%);
            display: flex;
            align-items: center;
            gap: 1rem;
            background: rgba(255, 255, 255, 0.8);
            padding: 0.5rem 1rem;
            border-radius: 9999px;
            border: 1px solid #e9d5ff;
            font-size: 0.95rem;
            font-weight: 500;
        }

        main {
            max-width: 900px;
            width: 95%;
            margin: 2rem 0;
            display: flex;
            flex-direction: column;
            gap: 2rem;
        }

        .card {
            background-color: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border: 2px solid rgba(255, 255, 255, 0.5);
            border-radius: 1.5rem;
            padding: 2.5rem;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.03), 0 4px 6px -2px rgba(0, 0, 0, 0.02);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }

        h2 {
            margin-top: 0;
            font-weight: 600;
            color: #4b5563;
        }

        .form-group {
            margin-bottom: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }

        label {
            font-weight: 500;
            font-size: 1.1rem;
            color: #4b5563;
        }

        input[type="text"], input[type="number"], input[type="password"], select {
            font-family: var(--font-family);
            padding: 0.8rem 1.2rem;
            border-radius: 0.75rem;
            border: 2px solid #e9d5ff;
            background-color: #fff;
            font-size: 1rem;
            outline: none;
            transition: border-color 0.2s;
        }

        input[type="text"]:focus, input[type="number"]:focus, input[type="password"]:focus, select:focus {
            border-color: var(--pastel-purple);
        }

        .btn {
            font-family: var(--font-family);
            cursor: pointer;
            padding: 0.8rem 1.8rem;
            border-radius: 0.75rem;
            border: none;
            font-weight: 600;
            font-size: 1.1rem;
            transition: all 0.2s ease;
        }

        .btn-primary {
            background-color: #e9d5ff;
            color: #6b21a8;
            border: 2px solid #d8b4fe;
        }

        .btn-secondary {
            background-color: var(--card-peach);
            color: #c2410c;
            border: 2px solid #ffedd5;
        }

        .hormone-section {
            margin-bottom: 2rem;
            border-bottom: 1px solid #f3e8ff;
            padding-bottom: 1.5rem;
        }

        .hormone-title {
            font-weight: 600;
            font-size: 1.2rem;
            color: #5b21b6;
            margin-bottom: 0.8rem;
        }

        .checkbox-options {
            display: flex;
            flex-direction: column;
            gap: 0.6rem;
        }

        .checkbox-label {
            display: flex;
            align-items: center;
            gap: 0.8rem;
            padding: 0.8rem 1.2rem;
            background-color: var(--card-peach);
            border: 2px solid #ffedd5;
            border-radius: 0.75rem;
            cursor: pointer;
            transition: all 0.2s;
        }

        .checkbox-label:hover {
            background-color: #fff7ed;
            border-color: #fed7aa;
        }

        .checkbox-label input[type="checkbox"] {
            width: 1.2rem;
            height: 1.2rem;
            accent-color: var(--pastel-orange);
        }

        .checkbox-label.selected {
            background-color: #ffedd5;
            border-color: var(--pastel-orange);
        }

        .score-badge {
            display: inline-block;
            padding: 0.5rem 1.5rem;
            border-radius: 9999px;
            font-weight: 700;
            font-size: 1.5rem;
            margin-bottom: 1rem;
        }

        .score-pass {
            background-color: var(--accent-mint);
            color: var(--mint-text);
            border: 2px solid #bbf7d0;
        }

        .score-fail {
            background-color: var(--accent-rose);
            color: var(--rose-text);
            border: 2px solid #fecdd3;
        }

        .calendar-container {
            margin-top: 2rem;
            background: rgba(255, 255, 255, 0.9);
            padding: 2rem;
            border-radius: 1rem;
            border: 1px solid #e9d5ff;
        }

        .calendar-grid {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 0.5rem;
            margin-top: 1rem;
        }

        .calendar-day-header {
            text-align: center;
            font-weight: 600;
            color: var(--text-muted);
            padding: 0.5rem 0;
            font-size: 0.9rem;
        }

        .calendar-cell {
            background-color: rgba(255, 255, 255, 0.5);
            border: 1px solid rgba(233, 213, 255, 0.5);
            border-radius: 0.5rem;
            min-height: 4.5rem;
            padding: 0.3rem;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            align-items: flex-start;
        }

        .calendar-cell.blank {
            background-color: transparent;
            border: none;
        }

        .date-num {
            font-weight: 500;
            font-size: 0.95rem;
            color: var(--text-dark);
        }

        .score-indicator {
            align-self: center;
            font-size: 0.85rem;
            font-weight: 700;
            padding: 0.2rem 0.5rem;
            border-radius: 0.25rem;
            width: 80%;
            text-align: center;
            margin-top: 0.3rem;
        }

        .score-indicator.high {
            background-color: #dcfce7;
            color: #166534;
        }

        .score-indicator.low {
            background-color: #ffe4e6;
            color: #9f1239;
        }

        .auth-container {
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }

        .auth-toggle {
            display: flex;
            justify-content: center;
            gap: 2rem;
            margin-bottom: 2rem;
        }

        .auth-toggle a {
            cursor: pointer;
            color: var(--text-muted);
            font-weight: 600;
            font-size: 1.2rem;
            text-decoration: none;
            padding-bottom: 0.3rem;
            border-bottom: 3px solid transparent;
            transition: all 0.2s;
        }

        .auth-toggle a.active {
            color: #6b21a8;
            border-bottom-color: #6b21a8;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
        }

        th, td {
            text-align: left;
            padding: 0.8rem;
            border-bottom: 1px solid #e9d5ff;
        }

        .textarea-coach {
            font-family: var(--font-family);
            width: 100%;
            padding: 0.8rem;
            border-radius: 0.5rem;
            border: 2px solid #e9d5ff;
        }

        .tab-buttons {
            display: flex;
            gap: 1rem;
            margin-bottom: 1rem;
        }

        .tab-btn {
            background: none;
            border: none;
            padding: 0.5rem 1.2rem;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            border-bottom: 3px solid transparent;
            color: var(--text-muted);
        }

        .tab-btn.active {
            border-bottom-color: var(--pastel-purple);
            color: #6b21a8;
        }

        .hidden {
            display: none !important;
        }

        .spinner {
            border: 4px solid rgba(0, 0, 0, 0.1);
            width: 36px;
            height: 36px;
            border-radius: 50%;
            border-left-color: var(--pastel-purple);
            animation: spin 1s linear infinite;
            margin: 2rem auto;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .error-banner {
            background-color: var(--accent-rose);
            color: var(--rose-text);
            border: 2px solid #ffe4e6;
            padding: 1.5rem;
            border-radius: 1rem;
            margin-top: 1.5rem;
            font-weight: 500;
        }
    </style>
</head>
<body>

    <header>
        <h1>Peri-Meter AI</h1>
        <p>Your Gentle Guide to Daily Hormonal Balance • Agents for Good</p>
        <div id="user-header-badge" class="user-profile-badge hidden">
            <span id="user-display-name">Guest</span>
            <button class="btn btn-secondary" onclick="handleLogout()" style="padding: 0.2rem 0.8rem; font-size: 0.85rem; border-radius: 0.5rem;">Logout</button>
        </div>
    </header>

    <main>
        <div class="tab-buttons" style="display: none;">
            <button class="tab-btn active" id="tab-app" onclick="switchTab('app')">Motivator App</button>
            <button class="tab-btn" id="tab-portal" onclick="switchTab('portal')">Health Coach Portal</button>
        </div>

        <section id="section-auth" class="card">
            <div class="auth-toggle">
                <a id="toggle-login" class="active" onclick="switchAuthTab('login')">Login</a>
                <a id="toggle-register" onclick="switchAuthTab('register')">Register & Onboard</a>
            </div>
            
            <div id="login-form" class="auth-container">
                <h2>Login to Peri-Meter AI</h2>
                <div class="form-group">
                    <label for="login-username">Username</label>
                    <input type="text" id="login-username" placeholder="Enter username">
                </div>
                <div class="form-group">
                    <label for="login-password">Password</label>
                    <input type="password" id="login-password" placeholder="Enter password">
                </div>
                <div id="login-error-banner" class="error-banner hidden"></div>
                <button class="btn btn-primary" onclick="handleLogin()" style="margin-top: 1rem;">Login</button>
                <div style="margin-top: 1.5rem; text-align: right;">
                    <a href="#" onclick="showForgotPassword(event)" style="color: var(--color-primary); font-size: 0.9rem; text-decoration: underline;">Forgot Username/Password?</a>
                </div>
            </div>

            <div id="forgot-form" class="auth-container hidden">
                <h2>Retrieve Username/Password</h2>
                <p style="color: var(--text-muted); margin-bottom: 1.5rem;">
                    Enter the email address registered with your account. We will send you an email with your login details.
                </p>
                <div class="form-group">
                    <label for="forgot-email">Email Address</label>
                    <input type="email" id="forgot-email" placeholder="Enter email address">
                </div>
                <div id="forgot-message-banner" class="error-banner hidden" style="background-color: #f0fdf4; color: #166534; border-color: #bbf7d0;"></div>
                <div id="forgot-error-banner" class="error-banner hidden"></div>
                <div style="display: flex; gap: 1rem; margin-top: 1rem;">
                    <button class="btn btn-primary" onclick="handleForgotPassword()">Send Credentials</button>
                    <button class="btn btn-secondary" onclick="switchAuthTab('login')">Cancel</button>
                </div>
            </div>
            
            <div id="register-form" class="auth-container hidden">
                <h2>Create Wellness Account</h2>
                <div class="form-group">
                    <label for="reg-username">Username</label>
                    <input type="text" id="reg-username" placeholder="Choose a username">
                </div>
                <div class="form-group">
                    <label for="reg-password">Password</label>
                    <input type="password" id="reg-password" placeholder="Choose a password">
                </div>
                <div class="form-group">
                    <label for="reg-email">Email Address</label>
                    <input type="email" id="reg-email" placeholder="Enter email address">
                </div>
                <div class="form-group">
                    <label for="reg-name">What is your name?</label>
                    <input type="text" id="reg-name" placeholder="Enter your name">
                </div>
                <div class="form-group">
                    <label for="reg-age">What is your age?</label>
                    <input type="number" id="reg-age" min="0" placeholder="Enter your age">
                </div>
                <div class="form-group">
                    <label for="reg-gender">What is your gender?</label>
                    <select id="reg-gender">
                        <option value="female">Female</option>
                        <option value="male">Male</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="reg-perimenopause_status">Are you experiencing symptoms of perimenopause?</label>
                    <select id="reg-perimenopause_status">
                        <option value="yes">Yes, currently experiencing symptoms</option>
                        <option value="no">No</option>
                    </select>
                </div>
                <div id="register-error-banner" class="error-banner hidden"></div>
                <button class="btn btn-primary" onclick="handleRegister()" style="margin-top: 1rem;">Create Account & Onboard</button>
            </div>
        </section>

        <section id="section-app" class="card hidden">
            <div id="quiz-form">
                <h2 id="quiz-heading">Daily Hormone Activity Log</h2>
                <div class="form-group" style="flex-direction: row; align-items: center; gap: 1rem; margin-bottom: 1.5rem;">
                    <label for="quiz-log-date" style="font-weight: 600;">Logging activities for:</label>
                    <select id="quiz-log-date" onchange="handleLogDateChange()" style="padding: 0.4rem 1rem; border-radius: 0.5rem; border: 2px solid #e9d5ff;">
                        <option value="today">Today</option>
                        <option value="yesterday">Yesterday</option>
                    </select>
                </div>
                <p style="color: var(--text-muted); margin-bottom: 2rem;">
                    Hormone levels shift based on our daily practices. Let's record which target activities you engaged in.
                </p>
                <div id="questions-container"></div>
                <div style="display: flex; gap: 1rem; margin-top: 2rem;">
                    <button class="btn btn-primary" onclick="submitQuiz()">Submit Daily Log</button>
                </div>
            </div>

            <div id="loading" class="hidden">
                <div class="spinner"></div>
                <p style="text-align: center; color: var(--text-muted);">Running Agent Graph Workflow...</p>
            </div>

            <div id="pending-review-notice" class="hidden">
                <div class="score-badge score-fail">Reviewing with Coach</div>
                <h2>Almost there!</h2>
                <p>Because your score is under 50, your results are pending Coach review. Please log back in once you receive an email alert from your health coach.</p>
            </div>

            <div id="results-dashboard" class="hidden">
                <h2>Your Hormone Balance Dashboard</h2>
                <div id="score-display"></div>
                <div id="coach-notes-display"></div>
                <div id="girl-talk-display"></div>
                <div id="jokes-display"></div>
                <button id="btn-log-yesterday" class="btn btn-secondary" onclick="logYesterday()" style="margin-top: 2rem; margin-right: 1rem;">Log Yesterday's Activities</button>
                <button class="btn btn-primary" onclick="resetApp()" style="margin-top: 2rem;">Log Today's Activities</button>
            </div>

            <div id="screening-error" class="hidden">
                <h2>Screening Result</h2>
                <div class="error-banner" id="error-message"></div>
                <button class="btn btn-primary" onclick="handleLogout()" style="margin-top: 2rem;">Log Out & Sign in Correctly</button>
            </div>

            <div id="calendar-wrapper" class="calendar-container hidden">
                <h2>Monthly Wellness Calendar</h2>
                <div id="tracker-calendar"></div>
            </div>
        </section>

        <section id="section-portal" class="card hidden"></section>
    </main>

    <script>
        let loggedInUser = null;
        let activeSessionId = null;
        let pollInterval = null;
        let calendarMonthOffset = 0;

        const COACH_PORTAL_HTML = `
            <h2>Health Coach Portal</h2>
            <div id="no-pending" style="padding: 2rem; text-align: center; color: var(--text-muted);">
                No sessions currently pending review.
            </div>
            <div id="pending-table-container" class="hidden">
                <table>
                    <thead>
                        <tr>
                            <th>User Name</th>
                            <th>Age</th>
                            <th>Gender</th>
                            <th>Hormone Inputs</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody id="pending-list"></tbody>
                </table>
            </div>
        `;

        window.addEventListener('load', () => {
            const saved = localStorage.getItem('perimeter_user');
            if (saved) {
                loggedInUser = JSON.parse(saved);
                loadMainApp();
            }
        });

        function switchAuthTab(form) {
            document.querySelectorAll('.auth-toggle a').forEach(a => a.classList.remove('active'));
            document.getElementById('forgot-form').classList.add('hidden');
            if (form === 'login') {
                document.getElementById('toggle-login').classList.add('active');
                document.getElementById('login-form').classList.remove('hidden');
                document.getElementById('register-form').classList.add('hidden');
            } else {
                document.getElementById('toggle-register').classList.add('active');
                document.getElementById('login-form').classList.add('hidden');
                document.getElementById('register-form').classList.remove('hidden');
            }
        }

        function showForgotPassword(event) {
            if (event) event.preventDefault();
            document.querySelectorAll('.auth-toggle a').forEach(a => a.classList.remove('active'));
            document.getElementById('login-form').classList.add('hidden');
            document.getElementById('register-form').classList.add('hidden');
            document.getElementById('forgot-form').classList.remove('hidden');
            document.getElementById('forgot-email').value = '';
            document.getElementById('forgot-message-banner').classList.add('hidden');
            document.getElementById('forgot-error-banner').classList.add('hidden');
        }

        function handleForgotPassword() {
            const email = document.getElementById('forgot-email').value.trim();
            if (!email) {
                document.getElementById('forgot-error-banner').innerText = "Please enter an email address.";
                document.getElementById('forgot-error-banner').classList.remove('hidden');
                document.getElementById('forgot-message-banner').classList.add('hidden');
                return;
            }
            
            fetch('/api/auth/forgot-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('forgot-message-banner').innerText = "An email has been sent with your credentials.";
                    document.getElementById('forgot-message-banner').classList.remove('hidden');
                    document.getElementById('forgot-error-banner').classList.add('hidden');
                } else {
                    document.getElementById('forgot-error-banner').innerText = data.error || "Email not found.";
                    document.getElementById('forgot-error-banner').classList.remove('hidden');
                    document.getElementById('forgot-message-banner').classList.add('hidden');
                }
            })
            .catch(err => {
                document.getElementById('forgot-error-banner').innerText = "An error occurred. Please try again.";
                document.getElementById('forgot-error-banner').classList.remove('hidden');
                document.getElementById('forgot-message-banner').classList.add('hidden');
            });
        }

        function handleLogin() {
            const username = document.getElementById('login-username').value.trim();
            const password = document.getElementById('login-password').value.trim();
            fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    loggedInUser = data.user;
                    loggedInUser.password = password;
                    localStorage.setItem('perimeter_user', JSON.stringify(loggedInUser));
                    loadMainApp();
                } else {
                    document.getElementById('login-error-banner').innerText = data.error;
                    document.getElementById('login-error-banner').classList.remove('hidden');
                }
            });
        }

        function handleRegister() {
            const username = document.getElementById('reg-username').value.trim();
            const password = document.getElementById('reg-password').value.trim();
            const email = document.getElementById('reg-email').value.trim();
            const name = document.getElementById('reg-name').value.trim();
            const age = parseInt(document.getElementById('reg-age').value);
            const gender = document.getElementById('reg-gender').value;
            const peri = document.getElementById('reg-perimenopause_status').value;
            
            if (!username) {
                document.getElementById('register-error-banner').innerText = "Username cannot be empty.";
                document.getElementById('register-error-banner').classList.remove('hidden');
                return;
            }
            if (username.length > 8) {
                document.getElementById('register-error-banner').innerText = "Username must be at most 8 characters long.";
                document.getElementById('register-error-banner').classList.remove('hidden');
                return;
            }
            
            const passwordRegex = /^(?=.*[a-zA-Z])(?=.*[0-9])(?=.*[!@#])[a-zA-Z0-9!@#]{8}$/;
            if (!passwordRegex.test(password)) {
                document.getElementById('register-error-banner').innerText = "Password must be exactly 8 characters long, containing a combination of alphabets, numbers, and only !, @, # as special characters.";
                document.getElementById('register-error-banner').classList.remove('hidden');
                return;
            }
            if (!email || !email.includes('@') || !email.includes('.')) {
                document.getElementById('register-error-banner').innerText = "Please enter a valid email address.";
                document.getElementById('register-error-banner').classList.remove('hidden');
                return;
            }
            if (!name) {
                document.getElementById('register-error-banner').innerText = "Name cannot be empty.";
                document.getElementById('register-error-banner').classList.remove('hidden');
                return;
            }
            if (isNaN(age) || age <= 0) {
                document.getElementById('register-error-banner').innerText = "Age must be a positive number.";
                document.getElementById('register-error-banner').classList.remove('hidden');
                return;
            }

            fetch('/api/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password, email, name, age, gender, perimenopause_status: peri })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    loggedInUser = { id: data.user_id, username, email, name, age, gender, perimenopause_status: peri, is_coach: false };
                    loggedInUser.password = password;
                    localStorage.setItem('perimeter_user', JSON.stringify(loggedInUser));
                    loadMainApp();
                } else {
                    document.getElementById('register-error-banner').innerText = data.error;
                    document.getElementById('register-error-banner').classList.remove('hidden');
                }
            });
        }

        function handleLogout() {
            if (pollInterval) clearInterval(pollInterval);
            loggedInUser = null;
            localStorage.removeItem('perimeter_user');
            location.reload();
        }

        function loadMainApp() {
            document.getElementById('user-display-name').innerText = loggedInUser.name;
            document.getElementById('user-header-badge').classList.remove('hidden');
            document.getElementById('section-auth').classList.add('hidden');
            
            const tabButtons = document.querySelector('.tab-buttons');
            const tabPortal = document.getElementById('tab-portal');
            const tabApp = document.getElementById('tab-app');

            if (loggedInUser.is_coach) {
                tabButtons.style.display = 'flex';
                tabPortal.style.display = 'block';
                tabApp.style.display = 'none';
                
                // Securely inject the coach portal HTML details only for authenticated coaches
                document.getElementById('section-portal').innerHTML = COACH_PORTAL_HTML;
                
                switchTab('portal');
            } else {
                // Early eligibility check
                const age = parseInt(loggedInUser.age);
                const gender = loggedInUser.gender.toLowerCase();
                const peri = loggedInUser.perimenopause_status.toLowerCase();
                
                let eligibilityError = null;
                if (isNaN(age) || age <= 0) {
                    eligibilityError = "Age cannot be zero or negative.";
                } else if (gender === "male") {
                    eligibilityError = "PeriMeter AI is designed for individuals of female biology.";
                } else if (age < 35 || age > 80) {
                    eligibilityError = "PeriMeter AI is optimized for ages 35+ (up to 80).";
                } else if (peri !== "yes") {
                    eligibilityError = "PeriMeter AI is designed for those experiencing perimenopause.";
                }
                
                if (eligibilityError) {
                    // Show screening error immediately and hide everything else
                    tabButtons.style.display = 'none';
                    tabPortal.style.display = 'none';
                    tabApp.style.display = 'block';
                    document.getElementById('section-portal').innerHTML = '';

                    document.getElementById('error-message').innerText = eligibilityError;
                    document.getElementById('screening-error').classList.remove('hidden');
                    document.getElementById('section-app').classList.remove('hidden');
                    document.getElementById('quiz-form').classList.add('hidden');
                    document.getElementById('results-dashboard').classList.add('hidden');
                    document.getElementById('calendar-wrapper').classList.add('hidden');
                    return;
                }

                // Completely hide tab buttons and empty the coach portal content for other users
                tabButtons.style.display = 'none';
                tabPortal.style.display = 'none';
                tabApp.style.display = 'block';
                document.getElementById('section-portal').innerHTML = '';
                
                switchTab('app');
                
                // Check if user has already logged today
                fetch('/api/logs?user_id=' + loggedInUser.id)
                    .then(res => res.json())
                    .then(logs => {
                        renderCalendar(logs);
                        document.getElementById('calendar-wrapper').classList.remove('hidden');
                        const todayStr = new Date().toISOString().split('T')[0];
                        const todaysLog = logs.find(l => l.date === todayStr);
                        if (todaysLog) {
                            document.getElementById('quiz-form').classList.add('hidden');
                            showDashboard({
                                eligible: true,
                                score: todaysLog.score,
                                coach_note: todaysLog.coach_note,
                                girl_talk: todaysLog.girl_talk,
                                jokes: (typeof todaysLog.jokes === 'string') ? JSON.parse(todaysLog.jokes) : todaysLog.jokes,
                                date: todaysLog.date
                            });
                        } else {
                            resetApp();
                        }
                    })
                    .catch(err => {
                        console.error("Error loading logs:", err);
                        resetApp();
                    });
            }
        }

        function switchTab(tab) {
            if (tab === 'portal' && (!loggedInUser || !loggedInUser.is_coach)) {
                return;
            }
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('tab-' + tab).classList.add('active');
            if (tab === 'app') {
                document.getElementById('section-app').classList.remove('hidden');
                document.getElementById('section-portal').classList.add('hidden');
            } else {
                document.getElementById('section-app').classList.add('hidden');
                document.getElementById('section-portal').classList.remove('hidden');
                loadPendingReviews();
            }
        }

        function getTargetDateStr(mode) {
            if (mode === 'yesterday') {
                return new Date(Date.now() - 86400000).toISOString().split('T')[0];
            }
            return new Date().toISOString().split('T')[0];
        }

        function handleLogDateChange() {
            const dateSelect = document.getElementById('quiz-log-date').value;
            const targetDateStr = getTargetDateStr(dateSelect);
            
            // Check if there is already a log for this date
            fetch('/api/logs?user_id=' + loggedInUser.id)
                .then(res => res.json())
                .then(logs => {
                    const log = logs.find(l => l.date === targetDateStr);
                    if (log) {
                        document.getElementById('quiz-form').classList.add('hidden');
                        showDashboard({
                            eligible: true,
                            score: log.score,
                            coach_note: log.coach_note,
                            girl_talk: log.girl_talk,
                            jokes: (typeof log.jokes === 'string') ? JSON.parse(log.jokes) : log.jokes,
                            date: log.date
                        });
                    } else {
                        // Keep quiz form visible, but clear checkboxes
                        document.getElementById('quiz-form').classList.remove('hidden');
                        document.getElementById('results-dashboard').classList.add('hidden');
                        document.querySelectorAll('.checkbox-label input[type="checkbox"]').forEach(c => {
                            c.checked = false;
                            c.parentElement.classList.remove('selected');
                        });
                    }
                })
                .catch(err => console.error("Error checking date logs:", err));
        }

        function logYesterday() {
            document.getElementById('results-dashboard').classList.add('hidden');
            document.getElementById('pending-review-notice').classList.add('hidden');
            document.getElementById('screening-error').classList.add('hidden');
            
            loadQuizQuestions();
            
            // Wait for quiz to load, then set to yesterday
            setTimeout(() => {
                const select = document.getElementById('quiz-log-date');
                if (select) {
                    select.value = 'yesterday';
                    handleLogDateChange();
                }
            }, 300);
        }

        function loadQuizQuestions() {
            fetch('/api/hormones')
                .then(res => res.json())
                .then(data => {
                    const container = document.getElementById('questions-container');
                    container.innerHTML = '';
                    for (const [hormone, details] of Object.entries(data)) {
                        const hSec = document.createElement('div');
                        hSec.className = 'hormone-section';
                        hSec.innerHTML = `<div class="hormone-title">${hormone}</div><p>${details.question}</p>`;
                        const optionsDiv = document.createElement('div');
                        optionsDiv.className = 'checkbox-options';
                        details.options.forEach(optText => {
                            const label = document.createElement('label');
                            label.className = 'checkbox-label';
                            label.innerHTML = `<input type="checkbox" name="${hormone}" value="${optText}"> ${optText}`;
                            label.querySelector('input').addEventListener('change', function() {
                                this.parentElement.classList.toggle('selected', this.checked);
                            });
                            optionsDiv.appendChild(label);
                        });
                        hSec.appendChild(optionsDiv);
                        container.appendChild(hSec);
                    }
                    const select = document.getElementById('quiz-log-date');
                    if (select) select.value = 'today';
                    document.getElementById('quiz-form').classList.remove('hidden');
                });
        }

        function startPolling(sessionId) {
            if (pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(() => {
                fetch('/api/status/' + sessionId)
                .then(res => res.json())
                .then(data => {
                    if (data.status === 'completed') {
                        clearInterval(pollInterval);
                        document.getElementById('pending-review-notice').classList.add('hidden');
                        showDashboard(data.data);
                    }
                })
                .catch(err => console.error("Error polling status:", err));
            }, 3000);
        }

        function submitQuiz() {
            const answers = {};
            document.querySelectorAll('.hormone-section').forEach(sec => {
                const hormone = sec.querySelector('.hormone-title').innerText;
                const checked = [];
                sec.querySelectorAll('input:checked').forEach(c => checked.push(c.value));
                answers[hormone] = checked;
            });
            const logDateSelect = document.getElementById('quiz-log-date') ? document.getElementById('quiz-log-date').value : 'today';
            const dateStr = getTargetDateStr(logDateSelect);
            
            fetch('/api/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: loggedInUser.id,
                    name: loggedInUser.name,
                    age: loggedInUser.age,
                    gender: loggedInUser.gender,
                    perimenopause_status: loggedInUser.perimenopause_status,
                    answers,
                    date: dateStr
                })
            })
            .then(res => res.json())
            .then(resData => {
                document.getElementById('quiz-form').classList.add('hidden');
                if (resData.status === 'completed') {
                    showDashboard(resData.data);
                } else if (resData.status === 'pending_coach_review') {
                    document.getElementById('pending-review-notice').classList.remove('hidden');
                }
            });
        }

        function showDashboard(report) {
            document.getElementById('pending-review-notice').classList.add('hidden');
            
            if (!report.eligible) {
                document.getElementById('error-message').innerText = report.error_message;
                document.getElementById('screening-error').classList.remove('hidden');
                document.getElementById('calendar-wrapper').classList.add('hidden');
                return;
            }

            const scoreDisplay = document.getElementById('score-display');
            scoreDisplay.innerHTML = '';
            
            // Format target date and timezone
            let targetDate = new Date();
            if (report.date) {
                const parts = report.date.split('-');
                targetDate = new Date(parts[0], parts[1] - 1, parts[2]);
            }
            const dateStr = new Intl.DateTimeFormat('en-US', {
                weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', timeZoneName: 'short'
            }).format(targetDate);
            
            const dateHeader = document.createElement('h3');
            dateHeader.style.color = 'var(--text-muted)';
            dateHeader.style.marginTop = '0';
            dateHeader.innerText = dateStr;
            scoreDisplay.appendChild(dateHeader);
            
            const badge = document.createElement('div');
            badge.className = 'score-badge ' + (report.score >= 50 ? 'score-pass' : 'score-fail');
            badge.innerText = `Score: ${report.score}`;
            scoreDisplay.appendChild(badge);
            
            const minScoreText = document.createElement('p');
            minScoreText.style.color = 'var(--text-muted)';
            minScoreText.style.fontSize = '0.9rem';
            minScoreText.style.marginTop = '0.5rem';
            minScoreText.style.marginBottom = '2rem';
            minScoreText.innerText = 'The minimum target score for hormonal balance is 60.';
            scoreDisplay.appendChild(minScoreText);

            // Coach notes
            const coachDiv = document.getElementById('coach-notes-display');
            coachDiv.innerHTML = '';
            if (report.coach_note) {
                const box = document.createElement('div');
                box.className = 'coach-note-box';
                box.innerHTML = `<div class="coach-note-title">Health Coach Encouragement</div><p>${report.coach_note}</p>`;
                coachDiv.appendChild(box);
            }

            // Girl talk
            const talkDiv = document.getElementById('girl-talk-display');
            talkDiv.innerHTML = '';
            if (report.girl_talk) {
                const box = document.createElement('div');
                box.className = 'girl-talk-box';
                box.innerHTML = `<div class="girl-talk-title">Daily Motivation & Girl Talk</div><p>${report.girl_talk.replace(/\\\\n/g, '<br>')}</p>`;
                talkDiv.appendChild(box);
            }

            // Jokes display
            const jokesDiv = document.getElementById('jokes-display');
            jokesDiv.innerHTML = '';
            if (report.jokes && report.jokes.length > 0) {
                const title = document.createElement('h3');
                title.innerText = "Daily Smiles:";
                jokesDiv.appendChild(title);
                
                report.jokes.forEach(joke => {
                    const box = document.createElement('div');
                    box.className = 'joke-box';
                    box.innerText = joke;
                    jokesDiv.appendChild(box);
                });
            }

            refreshCalendar();
                
            document.getElementById('results-dashboard').classList.remove('hidden');
        }

        function refreshCalendar() {
            if (!loggedInUser) return;
            fetch('/api/logs?user_id=' + loggedInUser.id)
                .then(res => res.json())
                .then(logs => {
                    renderCalendar(logs);
                    document.getElementById('calendar-wrapper').classList.remove('hidden');
                });
        }

        function renderCalendar(logs) {
            const calendarContainer = document.getElementById('tracker-calendar');
            calendarContainer.innerHTML = '';

            const today = new Date();
            const targetDate = new Date(today.getFullYear(), today.getMonth() + calendarMonthOffset, 1);
            const year = targetDate.getFullYear();
            const month = targetDate.getMonth();

            const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
            
            const calHeader = document.createElement('div');
            calHeader.style.display = 'flex';
            calHeader.style.justifyContent = 'space-between';
            calHeader.style.alignItems = 'center';
            calHeader.style.marginBottom = '1.5rem';
            
            const btnPrev = document.createElement('button');
            btnPrev.className = 'btn btn-secondary';
            btnPrev.style.padding = '0.2rem 0.5rem';
            btnPrev.innerText = '<';
            btnPrev.onclick = function() {
                calendarMonthOffset--;
                refreshCalendar();
            };
            
            const btnNext = document.createElement('button');
            btnNext.className = 'btn btn-secondary';
            btnNext.style.padding = '0.2rem 0.5rem';
            btnNext.innerText = '>';
            btnNext.onclick = function() {
                calendarMonthOffset++;
                refreshCalendar();
            };

            const calTitle = document.createElement('h3');
            calTitle.style.margin = '0';
            calTitle.innerText = `${monthNames[month]} ${year}`;
            
            const titleDiv = document.createElement('div');
            titleDiv.style.display = 'flex';
            titleDiv.style.alignItems = 'center';
            titleDiv.style.gap = '1rem';
            titleDiv.appendChild(btnPrev);
            titleDiv.appendChild(calTitle);
            titleDiv.appendChild(btnNext);
            
            calHeader.appendChild(titleDiv);
            calendarContainer.appendChild(calHeader);

            const grid = document.createElement('div');
            grid.className = 'calendar-grid';
            
            const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
            weekdays.forEach(day => {
                const dayHeader = document.createElement('div');
                dayHeader.className = 'calendar-day-header';
                dayHeader.innerText = day;
                grid.appendChild(dayHeader);
            });

            const firstDay = new Date(year, month, 1).getDay();
            const daysInMonth = new Date(year, month + 1, 0).getDate();

            for (let i = 0; i < firstDay; i++) {
                const cell = document.createElement('div');
                cell.className = 'calendar-cell blank';
                grid.appendChild(cell);
            }

            for (let d = 1; d <= daysInMonth; d++) {
                const cell = document.createElement('div');
                cell.className = 'calendar-cell';
                
                const dateNum = document.createElement('span');
                dateNum.className = 'date-num';
                dateNum.innerText = d;
                cell.appendChild(dateNum);

                const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
                const log = logs.find(l => l.date === dateStr);
                if (log) {
                    const scoreBadge = document.createElement('div');
                    scoreBadge.className = log.score >= 50 ? 'score-indicator high' : 'score-indicator low';
                    scoreBadge.innerText = `${log.score}`;
                    cell.appendChild(scoreBadge);
                    cell.style.cursor = 'pointer';
                    cell.title = `Score: ${log.score}\nCoach Note: ${log.coach_note || 'None'}`;
                    cell.onclick = function() {
                        showDashboard({
                            eligible: true,
                            score: log.score,
                            coach_note: log.coach_note,
                            girl_talk: log.girl_talk,
                            jokes: log.jokes
                        });
                    };
                }

                grid.appendChild(cell);
            }

            calendarContainer.appendChild(grid);
        }

        function resetApp() {
            if (pollInterval) clearInterval(pollInterval);
            document.getElementById('results-dashboard').classList.add('hidden');
            document.getElementById('pending-review-notice').classList.add('hidden');
            loadQuizQuestions();
            refreshCalendar();
            // Wait for quiz to load, then ensure date is today and check log status
            setTimeout(() => {
                const select = document.getElementById('quiz-log-date');
                if (select) {
                    select.value = 'today';
                    handleLogDateChange();
                }
            }, 300);
        }

        function loadPendingReviews() {
            const headers = { 'Content-Type': 'application/json' };
            if (loggedInUser) {
                headers['X-Coach-Username'] = loggedInUser.username;
                headers['X-Coach-Password'] = loggedInUser.password;
            }
            fetch('/api/pending', {
                headers: headers
            })
                .then(res => {
                    if (res.status === 403) {
                        alert("Unauthorized: Health coach access required.");
                        handleLogout();
                        throw new Error("Unauthorized");
                    }
                    return res.json();
                })
                .then(reviews => {
                    const tbody = document.getElementById('pending-list');
                    tbody.innerHTML = '';

                    if (reviews.length === 0) {
                        document.getElementById('no-pending').classList.remove('hidden');
                        document.getElementById('pending-table-container').classList.add('hidden');
                        return;
                    }

                    document.getElementById('no-pending').classList.add('hidden');
                    document.getElementById('pending-table-container').classList.remove('hidden');

                    reviews.forEach(review => {
                        const tr = document.createElement('tr');
                        
                        const tdName = document.createElement('td');
                        tdName.innerText = review.name;
                        tr.appendChild(tdName);

                        const tdAge = document.createElement('td');
                        tdAge.innerText = review.age;
                        tr.appendChild(tdAge);

                        const tdGender = document.createElement('td');
                        tdGender.innerText = review.gender;
                        tr.appendChild(tdGender);

                        const tdHormones = document.createElement('td');
                        const list = document.createElement('ul');
                        list.style.paddingLeft = '1.2rem';
                        list.style.margin = '0';
                        for (const [hormone, ans] of Object.entries(review.answers)) {
                            const li = document.createElement('li');
                            li.innerHTML = `<strong>${hormone}</strong>: ${ans.join(', ')}`;
                            list.appendChild(li);
                        }
                        tdHormones.appendChild(list);
                        tr.appendChild(tdHormones);

                        const tdAction = document.createElement('td');
                        const wrapper = document.createElement('div');
                        wrapper.style.display = 'flex';
                        wrapper.style.flexDirection = 'column';
                        wrapper.style.gap = '0.5rem';

                        const textarea = document.createElement('textarea');
                        textarea.className = 'textarea-coach';
                        textarea.placeholder = 'Provide motivation note...';
                        textarea.rows = 2;
                        
                        const btn = document.createElement('button');
                        btn.className = 'btn btn-primary';
                        btn.innerText = 'Approve & Send';
                        btn.style.padding = '0.4rem 1rem';
                        btn.style.fontSize = '0.9rem';
                        btn.onclick = function() {
                            const note = textarea.value.trim();
                            if (!note) {
                                alert('Please provide some encouragement comments.');
                                return;
                            }
                            submitCoachReview(review.session_id, note, btn);
                        };

                        wrapper.appendChild(textarea);
                        wrapper.appendChild(btn);
                        tdAction.appendChild(wrapper);
                        tr.appendChild(tdAction);

                        tbody.appendChild(tr);
                    });
                })
                .catch(err => {
                    console.error("Error loading pending reviews:", err);
                });
        }

        function submitCoachReview(sessionId, note, button) {
            button.disabled = true;
            button.innerText = 'Submitting...';

            const headers = { 'Content-Type': 'application/json' };
            if (loggedInUser) {
                headers['X-Coach-Username'] = loggedInUser.username;
                headers['X-Coach-Password'] = loggedInUser.password;
            }

            fetch('/api/coach-review/' + sessionId, {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({ coach_note: note })
            })
            .then(res => {
                if (res.status === 403) {
                    alert("Unauthorized: Health coach access required.");
                    handleLogout();
                    throw new Error("Unauthorized");
                }
                return res.json();
            })
            .then(data => {
                alert('Review submitted successfully!');
                loadPendingReviews();
            })
            .catch(err => {
                button.disabled = false;
                button.innerText = 'Approve & Send';
                alert('Error submitting review');
            });
        }
    </script>
</body>
</html>
"""
