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
FROM python:3.14-slim AS runtime

ARG INKSTITCH_VERSION=3.2.2
ARG INKSTITCH_DEB_SHA256=75118683a38f16fcdc099652a64435870c61f3f59fbe1ed6853318eedeea50a1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      inkscape xvfb wget ca-certificates \
 && wget -O /tmp/inkstitch.deb \
      "https://github.com/inkstitch/inkstitch/releases/download/v${INKSTITCH_VERSION}/inkstitch_${INKSTITCH_VERSION}_amd64.deb" \
 && echo "${INKSTITCH_DEB_SHA256}  /tmp/inkstitch.deb" | sha256sum -c - \
 && (dpkg -i /tmp/inkstitch.deb || apt-get -f install -y) \
 && rm -rf /var/lib/apt/lists/* /tmp/inkstitch.deb

# bring over just the built venv + app code
COPY --from=build /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    INKSTITCH_BIN=/opt/inkstitch/bin/inkstitch \
    U2NET_HOME=/opt/u2net

# bake the background-removal model into the image instead of downloading per container
RUN python -c "from rembg import new_session; new_session('u2net')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
