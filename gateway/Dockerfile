FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY pyproject.toml /app/
COPY mg_ai /app/mg_ai
COPY model-registry /app/model-registry
COPY routing /app/routing
COPY policies /app/policies
COPY scripts /app/scripts
COPY evals /app/evals
RUN groupadd -g 10001 mg && useradd -u 10001 -g mg -M mg && mkdir /state && chown mg:mg /state
USER 10001:10001
ENV MG_STATE_PATH=/state/state.sqlite
EXPOSE 8080
CMD ["uvicorn", "mg_ai.gateway:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log", "--workers", "1"]
