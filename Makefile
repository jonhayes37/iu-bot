# docker login -u jonhayes37

ensure-docker:
	@docker info >/dev/null 2>&1 || colima start

build-push: ensure-docker
	docker build --platform linux/amd64 -t iu-bot .
	docker tag iu-bot jonhayes37/iu-bot
	docker push jonhayes37/iu-bot
