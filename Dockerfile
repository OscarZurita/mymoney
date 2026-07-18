# Django app image for the mymoney project (development use).
FROM python:3.12-slim

# Unbuffered logs; don't scatter .pyc files into the bind-mounted source tree.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Run as a non-root user whose UID/GID match the host user, so files the
# container writes into the bind mount (e.g. new migrations) stay owned by,
# and editable as, the host user instead of root.
ARG UID=1000
ARG GID=1000
RUN groupadd --gid ${GID} app \
    && useradd --uid ${UID} --gid ${GID} --create-home app

WORKDIR /app

# Install dependencies first so this layer is cached across source changes.
COPY requirements.txt .
RUN pip install --requirement requirements.txt

# Copy the source. At runtime compose overlays this with a bind mount, so the
# baked copy is only a fallback for running the image without the mount.
COPY . .

USER app

EXPOSE 8000

# entrypoint runs migrations, then execs the command below.
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
