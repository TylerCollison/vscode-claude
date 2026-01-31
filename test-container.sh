#!/bin/bash
# Test script to build and run the container to verify VS Code server starts properly

echo "Building Docker image..."
docker build -t vscode-claude-test .

echo "Starting container in detached mode..."
docker run -d \
  --name vscode-claude-test \
  -e PUID=1000 \
  -e PGID=1000 \
  -e TZ=Etc/UTC \
  -p 8443:8443 \
  vscode-claude-test

echo "Waiting for container to start..."
sleep 10

echo "Checking container status..."
docker ps -f name=vscode-claude-test

echo "Checking logs for VS Code server startup..."
docker logs vscode-claude-test | grep -i "code-server\|start\|bind" | tail -10

echo "Testing port 8443 connectivity..."
# Check if port is listening
if nc -z localhost 8443; then
    echo "✅ Port 8443 is listening - VS Code server is running!"
    echo "Access at: http://localhost:8443"
else
    echo "❌ Port 8443 is not listening - check container logs"
    docker logs vscode-claude-test
fi