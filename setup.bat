@echo off
chcp 65001 >nul
echo =========================================
echo  Установка Транскрибатора
echo =========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ОШИБКА: Python не найден. Установите Python 3.10+ с python.org
    pause & exit /b 1
)

echo [1/3] Обновление pip...
python -m pip install --upgrade pip --quiet

echo [2/3] Установка зависимостей...
pip install -r requirements.txt

echo [3/3] Проверка .env...
if not exist .env (
    copy .env.example .env >nul
    echo.
    echo ВНИМАНИЕ: Создан файл .env
    echo Откройте его и вставьте ваш Deepgram API ключ!
    echo Получить ключ: https://console.deepgram.com
) else (
    echo .env уже существует — пропуск.
)

echo.
echo =========================================
echo  Установка завершена!
echo  Следующий шаг: отредактируйте .env
echo  Затем запустите run.bat
echo =========================================
pause
