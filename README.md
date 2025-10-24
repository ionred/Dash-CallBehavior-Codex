# Dash-CallBehavior-Codex

A Dash application for managing company event monitoring workflows.

## Getting started

1. Create and activate a virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the application with uvicorn:

   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8050
   ```

   The app is configured for ASGI hosting and can also be served via IIS using `httpPlatformHandler`.

## Project structure

```
app/
├── assets/                # Static assets (CSS, images)
├── callbacks/             # Dash callbacks wiring
├── data_access/           # SQL Server data layer
├── layouts/               # Layout definitions
├── services/              # Domain services, caching, background tasks
├── utils/                 # Helper utilities (CSV validation, formatting)
└── main.py                # Entrypoint for uvicorn
```

Configuration resides in `config.py`. File-system caching is enabled by default. A commented Redis configuration is provided for future use.

## Testing

Run a basic syntax check:

```bash
python -m compileall app
```

