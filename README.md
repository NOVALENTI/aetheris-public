# Aetheris Public — Content Extraction API

A small **Python / FastAPI** reference project showing how to build a bounded content-extraction API with **authentication, explicit source allowlisting, async HTTP, deterministic parsing, and offline tests**.

**Created by Valentino Herrera.**

## What it does

- `GET /healthz` returns health status without revealing configuration.
- `POST /extract` validates a caller token and a source URL, calls a public reader provider, and returns **source-derived** lines instead of fictional AI-generated facts.
- Only exact, explicitly configured HTTPS hostnames can be processed. IP-literal URLs, embedded credentials, arbitrary ports, and unapproved hosts are rejected.
- API returns generic upstream errors to avoid exposing internal information.

## Architecture

`Client → token check → URL/host allowlist → public reader → source-line parser → structured JSON`

The demo uses the publicly available Jina Reader service; it **does not** include private provider credentials. Running it against external websites is optional and requires a deliberate host allowlist. All included tests run offline using a mock provider.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export APP_ACCESS_TOKEN='choose-a-long-secret'
export ALLOWED_SOURCE_HOSTS='example.com'
uvicorn aetheris.api:app --reload
```

In a second terminal:

```bash
curl http://127.0.0.1:8000/healthz
curl -X POST http://127.0.0.1:8000/extract \
  -H 'Content-Type: application/json' \
  -H 'X-Proxy-Key: choose-a-long-secret' \
  -d '{"url":"https://example.com/","topic":"documentation"}'
```

Run the offline test suite:

```bash
pytest -q
```

## Security decisions and limitations

- Credentials must be provided via runtime environment variables. `.env` and other local files are ignored.
- An empty/unset token disables extraction. An empty host allowlist denies all sources.
- The URL allowlist is **exact host matching**, never a broad suffix match.
- External pages are processed by a third-party reader; **do not send private URLs or sensitive content**.
- This is an educational portfolio implementation, not a complete production proxy. It has no distributed rate limiting, audit log retention, or guarantee against external-provider behavior. Do not deploy it publicly without an additional security review, TLS, and operational limits.
- No private repository history, proprietary models, or infrastructure configuration are reproduced.

## Project scope

This is a deliberately small, tested example of secure-default API design rather than a claim of a fully deployed commercial product.

## Rights and commercial use

Copyright © 2026 Valentino Herrera. All rights reserved. No open-source reuse license is granted for this original demo. Viewing and forking are subject to GitHub's terms and applicable law; commercial use or commissioned adaptations require a separate written agreement. For licensing discussions: **valentinoherreraofficial@gmail.com**. Viewing this repository does not create an automatic payment obligation.
