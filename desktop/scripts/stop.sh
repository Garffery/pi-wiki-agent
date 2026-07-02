#!/bin/bash
# Stop dev servers on ports 9876 and 5173
for port in 9876 5173; do
  # Try Windows cmd netstat first
  pids=$(cmd.exe /c "netstat -ano | findstr :$port | findstr LISTENING" 2>/dev/null | awk '{print $5}' | tr -d '\r')
  if [ -z "$pids" ]; then
    # Fallback: try bash-native netstat (Unix/Cygwin)
    pids=$(netstat -ano 2>/dev/null | grep ":$port" | grep "LISTENING" | awk '{print $5}')
  fi
  for pid in $pids; do
    taskkill //F //PID "$pid" 2>/dev/null
  done
done
echo "Stopped."
