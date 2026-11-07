@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist .venv\Scripts\python.exe (
  echo [설치] 처음 실행이라 필요한 프로그램을 설치합니다. 10~20분 걸릴 수 있어요.
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)
if not exist jobs mkdir jobs

rem 자동 반영 모드: 코드(app.py, editor\*.py)가 바뀌면 다시 실행하지 않아도 화면이 새로 불러옵니다.
rem .env 의 API 키는 미리보기/편집을 누를 때마다 다시 읽습니다.
set GRADIO_SERVER_NAME=127.0.0.1
set GRADIO_SERVER_PORT=7860
set GRADIO_ALLOWED_PATHS=%~dp0jobs
start "" cmd /c "timeout /t 10 >nul & start http://127.0.0.1:7860"
.venv\Scripts\gradio.exe app.py --demo-name demo --watch-dirs editor
pause
