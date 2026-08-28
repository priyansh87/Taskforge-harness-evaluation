FROM python:3.11-slim

WORKDIR /workspace

COPY . /workspace

RUN pip install --no-cache-dir -e . \
 && pip install --no-cache-dir pytest pytest-cov pytest-mock

ENTRYPOINT ["/bin/bash"]
