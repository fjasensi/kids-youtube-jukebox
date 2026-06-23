# Agent Instructions

This app is already deployed locally with Podman and PostgreSQL. Treat the
running Podman stack as the source of truth for runtime checks.

## Deployment Safety

- Do not start a local `uvicorn` server on port `8000`. Port `8000` is reserved
  for the Podman-published app and may be actively used by the family.
- Do not run a second local server for testing unless the user explicitly asks.
  If a local dev server is unavoidable, use a non-production port such as
  `8001` only after checking it is free, and stop it before finishing.
- Before any deployment-related work, check the current runtime:
  - `make status`
- Deploy app code with:
  - `make deploy-app`
- Do not use `--force-recreate` unless the user explicitly approves it for that
  turn. It can recreate containers beyond the app service.
- Do not run `podman compose down`, remove containers, or remove volumes unless
  the user explicitly asks. The PostgreSQL volume contains family data.

## Database Safety

- PostgreSQL is part of the app, not a disposable test dependency.
- Only run read-only verification queries unless the user explicitly approves a
  data-changing operation.
- Schema changes should be implemented in application startup code or a reviewed
  migration path, then verified against the running Podman PostgreSQL.
- After a migration deploy, verify:
  - `make verify`
  - `make favorites-schema` if schema confirmation is needed

## Final Checks

Before reporting completion after deployment-related changes:

- Confirm no local test server remains on `8001` or another temporary port.
- Confirm port `8000` is served only through Podman/gvproxy.
- Confirm the app container and database container are healthy.
- Mention any command that recreated or restarted a container.
