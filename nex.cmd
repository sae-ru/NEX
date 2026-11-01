@echo off
setlocal DisableDelayedExpansion
if not defined NEX_PYTHON if exist "C:\Python314\python.exe" set "NEX_PYTHON=C:\Python314\python.exe"
if not defined NEX_LLDB if exist "%~dp0build\deps\windows-debugger23-source-f\clang64\bin\lldb.exe" set "NEX_LLDB=%~dp0build\deps\windows-debugger23-source-f\clang64\bin\lldb.exe"
if not defined NEX_LLDB_DAP if exist "%~dp0build\deps\windows-debugger23-source-f\clang64\bin\lldb-dap.exe" set "NEX_LLDB_DAP=%~dp0build\deps\windows-debugger23-source-f\clang64\bin\lldb-dap.exe"
if not defined NEX_TSC if exist "%~dp0web\node_modules\typescript\bin\tsc" set "NEX_TSC=%~dp0web\node_modules\typescript\bin\tsc"
"%~dp0build\windows-host\nex.exe" %*
exit /b %errorlevel%
