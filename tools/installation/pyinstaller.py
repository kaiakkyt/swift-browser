import subprocess
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
APP_NAME = "Swift Browser"

MAIN_SCRIPT = PROJECT_ROOT / "app.pyw"
ICON_FILE = PROJECT_ROOT / "icon.ico"
ISS_SCRIPT = PROJECT_ROOT / "tools" / "installation" / "setup.iss"
ISCC_PATH = Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")

DATA_FILES = [
    (PROJECT_ROOT / "app.qss", "."),
    (PROJECT_ROOT / "extensions.py", "."),
    (PROJECT_ROOT / "icon.ico", "."),
    (PROJECT_ROOT / "documents", "documents"),
    (PROJECT_ROOT / "sample_extensions", "sample_extensions"),
]

HIDDEN_IMPORTS = [
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtNetwork",
]

def build():
    """Build the executable using PyInstaller and then the Installer using Inno Setup."""
    
    try:
        import PyInstaller
        print(f"PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--windowed",
        "--onedir",
        "--noconfirm",
        "--clean",
    ]
    
    if ICON_FILE.exists():
        cmd.extend(["--icon", str(ICON_FILE)])
    
    for src, dest in DATA_FILES:
        if src.exists():
            cmd.extend(["--add-data", f"{src};{dest}"])
            print(f"  Adding: {src.name} -> {dest}")
        else:
            print(f"  Warning: {src} not found, skipping")
    
    for imp in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", imp])
    
    cmd.append(str(MAIN_SCRIPT))
    
    print(f"\nBuilding {APP_NAME}...")
    subprocess.run(cmd, cwd=PROJECT_ROOT)

    if (PROJECT_ROOT / "dist" / APP_NAME).exists():
        print(f"\n✓ PyInstaller Build successful!")
        
        if ISCC_PATH.exists() and ISS_SCRIPT.exists():
            print(f"\n--- Starting Inno Setup Compiler ---")
            iscc_cmd = [str(ISCC_PATH), str(ISS_SCRIPT)]
            result = subprocess.run(iscc_cmd, cwd=ISS_SCRIPT.parent)
            
            if result.returncode == 0:
                print(f"\nInstaller created successfully!")
            else:
                print(f"\nInno Setup failed with exit code {result.returncode}")
        else:
            print(f"\nSkipping Inno Setup: ISCC.exe or setup.iss not found.")
            print(f"  Looked for ISS at: {ISS_SCRIPT}")
    else:
        print(f"\n✗ PyInstaller Build failed.")
        sys.exit(1)


if __name__ == "__main__":
    build()
