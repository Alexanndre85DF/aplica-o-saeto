@echo off
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt
echo.
if exist .env (
  echo Banco: verifique a Visao geral no navegador
) else (
  echo Banco: arquivo local. Para a nuvem, cole a chave service_role no .env
)
echo Abra no navegador: http://127.0.0.1:8765
echo.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
pause
