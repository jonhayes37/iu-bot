# docker login -u jonhayes37

build-push:
	docker build --platform linux/amd64 -t iu-bot .
	docker tag iu-bot jonhayes37/iu-bot
	docker push jonhayes37/iu-bot
