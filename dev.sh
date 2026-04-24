#!/usr/bin/env bash
set -euo pipefail

SESSION="cooplook"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Kill existing session if present
if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux kill-session -t "$SESSION"
fi

# Create new session with backend pane
tmux new-session -d -s "$SESSION" -n "dev" -c "$PROJECT_DIR"

# Rename the first window and run backend
tmux send-keys -t "$SESSION:dev" './start.sh' C-m

# Split vertically and run frontend
tmux split-window -h -t "$SESSION:dev" -c "$PROJECT_DIR/frontend"
tmux send-keys -t "$SESSION:dev" 'npm run dev' C-m

# Select even layout
tmux select-layout -t "$SESSION:dev" even-horizontal

# Attach to session
tmux attach -t "$SESSION"
