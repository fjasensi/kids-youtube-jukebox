APP_URL ?= http://127.0.0.1:8000
APP_PORT ?= 8000
APP_CONTAINER ?= youtube-kids-jukebox_jukebox_1
DB_CONTAINER ?= youtube-kids-jukebox_db_1
COMPOSE ?= podman compose
PYTHON ?= .venv/bin/python
TAIL ?= 80

.DEFAULT_GOAL := help

.PHONY: help
help:
	@printf '%s\n' 'Safe commands for the running Podman jukebox:'
	@printf '%s\n' ''
	@printf '%s\n' '  make status           Show containers, health, and the published port'
	@printf '%s\n' '  make preflight        Show runtime state before a deploy'
	@printf '%s\n' '  make health           Check the deployed app health endpoint'
	@printf '%s\n' '  make port-check       Show who is listening on port 8000'
	@printf '%s\n' '  make logs             Show recent app logs'
	@printf '%s\n' '  make logs-follow      Follow app logs'
	@printf '%s\n' '  make db-logs          Show recent PostgreSQL logs'
	@printf '%s\n' '  make verify           Verify app, database, logs, and port after changes'
	@printf '%s\n' '  make test             Run local unit tests without starting a server'
	@printf '%s\n' '  make check            Run syntax checks and unit tests'
	@printf '%s\n' '  make deploy-app       Build and deploy only the jukebox app service'
	@printf '%s\n' '  make favorites-schema Read-only check of favorite_tracks profile schema'
	@printf '%s\n' '  make favorites-count  Read-only count of saved favorites'

.PHONY: ps
ps:
	podman ps -a

.PHONY: health
health:
	curl -fsS $(APP_URL)/health
	@printf '\n'

.PHONY: port-check
port-check:
	lsof -nP -iTCP:$(APP_PORT) -sTCP:LISTEN

.PHONY: logs
logs:
	podman logs --tail $(TAIL) $(APP_CONTAINER)

.PHONY: logs-follow
logs-follow:
	podman logs -f --tail $(TAIL) $(APP_CONTAINER)

.PHONY: db-logs
db-logs:
	podman logs --tail $(TAIL) $(DB_CONTAINER)

.PHONY: status
status: ps health port-check

.PHONY: preflight
preflight: ps
	-curl -fsS $(APP_URL)/health
	@printf '\n'
	$(MAKE) port-check

.PHONY: verify
verify: health ps port-check logs

.PHONY: py-compile
py-compile:
	$(PYTHON) -m py_compile app/main.py app/history.py app/models.py app/database.py app/profiles.py tests/test_app.py

.PHONY: js-check
js-check:
	node --check app/static/app.js

.PHONY: test
test:
	$(PYTHON) -m unittest -v

.PHONY: check
check: py-compile js-check test

.PHONY: deploy-app
deploy-app: preflight
	$(COMPOSE) up --build -d --no-deps jukebox
	$(MAKE) verify

.PHONY: favorites-schema
favorites-schema:
	podman exec $(DB_CONTAINER) psql -U jukebox -d jukebox -c "select column_name, is_nullable, column_default from information_schema.columns where table_name = 'favorite_tracks' and column_name in ('profile_id', 'video_id') order by column_name;"
	podman exec $(DB_CONTAINER) psql -U jukebox -d jukebox -c "select conname from pg_constraint where conrelid = 'favorite_tracks'::regclass and contype = 'u' order by conname;"

.PHONY: favorites-count
favorites-count:
	podman exec $(DB_CONTAINER) psql -U jukebox -d jukebox -c "select count(*) as favorites from favorite_tracks;"
