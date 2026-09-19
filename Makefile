# docker login -u jonhayes37

IMAGE := jonhayes37/iu-bot
# Every push is also tagged with the commit, so a bad release can be rolled back to a known tag.
VERSION := $(shell git rev-parse --short HEAD)

ensure-docker:
	@docker info >/dev/null 2>&1 || colima start

build-push: ensure-docker
	docker build --platform linux/amd64 -t iu-bot .
	docker tag iu-bot $(IMAGE)
	docker tag iu-bot $(IMAGE):$(VERSION)
	docker push $(IMAGE)
	docker push $(IMAGE):$(VERSION)
	@echo "Pushed $(IMAGE):latest and $(IMAGE):$(VERSION)"
