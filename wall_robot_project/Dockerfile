### Multi-stage Dockerfile: build wheels in a builder image, then install in a small runtime
FROM python:3.11-slim AS builder
ARG USER=appuser
ARG UID=1000
WORKDIR /wheels

# Install build deps for wheels
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /wheels/
RUN python -m pip install --upgrade pip setuptools wheel
# Build wheels into /wheels
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r /wheels/requirements.txt

FROM python:3.11-slim AS final
ARG USER=appuser
ARG UID=1000
WORKDIR /app

# Create non-root user
RUN groupadd -g ${UID} ${USER} \
 && useradd -m -u ${UID} -g ${UID} ${USER}

# Copy wheels from builder and install
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r /wheels/requirements.txt || true

# Copy application
COPY . /app
RUN chown -R ${USER}:${USER} /app

USER ${USER}
ENV PATH="/home/${USER}/.local/bin:${PATH}"

EXPOSE 8000

CMD ["uvicorn", "robot_control_system:app", "--host", "0.0.0.0", "--port", "8000"]
