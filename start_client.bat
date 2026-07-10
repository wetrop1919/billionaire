@echo off
cd /d C:\Users\user\Desktop\billionaire
call venv\Scripts\activate
set PYTHONPATH=C:\Users\user\Desktop\billionaire
python client/main.py
pause