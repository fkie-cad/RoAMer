@ECHO OFF
cd receiver
pyinstaller --onefile --clean main.py
cd ..
cd whitelister
pyinstaller --onefile --clean PeHeaderWhitelister.py
cd ..
cd unpacker
pyinstaller --onefile --clean main.py
cd ..