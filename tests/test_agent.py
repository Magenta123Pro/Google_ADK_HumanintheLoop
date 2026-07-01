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

    # Select 3 correct, 3 incorrect answers
    answers = {}
    hormones = list(HORMONE_ACTIVITIES.keys())
    for i, h in enumerate(hormones):
        data = HORMONE_ACTIVITIES[h]
        if i < 3:
            correct_opt = next(o["text"] for o in data["options"] if o["correct"])
            answers[h] = correct_opt
        else:
            incorrect_opt = next(o["text"] for o in data["options"] if not o["correct"])
            answers[h] = incorrect_opt

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
    assert report["score"] == 15  # 3 * 10 - 3 * 5 = 15
    assert len(report["jokes"]) == 2
    assert "aim to do stretching" in report["coach_note"].lower()
    assert "Cortisol" in report["girl_talk"] or "Melatonin" in report["girl_talk"] or "LH_FSH" in report["girl_talk"]

def test_multiple_options_scoring() -> None:
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="perimeter_agent")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="perimeter_agent")

    # For Estrogen: select 1 correct option and 1 incorrect option (scores 10 - 5 = 5 points)
    # For Progesterone: select 1 correct option (scores 10 points)
    # Others: select nothing (scores 0 points and counts as incorrect)
    answers = {
        "Estrogen": [
            "Strength training or eating cruciferous vegetables", # correct
            "Deep breathing exercises for 10 minutes"       # incorrect
        ],
        "Progesterone": [
            "Breathwork/meditation, zinc, or limiting alcohol"    # correct
        ],
        "Insulin": [],
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
    
    # Estrogen: 10 - 5 = 5
    # Progesterone: 10
    # Total expected score = 5 + 10 = 15
    assert report is not None
    assert report["eligible"] is True
    assert report["score"] == 15
