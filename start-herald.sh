#!/bin/bash
# Start Herald email assistant locally
cd "$(dirname "$0")"

# Create venv if needed
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

# Create data directory for archive suggestions
mkdir -p ~/Agents/herald-data

echo ""
echo "  Herald - AI Email Assistant"
echo "  http://localhost:8080"
echo ""
echo "  Open in your phone browser on the same network:"
echo "  http://$(ipconfig getifaddr en0 2>/dev/null || echo 'YOUR_IP'):8080"
echo ""

uvicorn src.app:app --host 0.0.0.0 --port 8080 --reload
