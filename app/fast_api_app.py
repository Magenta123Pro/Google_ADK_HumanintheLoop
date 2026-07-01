import os
from fastapi import FastAPI, Request
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

app = FastAPI(title="PeriMeter AI - Hormonal Balance Motivator")

# Initialize ADK runtime services
session_service = InMemorySessionService()
runner = Runner(agent=root_agent, session_service=session_service, app_name="perimeter_agent")

# In-memory store for UI to track session states
active_sessions = {}
pending_reviews = {}

class SubmitQuizPayload(BaseModel):
    name: str
    age: int
    gender: str
    perimenopause_status: str
    answers: dict[str, str]

class CoachReviewPayload(BaseModel):
    coach_note: str

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    # Renders the HTML template containing the UI and Coach Portal
    return HTMLResponse(content=INDEX_HTML_TEMPLATE)

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
        
        if interrupted and interrupt_id:
            # Workflow is suspended waiting for coach input
            pending_reviews[session_id] = {
                "session_id": session_id,
                "name": payload.name,
                "age": payload.age,
                "gender": payload.gender,
                "interrupt_id": interrupt_id,
                "answers": payload.answers
            }
            active_sessions[session_id] = {"status": "pending_coach_review"}
            return JSONResponse(content={
                "status": "pending_coach_review",
                "session_id": session_id,
                "message": "Your score is under 50. A Health Coach will review your report shortly to provide personalized encouragement!"
            })
            
        # If not interrupted, it means it completed (either ineligible or score >= 50)
        final_report = None
        for event in events:
            if event.output and isinstance(event.output, dict):
                final_report = event.output
                break
                
        if final_report:
            active_sessions[session_id] = {
                "status": "completed",
                "data": final_report
            }
            return JSONResponse(content={
                "status": "completed",
                "session_id": session_id,
                "data": final_report
            })
            
        return JSONResponse(status_code=500, content={"error": "Workflow did not return a valid report"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/pending")
async def get_pending_reviews():
    return JSONResponse(content=list(pending_reviews.values()))

@app.post("/api/coach-review/{session_id}")
async def submit_coach_review(session_id: str, payload: CoachReviewPayload):
    if session_id not in pending_reviews:
        return JSONResponse(status_code=404, content={"error": "Session review not found"})
        
    review_info = pending_reviews[session_id]
    interrupt_id = review_info["interrupt_id"]
    
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
        
        # Clean up from pending list
        pending_reviews.pop(session_id)
        
        # Extract finalized report
        final_report = None
        for event in events:
            if event.output and isinstance(event.output, dict):
                final_report = event.output
                break
                
        if final_report:
            active_sessions[session_id] = {
                "status": "completed",
                "data": final_report
            }
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
    <title>PeriMeter AI - Hormonal Balance Motivator</title>
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

        main {
            max-width: 900px;
            width: 95%;
            margin: 2rem 0;
            display: flex;
            flex-direction: column;
            gap: 2rem;
        }

        /* Glassmorphic Cards */
        .card {
            background-color: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border: 2px solid rgba(255, 255, 255, 0.5);
            border-radius: 1.5rem;
            padding: 2.5rem;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.03), 0 4px 6px -2px rgba(0, 0, 0, 0.02);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }

        .card:hover {
            transform: translateY(-2px);
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.05);
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

        input[type="text"], input[type="number"], select {
            font-family: var(--font-family);
            padding: 0.8rem 1.2rem;
            border-radius: 0.75rem;
            border: 2px solid #e9d5ff;
            background-color: #fff;
            font-size: 1rem;
            outline: none;
            transition: border-color 0.2s;
        }

        input[type="text"]:focus, input[type="number"]:focus, select:focus {
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

        .btn-primary:hover {
            background-color: #d8b4fe;
        }

        .btn-secondary {
            background-color: var(--card-peach);
            color: #c2410c;
            border: 2px solid #ffedd5;
        }

        .btn-secondary:hover {
            background-color: #ffedd5;
        }

        /* Radio Options styling */
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

        .radio-options {
            display: flex;
            flex-direction: column;
            gap: 0.6rem;
        }

        .radio-label {
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

        .radio-label:hover {
            background-color: #fff7ed;
            border-color: #fed7aa;
        }

        .radio-label input[type="radio"] {
            width: 1.2rem;
            height: 1.2rem;
            accent-color: var(--pastel-orange);
        }

        .radio-label.selected {
            background-color: #ffedd5;
            border-color: var(--pastel-orange);
        }

        /* Dashboard Results styling */
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

        .joke-box {
            background-color: rgba(255, 255, 255, 0.9);
            border-left: 6px solid var(--pastel-purple);
            padding: 1.2rem;
            border-radius: 0.5rem;
            font-style: italic;
            margin-top: 1rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);
        }

        .girl-talk-box {
            background-color: var(--accent-rose);
            border: 2px solid #ffe4e6;
            padding: 1.5rem;
            border-radius: 1rem;
            margin-top: 1.5rem;
            line-height: 1.6;
        }

        .girl-talk-title {
            font-weight: 600;
            font-size: 1.3rem;
            color: var(--rose-text);
            margin-bottom: 0.5rem;
        }

        .coach-note-box {
            background-color: var(--accent-mint);
            border: 2px solid #dcfce7;
            padding: 1.5rem;
            border-radius: 1rem;
            margin-top: 1.5rem;
        }

        .coach-note-title {
            font-weight: 600;
            font-size: 1.3rem;
            color: var(--mint-text);
            margin-bottom: 0.5rem;
        }

        /* Review portal table */
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

        th {
            color: #6b21a8;
            font-weight: 600;
        }

        .textarea-coach {
            font-family: var(--font-family);
            width: 100%;
            padding: 0.8rem;
            border-radius: 0.5rem;
            border: 2px solid #e9d5ff;
            resize: vertical;
            outline: none;
        }

        .textarea-coach:focus {
            border-color: var(--pastel-purple);
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
        <h1>PeriMeter AI</h1>
        <p>Your Gentle Guide to Daily Hormonal Balance • Agents for Good</p>
    </header>

    <main>
        <!-- Tab Navigation -->
        <div class="tab-buttons">
            <button class="tab-btn active" id="tab-app" onclick="switchTab('app')">Motivator App</button>
            <button class="tab-btn" id="tab-portal" onclick="switchTab('portal')">Health Coach Portal</button>
        </div>

        <!-- Section 1: Motivator App -->
        <section id="section-app" class="card">
            <!-- Phase 1: Onboarding -->
            <div id="onboarding-form">
                <h2>Welcome to PeriMeter AI</h2>
                <p style="color: var(--text-muted); margin-bottom: 2rem;">
                    Let's screen your details to make sure you are in our target wellness range.
                </p>
                <div class="form-group">
                    <label for="name">What is your name?</label>
                    <input type="text" id="name" placeholder="Enter your name" required>
                </div>
                <div class="form-group">
                    <label for="age">What is your age?</label>
                    <input type="number" id="age" min="0" placeholder="Enter your age" required>
                </div>
                <div class="form-group">
                    <label for="gender">What is your gender?</label>
                    <select id="gender">
                        <option value="female">Female</option>
                        <option value="male">Male</option>
                        <option value="other">Other</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="perimenopause_status">Are you experiencing symptoms of perimenopause?</label>
                    <select id="perimenopause_status">
                        <option value="yes">Yes, currently experiencing symptoms</option>
                        <option value="no">No</option>
                    </select>
                </div>
                <div id="onboarding-error-banner" class="error-banner hidden" style="margin-top: 1rem; margin-bottom: 1rem;"></div>
                <button class="btn btn-primary" onclick="proceedToQuiz()" style="margin-top: 1rem;">Next</button>
            </div>

            <!-- Phase 2: Hormone Quiz -->
            <div id="quiz-form" class="hidden">
                <h2 id="quiz-heading">Daily Hormone Activity Log</h2>
                <p style="color: var(--text-muted); margin-bottom: 2rem;">
                    Hormone levels shift based on our daily practices. Let's record which target activities you engaged in today.
                </p>
                
                <div id="questions-container"></div>
                
                <div style="display: flex; gap: 1rem; margin-top: 2rem;">
                    <button class="btn btn-secondary" onclick="backToOnboarding()">Back</button>
                    <button class="btn btn-primary" onclick="submitQuiz()">Submit Daily Log</button>
                </div>
            </div>

            <!-- Loading Spinner -->
            <div id="loading" class="hidden">
                <div class="spinner"></div>
                <p style="text-align: center; color: var(--text-muted);">Running Agent Graph Workflow...</p>
            </div>

            <!-- Review Interruption Notice -->
            <div id="pending-review-notice" class="hidden">
                <div class="score-badge score-fail">Reviewing with Coach</div>
                <h2>Almost there!</h2>
                <p>Because your score is under 50, your results have been routed to our Health Coach team for a Human-in-the-Loop review. They will add personal encouragement and support recommendations shortly.</p>
                <div class="spinner"></div>
                <p style="text-align: center; color: var(--text-muted); font-size: 0.9rem;">Waiting for coach approval... (You can review this session in the Coach Portal tab)</p>
            </div>

            <!-- Phase 3: Dashboard Results -->
            <div id="results-dashboard" class="hidden">
                <h2>Your Hormone Balance Dashboard</h2>
                <div id="score-display"></div>
                
                <div id="coach-notes-display"></div>
                <div id="girl-talk-display"></div>
                <div id="jokes-display"></div>
                <div id="tips-display" style="margin-top: 1.5rem;"></div>

                <button class="btn btn-primary" onclick="resetApp()" style="margin-top: 2rem;">Log Tomorrow's Activities</button>
            </div>

            <!-- Screening Rejected Error Screen -->
            <div id="screening-error" class="hidden">
                <h2>Screening Result</h2>
                <div class="error-banner" id="error-message"></div>
                <button class="btn btn-primary" onclick="resetApp()" style="margin-top: 2rem;">Start Over</button>
            </div>
        </section>

        <!-- Section 2: Health Coach Portal -->
        <section id="section-portal" class="card hidden">
            <h2>Health Coach Portal</h2>
            <p style="color: var(--text-muted); margin-bottom: 2rem;">
                Review pending sessions with low scores and input custom advice to resume the patient's motivator loop.
            </p>
            <div id="no-pending" style="padding: 2rem; text-align: center; color: var(--text-muted);">
                No sessions currently pending review. Good job, Coach!
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
        </section>
    </main>

    <script>
        let userData = {};
        let activeSessionId = null;
        let pollInterval = null;

        function switchTab(tab) {
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

        function proceedToQuiz() {
            const name = document.getElementById('name').value.trim();
            const age = parseInt(document.getElementById('age').value);
            const gender = document.getElementById('gender').value;
            const peri = document.getElementById('perimenopause_status').value;
            
            const errBanner = document.getElementById('onboarding-error-banner');
            errBanner.classList.add('hidden');

            if (!name) {
                alert('Please enter your name.');
                return;
            }
            if (isNaN(age) || age < 0) {
                alert('Please enter a valid age.');
                return;
            }

            // Client-side eligibility checks
            if (age === 0) {
                errBanner.innerText = 'Age cannot be zero or negative.';
                errBanner.classList.remove('hidden');
                return;
            }
            if (gender === 'male') {
                errBanner.innerText = 'PeriMeter AI is designed for individuals of female biology.';
                errBanner.classList.remove('hidden');
                return;
            }
            if (age < 35) {
                errBanner.innerText = 'PeriMeter AI is optimized for ages 35+.';
                errBanner.classList.remove('hidden');
                return;
            }
            if (peri !== 'yes') {
                errBanner.innerText = 'PeriMeter AI is designed for those experiencing perimenopause.';
                errBanner.classList.remove('hidden');
                return;
            }

            userData = { name, age, gender, perimenopause_status: peri, answers: {} };

            // Fetch questions
            fetch('/api/hormones')
                .then(res => res.json())
                .then(data => {
                    const container = document.getElementById('questions-container');
                    container.innerHTML = '';
                    
                    for (const [hormone, details] of Object.entries(data)) {
                        const hSec = document.createElement('div');
                        hSec.className = 'hormone-section';
                        
                        const title = document.createElement('div');
                        title.className = 'hormone-title';
                        title.innerText = hormone;
                        hSec.appendChild(title);
                        
                        const quest = document.createElement('p');
                        quest.innerText = details.question;
                        hSec.appendChild(quest);
                        
                        const optionsDiv = document.createElement('div');
                        optionsDiv.className = 'radio-options';
                        
                        details.options.forEach((optText, index) => {
                            const label = document.createElement('label');
                            label.className = 'radio-label';
                            
                            const radio = document.createElement('input');
                            radio.type = 'radio';
                            radio.name = hormone;
                            radio.value = optText;
                            if (index === 0) radio.checked = true; // Default select first
                            
                            label.appendChild(radio);
                            label.appendChild(document.createTextNode(optText));
                            
                            radio.addEventListener('change', function() {
                                document.querySelectorAll(`input[name="${hormone}"]`).forEach(r => {
                                    r.parentElement.classList.remove('selected');
                                });
                                if (this.checked) {
                                    label.classList.add('selected');
                                }
                            });
                            
                            optionsDiv.appendChild(label);
                        });
                        
                        hSec.appendChild(optionsDiv);
                        container.appendChild(hSec);
                    }

                    document.getElementById('onboarding-form').classList.add('hidden');
                    document.getElementById('quiz-form').classList.remove('hidden');
                });
        }

        function backToOnboarding() {
            document.getElementById('quiz-form').classList.add('hidden');
            document.getElementById('onboarding-form').classList.remove('hidden');
        }

        function submitQuiz() {
            // Collect selected radio options
            const answers = {};
            document.querySelectorAll('.hormone-section').forEach(sec => {
                const hormone = sec.querySelector('.hormone-title').innerText;
                const checkedRadio = sec.querySelector('input[type="radio"]:checked');
                if (checkedRadio) {
                    answers[hormone] = checkedRadio.value;
                }
            });

            userData.answers = answers;

            document.getElementById('quiz-form').classList.add('hidden');
            document.getElementById('loading').classList.remove('hidden');

            fetch('/api/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(userData)
            })
            .then(res => res.json())
            .then(resData => {
                document.getElementById('loading').classList.add('hidden');
                activeSessionId = resData.session_id;

                if (resData.status === 'pending_coach_review') {
                    document.getElementById('pending-review-notice').classList.remove('hidden');
                    // Start polling for updates
                    pollInterval = setInterval(checkSessionStatus, 3000);
                } else if (resData.status === 'completed') {
                    showDashboard(resData.data);
                }
            })
            .catch(err => {
                document.getElementById('loading').classList.add('hidden');
                alert('An error occurred during submission.');
            });
        }

        function checkSessionStatus() {
            if (!activeSessionId) return;
            
            fetch('/api/status/' + activeSessionId)
                .then(res => res.json())
                .then(resData => {
                    if (resData.status === 'completed') {
                        clearInterval(pollInterval);
                        document.getElementById('pending-review-notice').classList.add('hidden');
                        showDashboard(resData.data);
                    }
                });
        }

        function showDashboard(report) {
            document.getElementById('pending-review-notice').classList.add('hidden');
            
            if (!report.eligible) {
                document.getElementById('error-message').innerText = report.error_message;
                document.getElementById('screening-error').classList.remove('hidden');
                return;
            }

            const scoreDisplay = document.getElementById('score-display');
            scoreDisplay.innerHTML = '';
            
            const badge = document.createElement('div');
            badge.className = 'score-badge ' + (report.score >= 50 ? 'score-pass' : 'score-fail');
            badge.innerText = `Score: ${report.score}/60`;
            scoreDisplay.appendChild(badge);

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
                box.innerHTML = `<div class="girl-talk-title">Daily Motivation & Girl Talk</div><p>${report.girl_talk.replace(/\\n/g, '<br>')}</p>`;
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

            document.getElementById('results-dashboard').classList.remove('hidden');
        }

        function resetApp() {
            clearInterval(pollInterval);
            activeSessionId = null;
            userData = {};
            document.getElementById('name').value = '';
            document.getElementById('age').value = '';
            document.getElementById('gender').value = 'female';
            document.getElementById('perimenopause_status').value = 'yes';
            
            const errBanner = document.getElementById('onboarding-error-banner');
            errBanner.innerText = '';
            errBanner.classList.add('hidden');

            document.getElementById('results-dashboard').classList.add('hidden');
            document.getElementById('screening-error').classList.add('hidden');
            document.getElementById('onboarding-form').classList.remove('hidden');
        }

        // Coach Portal functions
        function loadPendingReviews() {
            fetch('/api/pending')
                .then(res => res.json())
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
                            li.innerHTML = `<strong>${hormone}</strong>: ${ans}`;
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
                });
        }

        function submitCoachReview(sessionId, note, button) {
            button.disabled = true;
            button.innerText = 'Submitting...';

            fetch('/api/coach-review/' + sessionId, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ coach_note: note })
            })
            .then(res => res.json())
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
