This project is managed by Google Jules. 

I do not have the time and level of coding skills to develop this project myself, therefore the program has been created in collaboration with Google's Jules, an AI coding agent that can repond to pull requests if people have issues in the future.

If the AI causes any major issues to the code in a new release, please contact me so I can work on a resolution.

If you would like to take over the project or expand it beyong just the gear360, feel free to reach out :)

## Building the Executable

If you are compiling the program yourself and encounter a `ModuleNotFoundError` (such as missing `PyQt5`), it means dependencies were not properly installed or bundled by PyInstaller.

To build the executable correctly:

**Windows:**
Run the provided `build.bat` script.

**Linux/macOS:**
Run the provided `build.sh` script:
```bash
./build.sh
```

These scripts will automatically install the necessary requirements from `requirements.txt` and run PyInstaller with the correct flags. The resulting application will be placed in the `dist/main` directory.
