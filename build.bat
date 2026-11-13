@echo off
rem Сборка Yaytsatube.exe на Windows. Нужен Python 3.12+.
python -m pip install -r requirements.txt pyinstaller || exit /b 1
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Yaytsatube ^
  --icon assets\icon.ico --add-data "app\ui.html;." --add-data "assets\icon.ico;." app\eggtube.py || exit /b 1
echo.
echo Готово: dist\Yaytsatube.exe. Запусти его: он сам предложит установку.
