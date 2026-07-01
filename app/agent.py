import json
import os
import sys
from typing import Any
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.workflow import START, Edge, Workflow, node
from google.genai import Client, types
from pydantic import BaseModel, Field

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import HORMONE_ACTIVITIES, MODEL_NAME

load_dotenv()

# Set up Gemini Client
client = Client()

class OnboardingData(BaseModel):
    name: str = Field(description="Name of the user")
    age: int = Field(description="Age of the user")
    gender: str = Field(description="Gender of the user")
    perimenopause_status: str = Field(description="Is the user experiencing perimenopause? (yes/no)")
    answers: dict[str, Any] = Field(description="Selected answers for each hormone")

@node
def parse_input(ctx: Context, node_input: Any) -> Event:
    """Parses user questionnaire input and stores it in the workflow state."""
    data = None
    text = ""
    
    if isinstance(node_input, dict):
        data = node_input
    elif isinstance(node_input, str):
        text = node_input
    elif hasattr(node_input, "parts") and node_input.parts:
        text = node_input.parts[0].text
    elif hasattr(node_input, "text") and node_input.text:
        text = node_input.text
    else:
        text = str(node_input)

    if not data:
        try:
            data = json.loads(text)
        except Exception:
            try:
                # Unescape double-escaped JSON (e.g. from datasets)
                cleaned = text.replace('\\"', '"').replace('\\\\"', '"')
                data = json.loads(cleaned)
            except Exception:
                data = {"name": "Guest", "age": 0, "gender": "unknown", "perimenopause_status": "no", "answers": {}}

    onboarding = OnboardingData(
        name=data.get("name", "Guest"),
        age=int(data.get("age", 0)),
        gender=data.get("gender", "unknown"),
        perimenopause_status=data.get("perimenopause_status", "no"),
        answers=data.get("answers", {})
    )
    
    ctx.state["name"] = onboarding.name
    ctx.state["age"] = onboarding.age
    ctx.state["gender"] = onboarding.gender
    ctx.state["perimenopause_status"] = onboarding.perimenopause_status
    ctx.state["answers"] = onboarding.answers
    
    return Event(output=onboarding)

@node
def check_eligibility(ctx: Context, node_input: OnboardingData) -> Event:
    """Verifies if the user fits the perimenopausal target group (Female, Age >= 35)."""
    age = node_input.age
    gender = node_input.gender.lower()
    peri = node_input.perimenopause_status.lower()

    if age <= 0:
        ctx.state["eligibility_error"] = "Age cannot be zero or negative."
        return Event(output=node_input, route="ineligible")
    elif gender == "male":
        ctx.state["eligibility_error"] = "PeriMeter AI is designed for individuals of female biology."
        return Event(output=node_input, route="ineligible")
    elif age < 35:
        ctx.state["eligibility_error"] = "PeriMeter AI is optimized for ages 35+."
        return Event(output=node_input, route="ineligible")
    elif peri != "yes":
        ctx.state["eligibility_error"] = "PeriMeter AI is designed for those experiencing perimenopause."
        return Event(output=node_input, route="ineligible")

    ctx.state["eligible"] = True
    return Event(output=node_input, route="eligible")

async def fetch_hormone_guidelines_from_mcp() -> dict[str, str]:
    try:
        python_exe = sys.executable or "python"
        server_path = os.path.join(os.path.dirname(__file__), "mcp_server.py")
        server_params = StdioServerParameters(
            command=python_exe,
            args=[server_path]
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.call_tool("get_hormone_guidelines", {})
                if response and len(response) > 0 and response[0].text:
                    return json.loads(response[0].text)
    except Exception:
        pass
    
    # Fallback to local config correct activity descriptions
    fallback = {}
    for h, data in HORMONE_ACTIVITIES.items():
        correct_desc = next((o["text"] for o in data["options"] if o["correct"]), "balance activities")
        fallback[h] = correct_desc
    return fallback

@node
async def calculate_score(ctx: Context, node_input: OnboardingData) -> Event:
    """Calculates daily score based on correct/incorrect activities."""
    answers = node_input.answers
    score = 0
    correct_hormones = []
    incorrect_hormones = []
    
    # Fetch guidelines from MCP server
    mcp_guidelines = await fetch_hormone_guidelines_from_mcp()
    
    for hormone, selected_val in answers.items():
        if isinstance(selected_val, str):
            selected_list = [selected_val]
        elif isinstance(selected_val, list):
            selected_list = selected_val
        else:
            selected_list = []

        if hormone in HORMONE_ACTIVITIES:
            hormone_correct_options = []
            hormone_incorrect_options = []
            
            for activity_text in selected_list:
                matched_option = None
                for opt in HORMONE_ACTIVITIES[hormone]["options"]:
                    if opt["text"] == activity_text:
                        matched_option = opt
                        break
                
                if matched_option:
                    if matched_option["correct"]:
                        hormone_correct_options.append(activity_text)
                    else:
                        hormone_incorrect_options.append(activity_text)
            
            # If user selects more than one option for the same hormone:
            # - First correct option gets 10 points
            # - Other correct options get 3 points each
            # - Incorrect options get -5 points each
            if hormone_correct_options:
                score += 10
                score += (len(hormone_correct_options) - 1) * 3
                correct_hormones.append(hormone)
            
            if hormone_incorrect_options:
                score += len(hormone_incorrect_options) * (-5)
                if hormone not in correct_hormones:
                    incorrect_hormones.append(hormone)
                    
            if not selected_list:
                incorrect_hormones.append(hormone)

    ctx.state["score"] = score
    ctx.state["correct_hormones"] = correct_hormones
    ctx.state["incorrect_hormones"] = incorrect_hormones
    ctx.state["mcp_guidelines"] = mcp_guidelines

    if score >= 50:
        return Event(output=node_input, route="high_score")
    else:
        return Event(output=node_input, route="low_score")

@node(rerun_on_resume=True)
def request_coach_input(ctx: Context, node_input: OnboardingData):
    """Yields a human-in-the-loop request for a health coach to review the low score and add encouragement."""
    score = ctx.state.get("score", 0)
    incorrect = ctx.state.get("incorrect_hormones", [])
    
    # Check if we already received coach's note
    if not ctx.resume_inputs or "coach_note" not in ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="coach_note",
            message=(
                f"📋 HITL COACH REVIEW REQUIRED\n"
                f"User: {ctx.state.get('name')} (Age: {ctx.state.get('age')})\n"
                f"Score: {score}/60\n"
                f"Hormones needing support: {', '.join(incorrect) if incorrect else 'None'}\n\n"
                f"Please provide custom coach encouragement notes to help motivate them:"
            )
        )
        return

    raw_note = ctx.resume_inputs["coach_note"]
    if isinstance(raw_note, dict):
        ctx.state["coach_note"] = raw_note.get("coach_note", "") or raw_note.get("result", "")
    else:
        ctx.state["coach_note"] = raw_note
    yield Event(output=node_input)

@node
def finalize_report(ctx: Context, node_input: Any) -> Event:
    """Generates Gemini motivational content and compiles the final report."""
    eligible = ctx.state.get("eligible", False)
    
    if not eligible:
        report = {
            "eligible": False,
            "error_message": ctx.state.get("eligibility_error", "Not eligible."),
            "score": 0,
            "jokes": [],
            "girl_talk": "",
            "coach_note": ""
        }
        yield Event(
            content=types.Content(role="model", parts=[types.Part.from_text(text=json.dumps(report))])
        )
        yield Event(output=report)
        return

    score = ctx.state.get("score", 0)
    name = ctx.state.get("name", "Friend")
    incorrect = ctx.state.get("incorrect_hormones", [])
    correct = ctx.state.get("correct_hormones", [])
    coach_note = ctx.state.get("coach_note", "")

    # Construct LLM prompt based on score
    if score >= 50:
        prompt = (
            f"Write a single clean, lighthearted joke or pun about healthy hormones, balance, or self-care to make a perimenopausal woman named {name} smile.\n"
            f"Format the output strictly as a JSON list of strings containing exactly 1 element, e.g. [\"Why did the estrogen go to the gym? To lift her spirits!\"]"
        )
        girl_talk = f"Amazing job, {name}! You scored a {score}/60 today. Keep up these wonderful habits to stay in balance!"
    else:
        mcp_guidelines = ctx.state.get("mcp_guidelines", {})
        guidelines = []
        for h in incorrect:
            correct_desc = mcp_guidelines.get(h, "balance activities")
            guidelines.append(f"- {h}: Focus on {correct_desc}")
                
        prompt = (
            f"Write exactly 2 clean, funny, and lighthearted jokes or puns about hormones, sleep, or women's midlife struggles to cheer up a perimenopausal woman named {name}.\n"
            f"Format the output strictly as a JSON list of strings containing exactly 2 elements, e.g. [\"Joke 1\", \"Joke 2\"]"
        )
        girl_talk = (
            f"Hey sis, we've all been there! Balancing hormones is a journey, not a destination. "
            f"Today we scored {score}/60. To help support your body tomorrow, here are a few gentle reminders:\n"
            + "\n".join(guidelines) +
            "\n\nYou've got this! We're in this together."
        )

    # Call Gemini to get the jokes
    jokes = []
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        jokes = json.loads(response.text)
    except Exception as e:
        # Fallback jokes if API call fails
        if score >= 50:
            jokes = ["What do hormones and a good joke have in common? They both need perfect timing!"]
        else:
            jokes = [
                "My mood swings have got mood swings today!",
                "I'm not having a hot flash, I'm just heating up the room with my presence!"
            ]

    report = {
        "eligible": True,
        "name": name,
        "age": ctx.state.get("age"),
        "gender": ctx.state.get("gender"),
        "score": score,
        "correct_hormones": correct,
        "incorrect_hormones": incorrect,
        "jokes": jokes,
        "girl_talk": girl_talk,
        "coach_note": coach_note
    }

    yield Event(
        content=types.Content(role="model", parts=[types.Part.from_text(text=json.dumps(report))])
    )
    yield Event(output=report)

# Define graph topology
root_agent = Workflow(
    name="perimeter_agent",
    description="PeriMeter AI agent that calculates scores, requests coach comments, and generates motivational jokes.",
    edges=[
        Edge(from_node=START, to_node=parse_input),
        Edge(from_node=parse_input, to_node=check_eligibility),
        Edge(from_node=check_eligibility, to_node=finalize_report, route="ineligible"),
        Edge(from_node=check_eligibility, to_node=calculate_score, route="eligible"),
        Edge(from_node=calculate_score, to_node=finalize_report, route="high_score"),
        Edge(from_node=calculate_score, to_node=request_coach_input, route="low_score"),
        Edge(from_node=request_coach_input, to_node=finalize_report),
    ],
)

app = App(
    root_agent=root_agent,
    name="perimeter_agent",
)
