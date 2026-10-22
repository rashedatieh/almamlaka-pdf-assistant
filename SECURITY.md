# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub's
[private vulnerability reporting](https://github.com/rashedatieh/almamlaka-pdf-assistant/security/advisories/new),
not in public issues. I aim to reply within 5 working days.

## Design

- No secrets are stored in this repository. The Claude API key and the app secrets are read at runtime from
  Google Secret Manager or environment variables; `.env` files are git-ignored.
- Model output is rendered as text only, under a strict Content Security Policy.
- Prompt-injection defences, signed conversation history, rate limiting and a daily cost cap are described
  in the README ("Security").
