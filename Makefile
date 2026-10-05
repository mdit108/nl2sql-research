PY ?= .venv/bin/python
PSQL ?= psql

.PHONY: venv db-init migrate data index ground-truth setup test selftest pilot compare api

venv:
	python3.12 -m venv .venv && $(PY) -m pip install -e ".[dev]"

db-init:            ## create roles, database and pgvector (needs a superuser)
	$(PSQL) -v ON_ERROR_STOP=1 -d postgres -f scripts/init_db.sql

migrate:
	.venv/bin/alembic upgrade head

data:               ## download, load and validate the Olist dataset
	$(PY) scripts/download_data.py
	$(PY) scripts/load_data.py
	$(PY) scripts/validate_data.py

index:              ## embed semantic/*.yaml into pgvector
	$(PY) scripts/index_knowledge.py

ground-truth:
	$(PY) -m evaluation.ground_truth

setup: db-init migrate data index ground-truth

test:
	$(PY) -m pytest -q

selftest:           ## gold SQL through the whole pipeline must score 100%
	$(PY) -m evaluation.run --llm gold-sql --name selftest --repeats 1

pilot:              ## E0-E6 retrieved + E4-E6 gold, 3 repeats, then the report
	$(PY) -m evaluation.run --conditions E0,E1,E2,E3,E4,E5,E6,E4-gold,E5-gold,E6-gold --repeats 3
	$(PY) -m evaluation.compare

compare:
	$(PY) -m evaluation.compare

api:
	.venv/bin/uvicorn app.api.main:app --reload
