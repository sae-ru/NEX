@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0..\.." || exit /b 1
set "NEX_NATIVE_PYTHON=%NEX_PYTHON%"
if not defined NEX_NATIVE_PYTHON set "NEX_NATIVE_PYTHON=C:\Python314\python.exe"
if not exist "%NEX_NATIVE_PYTHON%" set "NEX_NATIVE_PYTHON=python.exe"
"%NEX_NATIVE_PYTHON%" -X utf8 "%~dp0verify_native.py" --cohort "build\windows-wave30-cohort" --debugger-prefix "build\deps\windows-debugger23-source-f\clang64" --output "build\native-verification-%RANDOM%-%RANDOM%" --cuda %*
set "NEX_NATIVE_RESULT=%errorlevel%"
popd
exit /b %NEX_NATIVE_RESULT%
