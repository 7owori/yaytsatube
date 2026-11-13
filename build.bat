@echo off
rem Сборка Yaytsatube-Setup.exe на Windows. Нужен Python 3.12+.
python -m pip install -r requirements.txt pyinstaller || exit /b 1
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Yaytsatube-Setup ^
  --icon assets\icon.ico --add-data "app\ui.html;." --add-data "assets\icon.ico;." app\eggtube.py || exit /b 1
echo.
echo Готово: dist\Yaytsatube-Setup.exe. Запусти его: он сам предложит установку.
