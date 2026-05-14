FROM python:3.12-alpine

RUN apk add --no-cache docker-cli docker-cli-compose curl

WORKDIR /agent
COPY launcher_agent.py /agent/launcher_agent.py

EXPOSE 8787
CMD ["python", "/agent/launcher_agent.py"]
