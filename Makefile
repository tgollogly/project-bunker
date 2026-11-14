# Project Bunker — Copyright © 2026 Thomas Gollogly
.PHONY: init ingest-demo ingest-all sync query status verify test lint mesh-listen mesh-alert docker-up

PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

init:
	@bash scripts/init.sh

ingest-demo: init
	@$(BIN)/bunker ingest --source usgs_earthquakes_day

ingest-all: init
	@$(BIN)/bunker ingest-all

ingest-offline: init
	@$(BIN)/bunker ingest-all --offline

sync: init
	@$(BIN)/bunker sync-package

query: init
	@$(BIN)/bunker query "SELECT COUNT(*) AS events FROM bunker_data"

status: init
	@$(BIN)/bunker status

verify:
	@test -n "$(SYNC)" || (echo "Usage: make verify SYNC=./bunker_sync_YYYY-MM-DD" && exit 1)
	@$(BIN)/bunker verify-sync "$(SYNC)"

test: init
	@$(BIN)/pytest

lint: init
	@$(BIN)/ruff check src tests

mesh-listen:
	@$(BIN)/python -m bunker.comms.udp_broadcast listen

mesh-alert:
	@test -n "$(MSG)" || (echo 'Usage: make mesh-alert MSG="sync ready on USB 3"' && exit 1)
	@$(BIN)/python -m bunker.comms.udp_broadcast send "$(MSG)"

docker-up:
	@docker compose up --build -d

blackout:
	@bash scripts/blackout-recovery.sh