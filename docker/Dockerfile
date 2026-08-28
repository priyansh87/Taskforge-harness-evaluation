FROM python:3.11-slim

WORKDIR /workspace

COPY . /workspace

RUN pip install --no-cache-dir -r requirements/requirements-tests.txt \
 && pip install --no-cache-dir -e .

ENTRYPOINT ["/bin/bash"]
