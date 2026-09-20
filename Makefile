# docker login -u jonhayes37
.PHONY: upgrade-deps upgrade-deps-dry-run

IMAGE := jonhayes37/iu-bot
# Every push is also tagged with the commit, so a bad release can be rolled back to a known tag.
VERSION := $(shell git rev-parse --short HEAD)

# Re-pins every outdated direct dependency (runtime and dev), then refreshes the transitive ones.
upgrade-deps:
	python3 scripts/upgrade_dependencies.py

# Only list what upgrade-deps would change.
upgrade-deps-dry-run:
	python3 scripts/upgrade_dependencies.py --dry-run

ensure-docker:
	@docker info >/dev/null 2>&1 || colima start

build-push: ensure-docker
	docker build --platform linux/amd64 -t iu-bot .
	docker tag iu-bot $(IMAGE)
	docker tag iu-bot $(IMAGE):$(VERSION)
	docker push $(IMAGE)
	docker push $(IMAGE):$(VERSION)
	@echo "Pushed $(IMAGE):latest and $(IMAGE):$(VERSION)"
