# syntax=docker/dockerfile:1

# ---- build stage: resolve deps into a venv ----
FROM python:3.14-slim AS build
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_PREFERENCE=only-system
WORKDIR /app

# deps first, without the project → cacheable layer
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# then the code + install the project itself
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---- runtime stage: same base + Inkscape/Ink-Stitch sidecar ----
FROM python:3.13-slim AS runtime
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      inkscape xvfb wget ca-certificates \
 && wget -O /tmp/inkstitch.deb <inkstitch-release-url> \
 && (dpkg -i /tmp/inkstitch.deb || apt-get -f install -y) \
 && rm -rf /var/lib/apt/lists/* /tmp/inkstitch.deb

# bring over just the built venv + app code
COPY --from=build /app /app
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
