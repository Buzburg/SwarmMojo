#!/bin/sh
# Generated automatically by polyharness — DO NOT EDIT DIRECTLY
# Intercepts agent command execution against prohibited commands

COMMAND="$*"
DENY_LIST='["rm -rf /","git push --force","drop database"]'

if [ -z "$COMMAND" ]; then
  echo "Usage: safe-exec <command...>"
  exit 1
fi

for blocked in $(echo "$DENY_LIST" | sed 's/[][]//g' | tr ',' '\n' | tr -d '"' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'); do
  if [ -n "$blocked" ] && echo "$COMMAND" | grep -F -q "$blocked"; then
    echo "❌ [polyharness-guard] Execution blocked: command '$COMMAND' contains forbidden pattern '$blocked'."
    exit 126
  fi
done

exec "$@"
