run:
	uv run uvicorn app.fast_api_app:app --host 127.0.0.1 --port 8080 --reload

test:
	uv run pytest tests/

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

generate-traces:
	uv run python tests/eval/generate_traces.py

grade:
	uv run agents-cli eval grade

eval: generate-traces grade
