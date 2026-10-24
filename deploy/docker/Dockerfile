# Any machine with Docker (Linux, macOS, Windows). Build from the folder that holds agent.toml:
#   docker build -f <Ultron>/deploy/docker/Dockerfile -t ultron .
# (the folder holds agent.toml; when it is not an Ultron checkout itself, Ultron comes from GitHub)
#   docker run -d --name ultron --restart unless-stopped --env-file .env -v "$PWD/output:/app/output" ultron
# Secrets come in only through --env-file: keep .env, output/ and other private files out of the
# image with a .dockerignore next to agent.toml (e.g. lines: .env  output  .git).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY . /app
RUN if [ -f /app/pyproject.toml ] && grep -q 'name = "ultron"' /app/pyproject.toml; \
    then pip install --no-cache-dir "/app[full]"; \
    else pip install --no-cache-dir "ultron[full] @ git+https://github.com/bindalbhikan/Ultron.git"; fi
CMD ["ultron", "serve"]
