@echo off
setlocal DisableDelayedExpansion
set "NEX_GAME_PYTHON=%NEX_PYTHON%"
if not defined NEX_GAME_PYTHON set "NEX_GAME_PYTHON=C:\Python314\python.exe"
if not exist "%NEX_GAME_PYTHON%" set "NEX_GAME_PYTHON=python.exe"
"%NEX_GAME_PYTHON%" -X utf8 "%~dp0..\tic-tac-toe\project.py" build %*
exit /b %errorlevel%
