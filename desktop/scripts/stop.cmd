@echo off
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9876" ^| findstr "LISTENING"') do taskkill /F /PID %%a 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do taskkill /F /PID %%a 2>nul
echo Stopped.
