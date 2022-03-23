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
cd updater
pyinstaller --onefile --clean update_launcher.py
pyinstaller --onefile --clean updater.py
cd ..