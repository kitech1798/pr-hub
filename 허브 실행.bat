@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo [KITECH 홍보 허브] streamlit 시작합니다...
echo.
echo  - 종료: 이 창에서 Ctrl+C 두 번 또는 창 닫기
echo  - 브라우저가 자동으로 열립니다 (안 뜨면 http://localhost:8501)
echo.
python -m streamlit run "%~dp0app\streamlit_app.py"
pause
