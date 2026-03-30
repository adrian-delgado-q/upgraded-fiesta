# upgraded-fiesta

Role-agnostic job collection and scoring framework.

Commands:

- `python -m collector init-db`
- `python -m collector status`
- `python -m collector scrape --seed-url <url>`
- `python run_console.py`
- `make help`

Console setup:

- `python -m pip install --user -e .`
- `python -m collector init-db`
- `python run_console.py`

Convenience targets:

- `make install`
- `make init-db`
- `make status`
- `make console`
- `make runtime`
- `make debug-score TITLE="Senior Platform Engineer" DESCRIPTION="Build platform infrastructure with Kubernetes and Terraform."`

This starts:

- FastAPI backend at `http://127.0.0.1:8000`
- Streamlit frontend at `http://127.0.0.1:8501`
