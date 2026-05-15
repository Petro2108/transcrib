@echo off
chcp 65001 >nul

if not exist .env (
    echo ОШИБКА: файл .env не найден. Сначала запустите setup.bat
    pause & exit /b 1
)

rem Запуск без консольного окна (pythonw)
start "" pythonw transcriber.py
