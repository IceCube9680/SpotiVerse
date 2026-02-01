# Use slim Python base image
FROM python:3.12-slim

# Metadata
LABEL maintainer="https://github.com/priest1966"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Set working directory
WORKDIR /app

# Install system dependencies (ffmpeg + build tools for Pillow/other libs)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ffmpeg \
      build-essential \
      git \
      curl \
      ca-certificates \
      libjpeg62-turbo-dev \
      zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency list first (for caching)
COPY requirements.txt /app/requirements.txt

# Install Python deps
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r /app/requirements.txt

# Copy project code
COPY . /app

# Ensure runtime dirs exist
RUN mkdir -p /app/temp /app/data/thumbnails && \
    groupadd -r bot && useradd -r -g bot bot && \
    chown -R bot:bot /app

USER bot

# No ports needed (Telegram bot)
# EXPOSE 8080

# Start the bot
CMD ["python", "bot.py"]

