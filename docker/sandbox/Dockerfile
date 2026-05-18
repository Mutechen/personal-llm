# personal-llm skill sandbox base image.
#
# Phase 1+: the agent loop runs skills that touch the network or filesystem
# outside the vault in an ephemeral container built from this image.
# Skills that are pure-Python and side-effect-free run in smolagents'
# LocalPythonExecutor on the host (cheaper, no container spin-up).
#
# Keep this image small and the allowlist conservative — the principle is
# "give a skill exactly what it needs, nothing more."

FROM python:3.12-slim AS base

# Non-root user — skills never run as root.
RUN useradd -m -u 10001 -s /bin/bash sandbox

WORKDIR /sandbox

# Curated default packages. Add to this list deliberately; every added package
# is a new attack surface for an adversarial skill.
RUN pip install --no-cache-dir \
        requests==2.32.* \
        beautifulsoup4==4.12.* \
        lxml==5.* \
        pyyaml==6.* \
        python-dateutil==2.9.* \
        tenacity==9.* \
    && rm -rf /root/.cache/pip

# Optional larger packages — uncomment if your skills routinely need them.
# Each adds ~50-150MB to the image.
# RUN pip install --no-cache-dir pandas==2.* numpy==1.* && rm -rf /root/.cache/pip

USER sandbox

# Default smoke check — `docker run personal-llm/sandbox` verifies the image builds and runs.
CMD ["python", "-c", "print('personal-llm sandbox ready'); import sys; sys.exit(0)"]
