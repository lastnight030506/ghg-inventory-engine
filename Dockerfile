# syntax=docker/dockerfile:1
FROM python:3.12-slim

# DejaVu is not optional: the PDF report renders CO₂ and the table rules with it,
# and without the font the report fails loudly rather than printing tofu.
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

# hatchling needs the metadata to build; the package itself is installed from src.
COPY pyproject.toml README.md ./
COPY src ./src
COPY tests ./tests
# data must be present at build time: pyproject force-includes it into the wheel
# under ghg/data/, so the installed tool is self-contained. Copying it afterwards
# would leave the wheel empty and rely on the CWD fallback instead.
COPY data ./data
# The dev extras, not a bare pytest: the suite imports pypdf to compare PDF
# text, and a partial install made that a red run in CI instead of a code bug.
RUN pip install --no-cache-dir ".[dev]"

# Non-root. The bind-mounted output directory cannot inherit permissions from the
# image, so the documented run command passes `--user $(id -u):$(id -g)`; that
# makes the report come back owned by whoever ran it instead of by uid 10001.
# HOME is /tmp so matplotlib's font cache does not try to write an unwritable
# home directory when the uid has no passwd entry.
RUN useradd --create-home --uid 10001 ghg \
 && mkdir -p /app/out \
 && chown -R ghg:ghg /app
USER ghg

ENV HOME=/tmp
VOLUME ["/app/out"]

# Default: the full pipeline. Override the command to run the test suite instead.
CMD ["ghg", "inventory", "--out", "/app/out"]
