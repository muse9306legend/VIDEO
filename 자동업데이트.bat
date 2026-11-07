@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 1분마다 GitHub 에서 새 코드를 받아옵니다. 받아오면 켜져 있는 편집기가 몇 초 안에 새 코드로 바뀝니다.
rem 분석이나 영상 만들기가 진행 중이면(jobs\_busy 에 표시가 있으면) 끝날 때까지 기다립니다.
where git >nul 2>nul || (echo [자동 업데이트] git 이 없어 꺼집니다. & exit /b)
if not exist .git (echo [자동 업데이트] git 으로 받은 폴더가 아니라 꺼집니다. & exit /b)
:loop
powershell -NoProfile -Command "$d='jobs\_busy'; if (Test-Path $d) { Get-ChildItem $d -Filter *.lock | Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-6) } | Remove-Item -ErrorAction SilentlyContinue; if (Get-ChildItem $d -Filter *.lock) { exit 1 } }; exit 0"
if errorlevel 1 (
  echo [%time%] 작업 중이라 업데이트를 미룹니다.
) else (
  git pull --ff-only -q && echo [%time%] 최신 코드 확인 완료
)
timeout /t 60 /nobreak >nul
goto loop
