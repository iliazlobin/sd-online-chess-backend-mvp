# Multi-stage build: python:3.12-slim
# - builder: installs project into a venv
# - runtime: copies venv + src, serves via uvicorn

# ---- Builder stage ----
FROM python:3.12-slim AS builder

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY pyproject.toml ./

# Install dependencies (no dev extras for production)
RUN pip install --no-cache-dir ".[dev]" && \
    pip check

# Copy source
COPY src/ ./src/

# Install the project itself so entry-points and the package are both available
RUN pip install --no-cache-dir --no-deps .

# ---- Runtime stage ----
FROM python:3.12-slim

ENV PATH="/opt/venv/bin:$PATH"

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

EXPOSE 8000

CMD ["uvicorn", "chess_mvp.main:app", "--host", "0.0.0.0", "--port", "8000"]
