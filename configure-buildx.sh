#!/usr/bin/with-contenv bash
# Configure BuildKit builder for faster Docker builds
# Creates a persistent docker-container driver builder that avoids
# the expensive layer-export step at the end of builds.
# Only runs when USE_BUILDKIT_BUILDER=true is set.
# Runs at container startup (not at image build time) because
# the Docker socket is only available at runtime.

set -euo pipefail

# Gate on explicit opt-in — only create the builder if the user opts in
if [ "${USE_BUILDKIT_BUILDER:-}" != "true" ]; then
    exit 0
fi

BUILDER_NAME="${BUILDX_BUILDER_NAME:-buildkit-builder}"

# Check if Docker socket is available
if [ ! -S /var/run/docker.sock ]; then
    echo "WARNING: Docker socket not found at /var/run/docker.sock. Skipping BuildKit builder setup."
    exit 0
fi

# Test Docker connectivity
if ! docker info >/dev/null 2>&1; then
    echo "WARNING: Cannot connect to Docker daemon. Skipping BuildKit builder setup."
    exit 0
fi

# Check if builder already exists.
# docker buildx ls prints a header then two-line groups:
#   builder-name*  driver
#    \_ node-name   \_ endpoint   status   ...
# The builder name may have a trailing '*' (current default).
# The node's status is in field 5 of the child line.
EXISTING_STATUS=$(docker buildx ls 2>/dev/null | awk -v name="${BUILDER_NAME}" '
    BEGIN { found=0; status="" }
    { orig=$1; gsub(/\*$/, "", $1) }
    $1 == name { found=1; checking=1; next }
    checking == 1 { status=$5; checking=0 }
    END { if (!found) print "not-found"; else print status }
')
if [ "$EXISTING_STATUS" = "running" ]; then
    echo "BuildKit builder '${BUILDER_NAME}' already exists and is running. Setting as default."
    docker buildx use "${BUILDER_NAME}" 2>/dev/null || true
    exit 0
elif [ "$EXISTING_STATUS" != "not-found" ]; then
    echo "BuildKit builder '${BUILDER_NAME}' found but status is '${EXISTING_STATUS}'. Removing and recreating..."
    docker buildx rm "${BUILDER_NAME}" 2>/dev/null || true
fi

# Create a new builder with docker-container driver
echo "Creating persistent BuildKit builder '${BUILDER_NAME}' (docker-container driver)..."
if docker buildx create --name "${BUILDER_NAME}" --driver docker-container --use --bootstrap; then
    echo "SUCCESS: BuildKit builder '${BUILDER_NAME}' created and set as default."
    echo "Future 'docker build' commands will use BuildKit natively without layer export overhead."
else
    echo "WARNING: Failed to create BuildKit builder. Docker builds will use the default driver."
fi
