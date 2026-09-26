.PHONY: install dev backend frontend test lint format eval eval-list eval-publish validation-image

install:
	cd backend && uv sync
	cd frontend && npm install

dev:
	@echo "Run 'make backend' and 'make frontend' in separate terminals"

backend:
	cd backend && uv run uvicorn orod.main:app --reload

frontend:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest
	cd frontend && npm test -- --run

lint:
	cd backend && uv run ruff check src tests evals containers ../scripts/verify_ollama.py && uv run mypy src evals
	cd frontend && npm run lint

format:
	cd backend && uv run ruff format src tests evals

# Replay the controlled vulnerability corpus. Override MODELS to compare models, e.g.
#   make eval MODELS="--model qwen2.5-coder:14b --model claude-opus-5"
MODELS ?=
EVAL_ARGS ?=

eval:
	cd backend && uv run python -m evals run $(MODELS) $(EVAL_ARGS)

eval-list:
	cd backend && uv run python -m evals list

eval-publish:
	cd backend && uv run python -m evals run $(MODELS) $(EVAL_ARGS) --publish

validation-image:
	docker build -t orod-validation:local backend/containers/validation
