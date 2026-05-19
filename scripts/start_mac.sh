#!/bin/bash
set -e

IMAGE_NAME="finally"
CONTAINER_NAME="finally-app"
DATA_VOLUME="finally-data"

# Resolve project root (parent of this script's directory) so the script
# can be run from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Ensure .env exists (required by --env-file)
if [[ ! -f ".env" ]]; then
  echo "Error: .env file not found in $PROJECT_ROOT"
  echo "Copy .env.example to .env and fill in your API keys."
  exit 1
fi

# Build if requested or if image doesn't exist
if [[ "$1" == "--build" ]] || ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
  echo "Building FinAlly image..."
  docker build -t "$IMAGE_NAME" .
fi

# Stop existing container if running
if docker ps -q -f name="^${CONTAINER_NAME}$" | grep -q .; then
  echo "Stopping existing container..."
  docker stop "$CONTAINER_NAME" >/dev/null && docker rm "$CONTAINER_NAME" >/dev/null
elif docker ps -aq -f name="^${CONTAINER_NAME}$" | grep -q .; then
  # Container exists but is stopped — remove it so `docker run` doesn't conflict
  docker rm "$CONTAINER_NAME" >/dev/null
fi

# Start container
docker run -d \
  --name "$CONTAINER_NAME" \
  -v "$DATA_VOLUME:/app/db" \
  -p 8000:8000 \
  --env-file .env \
  "$IMAGE_NAME" >/dev/null

echo ""
echo "FinAlly is running at: http://localhost:8000"
echo "Stop with: ./scripts/stop_mac.sh"
