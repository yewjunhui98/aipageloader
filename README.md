# Predictive Page Preload PoC (Podman + MSSQL + AI/ML)

This proof of concept demonstrates:

- **Visit tracking**: user page visits are stored in MSSQL.
- **Per-user AI/ML model**: a simple Markov transition model is trained from the full visit sequence.
- **Model persistence**: transition weights are stored as JSON in MSSQL (`user_transition_models`).
- **Frontend preloading**: next-page predictions are fetched and preloaded to simulate instant navigation.

## Architecture

- `frontend` (Nginx static app, port `8080`)
- `backend` (FastAPI + pyodbc model/API service, port `8000`)
- `mssql` (SQL Server 2019, port `1433`)

Persistent DB storage is mapped to:

- Podman volume `poc_mssql_data -> /var/opt/mssql` (persistent across restarts)

## Database Tables

Created automatically by backend on startup:

1. `dbo.users`
2. `dbo.pages`
3. `dbo.page_visits`
4. `dbo.user_transition_models`

## Run with Podman (recommended on Windows)

Prerequisite: Podman machine already started.

```powershell
# from this project root
.\scripts\start-poc.ps1
```

Open frontend:

- http://localhost:8080

API docs:

- http://localhost:8000/docs

Stop everything:

```powershell
.\scripts\stop-poc.ps1
```

## Optional: Compose flow

If your Podman install has a compose provider (`podman-compose` or `docker-compose`), you can also run:

```powershell
podman compose -f .\podman-compose.yml up --build
```

## Demo flow

1. Create a user in the UI.
2. Visit a few pages in a pattern, such as:
   - Home -> Tech -> Finance
   - Home -> Tech -> Sports
3. Revisit `Tech`; backend predicts likely next pages.
4. Frontend preloads predicted pages and serves them from cache on click.

## Useful commands

```powershell
podman ps
podman logs -f poc-backend
podman logs -f poc-mssql
```

## Notes

- Change the SQL `MSSQL_SA_PASSWORD` before sharing externally.
- This is a PoC model to illustrate predictive preloading behavior, not production-grade recommendation quality.
- On Windows + Podman machine, SQL Server bind-mounts to NTFS paths can fail permission checks, so the starter script uses a named Podman volume for reliable persistence.
