FROM python:3.11-slim

WORKDIR /workspace

COPY . /workspace

# Install in editable mode, fallback to standard install, and ensure pytest is installed
RUN pip install --no-cache-dir -e ".[test]" 2>/dev/null || pip install --no-cache-dir -e . \
 && pip install --no-cache-dir pytest

ENTRYPOINT ["/bin/bash"]
