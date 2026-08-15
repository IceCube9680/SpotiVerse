#!/bin/bash
# SpotiVerse Bot Control Script

PROJECT_DIR="/home/icecube/ASUS/SpotiVerse"
PID_FILE="$PROJECT_DIR/bot.pid"
LOG_FILE="$PROJECT_DIR/bot.log"

# Use python3 or active virtual environment python
if [ -d "$PROJECT_DIR/venv" ]; then
    PYTHON_BIN="$PROJECT_DIR/venv/bin/python"
elif [ -d "$HOME/Downloads/Spotiverse/venv" ]; then
    PYTHON_BIN="$HOME/Downloads/Spotiverse/venv/bin/python"
else
    PYTHON_BIN="$(which python3)"
fi

cd "$PROJECT_DIR" || exit 1

case "$1" in
    start)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "SpotiVerse Bot is already running (PID: $(cat "$PID_FILE"))."
        else
            echo "Starting SpotiVerse Bot using $PYTHON_BIN..."
            nohup "$PYTHON_BIN" bot.py > "$LOG_FILE" 2>&1 &
            echo $! > "$PID_FILE"
            echo "SpotiVerse Bot started with PID $(cat "$PID_FILE")."
            echo "Logs are being written to: $LOG_FILE"
        fi
        ;;
    stop)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "Stopping SpotiVerse Bot (PID: $(cat "$PID_FILE"))..."
            kill "$(cat "$PID_FILE")"
            rm -f "$PID_FILE"
            echo "Bot stopped."
        else
            echo "SpotiVerse Bot is not running."
            rm -f "$PID_FILE" 2>/dev/null
        fi
        ;;
    restart)
        $0 stop
        sleep 2
        $0 start
        ;;
    status)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "SpotiVerse Bot is RUNNING (PID: $(cat "$PID_FILE"))."
        else
            echo "SpotiVerse Bot is STOPPED."
        fi
        ;;
    logs)
        if [ -f "$LOG_FILE" ]; then
            tail -f -n 50 "$LOG_FILE"
        else
            echo "Log file $LOG_FILE does not exist yet."
        fi
        ;;
    run)
        echo "Running SpotiVerse Bot in foreground..."
        exec "$PYTHON_BIN" bot.py
        ;;
        *)
        echo "Usage: $0 {start|stop|restart|status|logs|run}"
        exit 1
        ;;
esac
