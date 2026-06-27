@echo off
echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo Building executable...
pyinstaller --noconfirm --onedir --windowed --add-data "src;src/" --hidden-import PyQt5 src/main.py
echo Build complete. The executable is in the dist/main directory.
pause
