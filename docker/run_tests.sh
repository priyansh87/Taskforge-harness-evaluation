#!/usr/bin/env bash
cd /workspace
pytest tests/ -q --tb=short --no-cov
EXIT_VAL=$?
echo "EXIT_CODE:$EXIT_VAL"
exit $EXIT_VAL
