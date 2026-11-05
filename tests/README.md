# Running the test suite

Install the development-only test runner, then run every parser, source,
grading, and storage test with:

```sh
uv pip install --target /tmp/betcouncil-test-deps -r requirements-dev.txt
PYTHONPATH="/tmp/betcouncil-test-deps${PYTHONPATH:+:$PYTHONPATH}" python -m pytest -v
```

The command assumes the application's runtime dependencies from
`requirements.txt` are already installed. `pytest` and the test setup remain
separate from `requirements.txt`, so they are not added to the runtime feed
dependencies.
