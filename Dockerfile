FROM python:3.12-bookworm

WORKDIR /app

# System dependencies: ffmpeg runtime + dev (for pip av) + chromium
RUN apt-get update -qq && apt-get install -y -qq \
    ffmpeg \
    libavformat-dev libavcodec-dev libavdevice-dev \
    libavfilter-dev libavutil-dev libswscale-dev libswresample-dev \
    && rm -rf /var/lib/apt/lists/*

# Install project and all dependencies
COPY pyproject.toml .
COPY src/ src/
COPY README.md .
RUN pip install --no-cache-dir -e ".[dev,transcribe,transcribe-deepgram]"

# Install Playwright browsers (requires GLIBC 2.28+, bookworm has 2.36)
RUN playwright install chromium && playwright install-deps chromium

# Default: mount config and data at runtime
VOLUME ["/app/data", "/app/config.yaml", "/app/.env"]

ENTRYPOINT ["media2text"]
CMD ["--help"]
