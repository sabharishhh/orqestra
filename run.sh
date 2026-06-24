#!/bin/bash

PROJECT_DIR="/Users/sabharishhh/Developer/orqestra"
VENV_PATH="$PROJECT_DIR/.venv/bin/activate"

osascript <<EOF
tell application "Terminal"

    -- Docker
    do script "cd \"$PROJECT_DIR\" && source \"$VENV_PATH\" && docker compose down -v && docker compose up"

    -- Frontend
    do script "cd \"$PROJECT_DIR/frontend\" && source \"$VENV_PATH\" && npm run dev"

    -- Celery Worker
    do script "cd \"$PROJECT_DIR\" && source \"$VENV_PATH\" && celery -A core.celery_app worker --pool=solo --loglevel=info -Q celery,claim_extraction,dead_letters"

    -- FastAPI
    do script "cd \"$PROJECT_DIR\" && source \"$VENV_PATH\" && uvicorn api.main:app --reload"

end tell
EOF

# Give services time to start
sleep 15

# Inject traffic
cd "$PROJECT_DIR"
source "$VENV_PATH"
python inject_traffic.py