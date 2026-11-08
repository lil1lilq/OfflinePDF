@echo off
"%~dp0OfflinePDF.exe" --unregister-explorer
if errorlevel 1 pause
