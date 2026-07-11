#!/bin/sh
set -e

BACKEND_URL="${NEXT_PUBLIC_BACKEND_BASE_URL:-http://localhost:8000}"
echo "Runtime backend URL: $BACKEND_URL"

# If the runtime value differs from the build default, swap it in all .js files
if [ "$BACKEND_URL" != "http://localhost:8000" ]; then
  find /app -name '*.js' -type f -exec sed -i "s|http://localhost:8000|${BACKEND_URL}|g" {} +
fi

exec node server.js