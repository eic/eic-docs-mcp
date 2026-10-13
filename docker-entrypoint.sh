#!/bin/sh
# With arguments: run them. Without: refresh the sources, rebuild the index, serve.
set -eu

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

eic-docs-mcp --update
eic-docs-mcp --index
exec eic-docs-mcp --transport http --host 0.0.0.0 --port "${PORT:-8000}" --refresh-hours "${EIC_DOCS_REFRESH_HOURS:-24}"
