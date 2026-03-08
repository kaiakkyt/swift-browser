import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
APP_NAME = "Swift Browser"

MAIN_SCRIPT = PROJECT_ROOT / "app.pyw"
ICON_FILE = PROJECT_ROOT / "icon.ico"

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
    """Build the executable using PyInstaller."""
    
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
    print(f"Command: {' '.join(cmd)}\n")
    
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    
    if result.returncode == 0:
        output_dir = PROJECT_ROOT / "dist" / APP_NAME
        print(f"\n✓ Build successful!")
        print(f"  Output: {output_dir}")
        print(f"\n  Run '{APP_NAME}.exe' from the dist folder.")
    else:
        print(f"\n✗ Build failed with exit code {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
