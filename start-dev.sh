#!/bin/bash

# Script to start frontend and backend in separate terminal windows

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Start backend in a new terminal window
osascript <<EOF
tell application "Terminal"
    do script "cd '$SCRIPT_DIR/api' && source .venv/bin/activate && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
    set custom title of front window to "LUMEN Backend"
end tell
EOF

# Small delay to ensure terminal windows open in order
sleep 1

# Start frontend in a new terminal window
osascript <<EOF
tell application "Terminal"
    do script "cd '$SCRIPT_DIR/web' && npm run dev"
    set custom title of front window to "LUMEN Frontend"
    activate
end tell
EOF

echo "Started LUMEN development servers in separate terminal windows:"
echo "- Backend: http://localhost:8000"
echo "- Frontend: http://localhost:5173"
