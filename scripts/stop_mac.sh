#!/bin/bash
set -e

CONTAINER_NAME="finally-app"

if docker ps -q -f name="^${CONTAINER_NAME}$" | grep -q .; then
  echo "Stopping FinAlly..."
  docker stop "$CONTAINER_NAME" >/dev/null && docker rm "$CONTAINER_NAME" >/dev/null
  echo "Stopped. Data volume preserved."
elif docker ps -aq -f name="^${CONTAINER_NAME}$" | grep -q .; then
  docker rm "$CONTAINER_NAME" >/dev/null
  echo "Removed stopped container. Data volume preserved."
else
  echo "FinAlly is not running."
fi
