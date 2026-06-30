import sys
import os
import json
import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

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

def get_final_response(events):
    for event in reversed(events):
        if event.content and event.content.parts:
            texts = [p.text for p in event.content.parts if p.text]
            if texts:
                return {
                    "role": event.content.role or "model",
                    "parts": [{"text": "".join(texts)}]
                }
    return None

def decode_bytes(obj):
    if isinstance(obj, bytes):
        try:
            return obj.decode('utf-8')
        except UnicodeDecodeError:
            import base64
            return base64.b64encode(obj).decode('utf-8')
    elif isinstance(obj, dict):
        return {k: decode_bytes(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decode_bytes(x) for x in obj]
    return obj

def main():
    dataset_path = PROJECT_ROOT / "tests" / "eval" / "datasets" / "basic-dataset.json"
    output_path = PROJECT_ROOT / "artifacts" / "traces" / "generated_traces.json"

    print(f"Loading dataset from {dataset_path}...")
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    cases = data.get("eval_cases", [])
    print(f"Loaded {len(cases)} cases.")

    session_service = InMemorySessionService()

    generated_cases = []
    for i, case in enumerate(cases):
        case_id = case.get("eval_case_id")
        prompt_content = case.get("prompt")
        prompt_text = prompt_content["parts"][0]["text"]
        print(f"\n[{i+1}/{len(cases)}] Running case: {case_id}")

        session = session_service.create_session_sync(user_id="eval_user", app_name="perimeter_agent")
        runner = Runner(agent=root_agent, session_service=session_service, app_name="perimeter_agent")

        user_message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt_text)]
        )

        events = list(
            runner.run(
                new_message=user_message,
                user_id="eval_user",
                session_id=session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        )

        all_events = list(events)

        # Check for interruption
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
            # Low score case gets automated coach review comments
            coach_note = "Great effort! Focus on breathing exercises and limiting coffee in the afternoon."
            print(f"  [HITL Interrupted] Providing coach note: {coach_note}")
            
            response_part = create_request_input_response(interrupt_id, {"coach_note": coach_note})
            resume_message = types.Content(role="user", parts=[response_part])
            
            resume_events = list(
                runner.run(
                    new_message=resume_message,
                    user_id="eval_user",
                    session_id=session.id,
                    run_config=RunConfig(streaming_mode=StreamingMode.SSE),
                )
            )
            all_events.extend(resume_events)

        # Format events for trace output
        turn_events = []
        turn_events.append({
            "author": "user",
            "content": {
                "role": "user",
                "parts": [{"text": prompt_text}]
            }
        })

        for event in all_events:
            if event.content:
                event_dict = {
                    "author": event.author or event.node_info.output_for[0].split("/")[-1] if (event.node_info and event.node_info.output_for) else "model",
                    "content": event.content.model_dump(exclude_none=True),
                }
                if event.timestamp:
                    event_dict["event_time"] = datetime.datetime.fromtimestamp(event.timestamp, datetime.timezone.utc).isoformat().replace("+00:00", "Z")
                turn_events.append(event_dict)

        final_response = get_final_response(all_events)

        eval_case_dict = {
            "eval_case_id": case_id,
            "prompt": prompt_content,
            "agent_data": {
                "turns": [
                    {
                        "turn_index": 0,
                        "turn_id": "turn_0",
                        "events": turn_events
                    }
                ]
            }
        }
        if final_response:
            eval_case_dict["responses"] = [{"response": final_response}]

        generated_cases.append(eval_case_dict)
        print(f"  Completed case {case_id}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"eval_cases": decode_bytes(generated_cases)}, f, indent=2)
    print(f"\nSuccessfully wrote traces to {output_path}")

if __name__ == "__main__":
    main()
