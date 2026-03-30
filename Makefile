PYTHON ?= python3
PROFILE ?= robotics_platform_validation
TITLE ?= Senior Platform Engineer
COMPANY ?= Debug Company
LOCATION ?= Toronto, ON, Canada
REMOTE ?= Remote Canada
URL ?= https://example.com/jobs/debug
DESCRIPTION ?= Build platform infrastructure with Kubernetes, Terraform, AWS, Prometheus, Grafana, and GitHub Actions.
SEED_URL ?=
TERMS ?=
LOG_LEVEL ?= INFO

.PHONY: help install init-db status console backend frontend compile runtime profile-summary debug-score scrape-seed scrape-terms

help:
	@printf "\nTargets:\n"
	@printf "  install          Install project dependencies in editable mode\n"
	@printf "  init-db          Recreate and initialize the database\n"
	@printf "  status           Show collector/runtime status\n"
	@printf "  console          Run backend + frontend together\n"
	@printf "  backend          Run FastAPI backend only\n"
	@printf "  frontend         Run Streamlit frontend only\n"
	@printf "  compile          Compile-check Python modules\n"
	@printf "  runtime          Print runtime and active-profile summary\n"
	@printf "  profile-summary  Alias for runtime\n"
	@printf "  debug-score      Run a local scoring/debug pass for one sample job\n"
	@printf "  scrape-seed      Scrape one seed URL (set SEED_URL=...)\n"
	@printf "  scrape-terms     Scrape by explicit terms (set TERMS='foo bar baz')\n"
	@printf "\nUseful vars:\n"
	@printf "  PROFILE=%s\n" "$(PROFILE)"
	@printf "  LOG_LEVEL=%s\n" "$(LOG_LEVEL)"
	@printf "  TITLE=... COMPANY=... LOCATION=... REMOTE=... DESCRIPTION=...\n"
	@printf "  SEED_URL=https://...\n"
	@printf "  TERMS='platform engineer site reliability engineer'\n\n"

install:
	$(PYTHON) -m pip install --user -e .

init-db:
	$(PYTHON) -m collector init-db

status:
	$(PYTHON) -m collector status --profile $(PROFILE)

console:
	$(PYTHON) run_console.py

backend:
	$(PYTHON) -m uvicorn console.backend.app.main:app --host 127.0.0.1 --port 8000

frontend:
	JOB_CONSOLE_API_BASE_URL=http://127.0.0.1:8000 $(PYTHON) -m streamlit run console/frontend/streamlit_app.py --server.address 127.0.0.1 --server.port 8501

compile:
	$(PYTHON) -m compileall collector console shared scripts run_console.py

runtime:
	$(PYTHON) scripts/show_runtime.py

profile-summary: runtime

debug-score:
	$(PYTHON) scripts/debug_score.py --profile $(PROFILE) --title "$(TITLE)" --company "$(COMPANY)" --location "$(LOCATION)" --remote "$(REMOTE)" --url "$(URL)" --description "$(DESCRIPTION)"

scrape-seed:
	@if [ -z "$(SEED_URL)" ]; then echo "Set SEED_URL=https://..."; exit 1; fi
	$(PYTHON) -m collector scrape --profile $(PROFILE) --seed-url "$(SEED_URL)" --log-level $(LOG_LEVEL)

scrape-terms:
	@if [ -z "$(TERMS)" ]; then echo "Set TERMS='platform engineer site reliability engineer'"; exit 1; fi
	$(PYTHON) -m collector scrape --profile $(PROFILE) --terms $(TERMS) --log-level $(LOG_LEVEL)
