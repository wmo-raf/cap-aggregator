# Compose stacks: production base + dev overlay
DC = docker compose -f docker-compose.yml
DEV_DC = docker compose -f docker-compose.yml -f docker-compose.dev.yml

APP = capagg-app
WORKER_DEFAULT = capagg-worker-default
WORKER_INGESTION = capagg-worker-ingestion
BEAT = capagg-beat
CONSUMER = capagg-mqtt-consumer

MANAGE = capagg

.PHONY: build up up-d down stop restart ps config logs app-logs shell migrate makemigrations \
	createsuperuser collectstatic sync-mosquitto create-tile-function \
	dev-build dev-up dev-up-d dev-down dev-stop dev-restart dev-ps dev-config dev-logs \
	dev-app-logs dev-worker-default-logs dev-worker-ingestion-logs dev-beat-logs dev-consumer-logs \
	dev-shell dev-worker-default-shell dev-worker-ingestion-shell \
	dev-migrate dev-makemigrations dev-createsuperuser dev-sync-mosquitto dev-create-tile-function dev-test \
	dev-test-js dev-vite-logs

# ======================
# PRODUCTION
# ======================

build:
	$(DC) build

up:
	$(DC) up -d

down:
	$(DC) down

stop:
	$(DC) stop

restart:
	$(DC) restart

ps:
	$(DC) ps

config:
	$(DC) config

logs:
	$(DC) logs -f $(LOG_ARGS)

app-logs:
	$(DC) logs -f $(APP) $(LOG_ARGS)

shell:
	$(DC) exec $(APP) bash

migrate:
	$(DC) exec $(APP) $(MANAGE) migrate

makemigrations:
	$(DC) exec $(APP) $(MANAGE) makemigrations

createsuperuser:
	$(DC) exec $(APP) $(MANAGE) createsuperuser

collectstatic:
	$(DC) exec $(APP) $(MANAGE) collectstatic --noinput

# Bootstrap/repair only — auth files sync automatically on SourceAuthority save,
# and the broker self-reloads when they change
sync-mosquitto:
	$(DC) exec $(APP) $(MANAGE) sync_mosquitto

create-tile-function:
	$(DC) exec $(APP) $(MANAGE) create_alerts_tile_function

# ======================
# DEV
# ======================

dev-build:
	$(DEV_DC) build

dev-up:
	$(DEV_DC) up

dev-up-d:
	$(DEV_DC) up -d

dev-down:
	$(DEV_DC) down

dev-stop:
	$(DEV_DC) stop

dev-restart:
	$(DEV_DC) restart

dev-ps:
	$(DEV_DC) ps

dev-config:
	$(DEV_DC) config

dev-logs:
	$(DEV_DC) logs -f $(LOG_ARGS)

dev-app-logs:
	$(DEV_DC) logs -f $(APP) $(LOG_ARGS)

dev-worker-default-logs:
	$(DEV_DC) logs -f $(WORKER_DEFAULT)

dev-worker-ingestion-logs:
	$(DEV_DC) logs -f $(WORKER_INGESTION)

dev-beat-logs:
	$(DEV_DC) logs -f $(BEAT)

dev-consumer-logs:
	$(DEV_DC) logs -f $(CONSUMER)

dev-shell:
	$(DEV_DC) exec $(APP) bash

dev-worker-default-shell:
	$(DEV_DC) exec $(WORKER_DEFAULT) bash

dev-worker-ingestion-shell:
	$(DEV_DC) exec $(WORKER_INGESTION) bash

dev-migrate:
	$(DEV_DC) exec $(APP) $(MANAGE) migrate

dev-makemigrations:
	$(DEV_DC) exec $(APP) $(MANAGE) makemigrations

dev-createsuperuser:
	$(DEV_DC) exec $(APP) $(MANAGE) createsuperuser

dev-sync-mosquitto:
	$(DEV_DC) exec $(APP) $(MANAGE) sync_mosquitto

dev-create-tile-function:
	$(DEV_DC) exec $(APP) $(MANAGE) create_alerts_tile_function

dev-test:
	@export $$(grep -v '^[[:space:]]*#' .env | grep -v '^[[:space:]]*$$' | grep -v '^UID=' | xargs) && \
	$(DEV_DC) exec \
	  -e "DATABASE_URL=postgis://$$DB_USER:$$DB_PASSWORD@capagg-db:5432/$$DB_NAME" \
	  $(APP) $(MANAGE) test --keepdb $(TEST_ARGS)

# Vitest (explorer SPA) — companion to dev-test
dev-test-js:
	$(DEV_DC) run --rm capagg-vite sh -c "npm install && npm test"

dev-vite-logs:
	$(DEV_DC) logs -f capagg-vite
