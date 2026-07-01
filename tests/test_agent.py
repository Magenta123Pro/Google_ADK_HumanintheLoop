import json
import pytest
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from google.adk.workflow.utils._workflow_hitl_utils import (
    has_request_input_function_call,
    get_request_input_interrupt_ids,
    create_request_input_response,
)

from app.agent import root_agent
from app.config import HORMONE_ACTIVITIES

def get_final_report(events):
    for event in reversed(events):
        if event.output and isinstance(event.output, dict):
            return event.output
    return None

def test_ineligible_age_young() -> None:
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="perimeter_agent")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="perimeter_agent")

    payload = {
        "name": "Carol",
        "age": 30,
        "gender": "female",
        "perimenopause_status": "yes",
        "answers": {}
    }
    message = types.Content(role="user", parts=[types.Part.from_text(text=json.dumps(payload))])
    events = list(runner.run(new_message=message, user_id="test_user", session_id=session.id))
    
    report = get_final_report(events)
    assert report is not None
    assert report["eligible"] is False
    assert "35+" in report["error_message"]

def test_ineligible_age_zero() -> None:
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="perimeter_agent")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="perimeter_agent")

    payload = {
        "name": "Alice",
        "age": 0,
        "gender": "female",
        "perimenopause_status": "yes",
        "answers": {}
    }
    message = types.Content(role="user", parts=[types.Part.from_text(text=json.dumps(payload))])
    events = list(runner.run(new_message=message, user_id="test_user", session_id=session.id))
    
    report = get_final_report(events)
    assert report is not None
    assert report["eligible"] is False
    assert "zero" in report["error_message"].lower()

def test_ineligible_age_eighty_five() -> None:
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="perimeter_agent")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="perimeter_agent")

    payload = {
        "name": "Alice",
        "age": 85,
        "gender": "female",
        "perimenopause_status": "yes",
        "answers": {}
    }
    message = types.Content(role="user", parts=[types.Part.from_text(text=json.dumps(payload))])
    events = list(runner.run(new_message=message, user_id="test_user", session_id=session.id))
    
    report = get_final_report(events)
    assert report is not None
    assert report["eligible"] is False
    assert "80" in report["error_message"]

def test_ineligible_gender_male() -> None:
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="perimeter_agent")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="perimeter_agent")

    payload = {
        "name": "Bob",
        "age": 40,
        "gender": "male",
        "perimenopause_status": "no",
        "answers": {}
    }
    message = types.Content(role="user", parts=[types.Part.from_text(text=json.dumps(payload))])
    events = list(runner.run(new_message=message, user_id="test_user", session_id=session.id))
    
    report = get_final_report(events)
    assert report is not None
    assert report["eligible"] is False
    assert "female biology" in report["error_message"]

def test_eligible_high_score() -> None:
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="perimeter_agent")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="perimeter_agent")

    # Select all correct answers
    answers = {}
    for h, data in HORMONE_ACTIVITIES.items():
        correct_opt = next(o["text"] for o in data["options"] if o["correct"])
        answers[h] = correct_opt

    payload = {
        "name": "Diana",
        "age": 45,
        "gender": "female",
        "perimenopause_status": "yes",
        "answers": answers
    }
    message = types.Content(role="user", parts=[types.Part.from_text(text=json.dumps(payload))])
    events = list(runner.run(new_message=message, user_id="test_user", session_id=session.id))
    
    report = get_final_report(events)
    assert report is not None
    assert report["eligible"] is True
    assert report["score"] == 60
    assert len(report["jokes"]) == 1
    assert "Amazing job" in report["girl_talk"]

def test_eligible_low_score_hitl() -> None:
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="perimeter_agent")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="perimeter_agent")

    # Select 3 correct, 3 empty answers
    answers = {}
    hormones = list(HORMONE_ACTIVITIES.keys())
    for i, h in enumerate(hormones):
        data = HORMONE_ACTIVITIES[h]
        if i < 3:
            correct_opt = next(o["text"] for o in data["options"] if o["correct"])
            answers[h] = correct_opt
        else:
            answers[h] = []

    payload = {
        "name": "Eve",
        "age": 48,
        "gender": "female",
        "perimenopause_status": "yes",
        "answers": answers
    }
    message = types.Content(role="user", parts=[types.Part.from_text(text=json.dumps(payload))])
    events = list(runner.run(new_message=message, user_id="test_user", session_id=session.id))
    
    # Verify we hit HITL suspension
    interrupted = False
    interrupt_id = None
    for event in events:
        if has_request_input_function_call(event):
            interrupted = True
            ids = get_request_input_interrupt_ids(event)
            if ids:
                interrupt_id = ids[0]
                break

    assert interrupted is True
    assert interrupt_id == "coach_note"

    # Resume with coach comments
    response_part = create_request_input_response(interrupt_id, {"coach_note": "Great start, Eve! Let's aim to do stretching before bed tomorrow."})
    resume_message = types.Content(role="user", parts=[response_part])
    
    resume_events = list(
        runner.run(
            new_message=resume_message,
            user_id="test_user",
            session_id=session.id,
        )
    )
    
    report = get_final_report(resume_events)
    assert report is not None
    assert report["eligible"] is True
    assert report["score"] == 30
    assert len(report["jokes"]) == 2
    assert "aim to do stretching" in report["coach_note"].lower()
    assert "Cortisol" in report["girl_talk"] or "Melatonin" in report["girl_talk"] or "LH_FSH" in report["girl_talk"]

def test_multiple_options_scoring() -> None:
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="perimeter_agent")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="perimeter_agent")

    # Estrogen: 2 correct options selected -> 10 + 3 * 2 = 16 points
    # Progesterone: 3 correct options selected -> 10 + 3 * 3 = 19 points
    # Insulin: 1 correct option selected -> 10 points
    # Others: 0 correct options selected -> 0 points
    # Total score = 16 + 19 + 10 = 45 points (pending coach review)
    answers = {
        "Estrogen": [
            "Strength training",
            "Eating cruciferous vegetables"
        ],
        "Progesterone": [
            "Breathwork and meditation",
            "Consuming zinc",
            "Limiting alcohol intake"
        ],
        "Insulin": [
            "Fiber-first eating"
        ],
        "Cortisol": [],
        "LH_FSH": [],
        "Melatonin": []
    }

    payload = {
        "name": "Diana",
        "age": 45,
        "gender": "female",
        "perimenopause_status": "yes",
        "answers": answers
    }
    message = types.Content(role="user", parts=[types.Part.from_text(text=json.dumps(payload))])
    events = list(runner.run(new_message=message, user_id="test_user", session_id=session.id))
    
    interrupted = False
    interrupt_id = None
    for event in events:
        if has_request_input_function_call(event):
            interrupted = True
            ids = get_request_input_interrupt_ids(event)
            if ids:
                interrupt_id = ids[0]
                break

    assert interrupted is True
    assert interrupt_id == "coach_note"

    response_part = create_request_input_response(interrupt_id, {"coach_note": "Good start!"})
    resume_message = types.Content(role="user", parts=[response_part])
    
    resume_events = list(runner.run(new_message=resume_message, user_id="test_user", session_id=session.id))
    report = get_final_report(resume_events)
    
    assert report is not None
    assert report["eligible"] is True
    assert report["score"] == 45

def test_database_email_registration_and_helpers() -> None:
    from app.database import register_user, authenticate_user, get_user_email
    import uuid
    
    unique_username = f"user_{uuid.uuid4().hex[:8]}"
    email = f"{unique_username}@example.com"
    
    # 1. Register user with email
    reg_res = register_user(
        username=unique_username,
        password="test_password",
        email=email,
        name="Test User",
        age=40,
        gender="female",
        perimenopause_status="yes"
    )
    assert reg_res["success"] is True
    user_id = reg_res["user_id"]
    assert user_id > 0
    
    # 2. Authenticate user and verify email is returned
    auth_res = authenticate_user(unique_username, "test_password")
    assert auth_res["success"] is True
    assert auth_res["user"]["email"] == email
    
    # 3. Retrieve user email using get_user_email helper
    retrieved_email = get_user_email(user_id)
    assert retrieved_email == email

def test_coach_authentication_and_verification() -> None:
    import os
    from app.database import authenticate_user, verify_coach_credentials, register_user
    import uuid
    
    coach_user = os.getenv("COACH_USERNAME", "health_coach")
    coach_pass = os.getenv("COACH_PASSWORD", "CoachSecure2026!")
    
    # 1. Authenticate standard user and verify they are NOT coach
    unique_username = f"user_{uuid.uuid4().hex[:8]}"
    register_user(
        username=unique_username,
        password="test_password",
        email="test@example.com",
        name="Regular User",
        age=40,
        gender="female",
        perimenopause_status="yes"
    )
    auth_user = authenticate_user(unique_username, "test_password")
    assert auth_user["success"] is True
    assert auth_user["user"]["is_coach"] is False
    assert verify_coach_credentials(unique_username, "test_password") is False

    # 2. Authenticate configured coach and verify they ARE coach
    auth_coach = authenticate_user(coach_user, coach_pass)
    assert auth_coach["success"] is True
    assert auth_coach["user"]["is_coach"] is True
    assert verify_coach_credentials(coach_user, coach_pass) is True

def test_yesterday_logging_and_validation() -> None:
    from app.database import register_user, save_daily_log, get_user_logs
    import uuid
    
    unique_username = f"user_{uuid.uuid4().hex[:8]}"
    
    # 1. Register user
    reg = register_user(unique_username, "password123", "email@test.com", "Name", 40, "female", "yes")
    assert reg["success"] is True
    uid = reg["user_id"]
    
    # 2. Try duplicate registration
    reg_dup = register_user(unique_username, "password123", "email@test.com", "Name", 40, "female", "yes")
    assert reg_dup["success"] is False
    assert "exists" in reg_dup["error"]
    
    # 3. Test saving a log for yesterday
    yesterday_date = "2026-06-30"
    success = save_daily_log(uid, yesterday_date, 60, {"Estrogen": ["Strength training"]}, ["Smile!"], "Keep going")
    assert success is True
    
    # 4. Retrieve log and verify date
    logs = get_user_logs(uid)
    assert len(logs) == 1
    assert logs[0]["date"] == yesterday_date
    assert logs[0]["score"] == 60


def test_human_in_loop_endpoints() -> None:
    from fastapi.testclient import TestClient
    from app.fast_api_app import app, pending_reviews, active_sessions
    import os
    
    client = TestClient(app)
    
    session_id = "test_hitl_session"
    pending_reviews[session_id] = {
        "session_id": session_id,
        "user_id": "test_user_uid",
        "name": "Test User",
        "age": 45,
        "gender": "female",
        "interrupt_id": "dummy_interrupt",
        "answers": {},
        "date": "2026-07-01"
    }
    
    coach_user = os.getenv("COACH_USERNAME", "health_coach")
    coach_pass = os.getenv("COACH_PASSWORD", "CoachSecure2026!")
    
    # Test negative: unauthorized access to get pending reviews
    res_unauth = client.get("/api/pending", headers={})
    assert res_unauth.status_code == 403
    
    # Test negative: unauthorized coach review submission
    res_unauth_submit = client.post(f"/api/coach-review/{session_id}", json={"coach_note": "Great!"})
    assert res_unauth_submit.status_code == 403
    
    # Test positive: fetch pending reviews as coach
    headers = {
        "X-Coach-Username": coach_user,
        "X-Coach-Password": coach_pass
    }
    res_pending = client.get("/api/pending", headers=headers)
    assert res_pending.status_code == 200
    
    # Test negative: Submit review for invalid session
    res_invalid_session = client.post("/api/coach-review/invalid_sess", json={"coach_note": "hi"}, headers=headers)
    assert res_invalid_session.status_code == 404


def test_api_status_endpoint() -> None:
    from fastapi.testclient import TestClient
    from app.fast_api_app import app, active_sessions
    
    client = TestClient(app)
    
    # 1. Negative: non-existent session
    res = client.get("/api/status/invalid_session_here")
    assert res.status_code == 404
    
    # 2. Positive: existing session
    active_sessions["test_status_sess"] = {"status": "completed", "data": {"score": 60}}
    res2 = client.get("/api/status/test_status_sess")
    assert res2.status_code == 200
    assert res2.json()["status"] == "completed"
