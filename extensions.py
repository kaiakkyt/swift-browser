import sys
import os
import shutil
import zipfile
import json
import importlib.util
import traceback
from pathlib import Path
from PyQt6.QtCore import QSettings, Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QTextEdit, QGroupBox, QFrame, QScrollArea, QWidget,
    QInputDialog, QTabWidget, QPlainTextEdit
)


class ExtensionManager:
    """Manages browser extensions (zip packages)."""
    
    def __init__(self, browser=None):
        self.browser = browser
        self.extensions = {}
        self.extension_info = {}
        self.extension_styles = {}
        self.disabled_extensions = set()
        self.extensions_dir = Path.home() / ".swift_browser" / "extensions"
        self.extensions_dir.mkdir(parents=True, exist_ok=True)
        
        self._load_disabled_extensions()
    
    def set_browser(self, browser):
        """Set browser reference after initialization."""
        self.browser = browser
    
    def _load_disabled_extensions(self):
        """Load list of disabled extensions from settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        disabled = settings.value("disabled_extensions", []) or []
        self.disabled_extensions = set(disabled)
    
    def _save_disabled_extensions(self):
        """Save disabled extensions list to settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        settings.setValue("disabled_extensions", list(self.disabled_extensions))
    
    def get_installed_extensions(self):
        """Get list of installed extension names from settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        return settings.value("installed_extensions", []) or []
    
    def _save_installed_extensions(self, extensions_list):
        """Save installed extensions list to settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        settings.setValue("installed_extensions", extensions_list)
    
    def _get_extension_path(self, name):
        """Get the folder path for an extension."""
        return self.extensions_dir / name
    
    def _get_main_py_path(self, name):
        """Get main.py path for an extension."""
        return self._get_extension_path(name) / "main.py"
    
    def _get_style_qss_path(self, name):
        """Get style.qss path for an extension."""
        return self._get_extension_path(name) / "style.qss"
    
    def _get_icon_path(self, name):
        """Get icon path for an extension (checks for .ico and .png)."""
        ext_path = self._get_extension_path(name)
        for icon_name in ["icon.ico", "icon.png", "icon.jpg", "icon.svg"]:
            icon_path = ext_path / icon_name
            if icon_path.exists():
                return icon_path
        return None
    
    def get_extension_icon(self, name):
        """Get QIcon for an extension."""
        icon_path = self._get_icon_path(name)
        if icon_path:
            return QIcon(str(icon_path))
        return None
    
    def _validate_extension_info(self, info, source_name):
        """Validate extension_info has required fields with correct types.
        
        Required format:
        extension_info = {
            "name": str,
            "version": str,
            "author": str,
            "description": str,
            "source": str  # GPL requirement - link to source code
        }
        """
        if info is None:
            raise ValueError(f"Extension '{source_name}' is missing required 'extension_info' dictionary")
        
        if not isinstance(info, dict):
            raise ValueError(f"Extension '{source_name}': extension_info must be a dictionary, got {type(info).__name__}")
        
        required_fields = {
            'name': str,
            'version': str,
            'author': str,
            'description': str,
            'source': str
        }
        
        for field, expected_type in required_fields.items():
            if field not in info:
                raise ValueError(f"Extension '{source_name}': extension_info missing required field '{field}'")
            
            value = info[field]
            if not isinstance(value, expected_type):
                raise ValueError(
                    f"Extension '{source_name}': extension_info['{field}'] must be {expected_type.__name__}, "
                    f"got {type(value).__name__}"
                )
            
            if not value.strip():
                raise ValueError(f"Extension '{source_name}': extension_info['{field}'] cannot be empty")
        
        return True
    
    def load_all_extensions(self):
        """Load all installed extensions on startup."""
        installed = self.get_installed_extensions()
        loaded = []
        failed = []
        
        for ext_name in installed:
            if ext_name in self.disabled_extensions:
                continue
            try:
                self._load_extension(ext_name)
                loaded.append(ext_name)
            except Exception as e:
                failed.append((ext_name, str(e)))
                print(f"Failed to load extension '{ext_name}': {e}")
        
        return loaded, failed
    
    def is_extension_enabled(self, name):
        """Check if an extension is enabled."""
        return name not in self.disabled_extensions
    
    def enable_extension(self, name):
        """Enable an extension and load it."""
        if name not in self.disabled_extensions:
            return
        
        self.disabled_extensions.discard(name)
        self._save_disabled_extensions()
        
        if name not in self.extensions:
            self._load_extension(name)
    
    def disable_extension(self, name):
        """Disable an extension and unload it."""
        if name in self.disabled_extensions:
            return
        
        if name in self.extensions:
            self._unload_extension_module(name)
        
        self.disabled_extensions.add(name)
        self._save_disabled_extensions()
    
    def _unload_extension_module(self, name):
        """Unload a single extension module."""
        if name not in self.extensions:
            return
        
        module = self.extensions[name]
        
        if hasattr(module, 'on_unload') and self.browser:
            try:
                module.on_unload(self.browser)
            except Exception as e:
                print(f"Error in {name}.on_unload(): {e}")
        
        if name in self.extension_styles and self.browser:
            self._remove_extension_style(name)
        
        del self.extensions[name]
    
    def _load_extension(self, name):
        """Load a single extension by name."""
        ext_path = self._get_extension_path(name)
        main_py = self._get_main_py_path(name)
        
        legacy_py = self.extensions_dir / f"{name}.py"
        if not ext_path.exists() and legacy_py.exists():
            self._migrate_legacy_extension(name)
        
        if not ext_path.exists():
            raise FileNotFoundError(f"Extension folder not found: {ext_path}")
        
        if not main_py.exists():
            raise FileNotFoundError(
                f"Extension '{name}' is missing required main.py file.\n"
                f"Expected location: {main_py}"
            )
        
        if str(ext_path) not in sys.path:
            sys.path.insert(0, str(ext_path))
        
        spec = importlib.util.spec_from_file_location(f"ext_{name}", main_py)
        module = importlib.util.module_from_spec(spec)
        
        try:
            spec.loader.exec_module(module)
        except SyntaxError as e:
            raise ValueError(f"Extension '{name}' has syntax errors in main.py:\n{e}")
        except Exception as e:
            raise RuntimeError(f"Error executing extension '{name}': {e}")
        
        info = getattr(module, 'extension_info', None)
        
        self._validate_extension_info(info, name)
        
        self.extensions[name] = module
        self.extension_info[name] = info
        
        style_qss = self._get_style_qss_path(name)
        if style_qss.exists() and self.browser:
            self._apply_extension_style(name, style_qss.read_text(encoding='utf-8'))
        
        if hasattr(module, 'on_load') and self.browser:
            try:
                module.on_load(self.browser)
            except Exception as e:
                print(f"Error in {name}.on_load(): {e}")
                traceback.print_exc()
        
        return info
    
    def _migrate_legacy_extension(self, name):
        """Migrate a legacy single .py file to folder structure."""
        legacy_py = self.extensions_dir / f"{name}.py"
        if not legacy_py.exists():
            return
        
        ext_path = self._get_extension_path(name)
        ext_path.mkdir(parents=True, exist_ok=True)
        
        shutil.move(str(legacy_py), str(ext_path / "main.py"))
        print(f"Migrated legacy extension '{name}' to folder structure")
    
    def _validate_zip_extension_info(self, zf, main_py_path, zip_name):
        """Validate extension_info in a zip file before extraction."""
        try:
            main_content = zf.read(main_py_path).decode('utf-8')
        except Exception as e:
            raise ValueError(f"Cannot read main.py from '{zip_name}': {e}")
        
        import ast
        try:
            tree = ast.parse(main_content)
        except SyntaxError as e:
            raise ValueError(
                f"Invalid extension package: '{zip_name}' contains syntax errors in main.py:\n"
                f"Line {e.lineno}: {e.msg}"
            )
        
        extension_info = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'extension_info':
                        try:
                            extension_info = ast.literal_eval(node.value)
                        except:
                            raise ValueError(
                                f"Invalid extension package: '{zip_name}' has malformed extension_info.\n"
                                "extension_info must be a simple dictionary literal."
                            )
        
        if extension_info is None:
            raise ValueError(
                f"Invalid extension package: '{zip_name}' is missing required extension_info.\n\n"
                "Extensions must define extension_info at module level:\n"
                "extension_info = {\n"
                '    "name": "Extension Name",\n'
                '    "version": "1.0",\n'
                '    "author": "Your Name",\n'
                '    "description": "What it does",\n'
                '    "source": "https://github.com/..."  # GPL required\n'
                "}"
            )
        
        self._validate_extension_info(extension_info, zip_name)
    
    def _apply_extension_style(self, name, qss):
        """Apply extension stylesheet."""
        if not self.browser:
            return
        
        self.extension_styles[name] = qss
        
        self._refresh_combined_styles()
    
    def _remove_extension_style(self, name):
        """Remove extension stylesheet."""
        if name in self.extension_styles:
            del self.extension_styles[name]
            self._refresh_combined_styles()
    
    def _refresh_combined_styles(self):
        """Refresh combined stylesheet from all loaded extensions."""
        if not self.browser:
            return
        
        self.browser._load_stylesheet()
        
        if self.extension_styles:
            current = self.browser.styleSheet()
            combined = current + "\n/* Extension Styles */\n"
            for name, qss in self.extension_styles.items():
                combined += f"\n/* Extension: {name} */\n{qss}\n"
            self.browser.setStyleSheet(combined)
    
    def install_extension(self, file_path):
        """Install an extension from a .zip or .py file."""
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if file_path.suffix == '.zip':
            return self._install_from_zip(file_path)
        elif file_path.suffix == '.py':
            return self._install_from_py(file_path)
        else:
            raise ValueError("Extension must be a .zip or .py file")
    
    def _install_from_zip(self, zip_path):
        """Install extension from a zip file."""
        ext_name = zip_path.stem
        
        ext_path = self._get_extension_path(ext_name)
        if ext_path.exists():
            raise ValueError(f"Extension '{ext_name}' is already installed")
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                names = zf.namelist()
                
                main_py_found = None
                if 'main.py' in names:
                    main_py_found = 'main.py'
                else:
                    for name in names:
                        if name.endswith('main.py') and not name.startswith('__'):
                            main_py_found = name
                            break
                
                if not main_py_found:
                    raise ValueError(
                        f"Invalid extension package: '{zip_path.name}' does not contain main.py.\n"
                        "Extension packages must include a main.py file at the root."
                    )
                
                self._validate_zip_extension_info(zf, main_py_found, zip_path.name)
                
                ext_path.mkdir(parents=True, exist_ok=True)
                
                if main_py_found == 'main.py':
                    zf.extractall(ext_path)
                else:
                    prefix = str(Path(main_py_found).parent)
                    if prefix and prefix != '.':
                        for name in names:
                            if name.startswith(prefix):
                                new_name = name[len(prefix):].lstrip('/')
                                if new_name:
                                    target = ext_path / new_name
                                    if name.endswith('/'):
                                        target.mkdir(parents=True, exist_ok=True)
                                    else:
                                        target.parent.mkdir(parents=True, exist_ok=True)
                                        target.write_bytes(zf.read(name))
                    else:
                        zf.extractall(ext_path)
            
            info = self._load_extension(ext_name)
            
            if ext_name in self.disabled_extensions:
                self.disabled_extensions.discard(ext_name)
                self._save_disabled_extensions()
            
            installed = self.get_installed_extensions()
            if ext_name not in installed:
                installed.append(ext_name)
                self._save_installed_extensions(installed)
            
            return info
            
        except Exception as e:
            if ext_path.exists():
                shutil.rmtree(ext_path)
            raise
    
    def _install_from_py(self, py_path):
        """Install extension from a single .py file (legacy support)."""
        ext_name = py_path.stem
        
        ext_path = self._get_extension_path(ext_name)
        if ext_path.exists():
            raise ValueError(f"Extension '{ext_name}' is already installed")
        
        ext_path.mkdir(parents=True, exist_ok=True)
        shutil.copy2(py_path, ext_path / "main.py")
        
        try:
            info = self._load_extension(ext_name)
            
            if ext_name in self.disabled_extensions:
                self.disabled_extensions.discard(ext_name)
                self._save_disabled_extensions()
            
            installed = self.get_installed_extensions()
            if ext_name not in installed:
                installed.append(ext_name)
                self._save_installed_extensions(installed)
            
            return info
            
        except Exception as e:
            if ext_path.exists():
                shutil.rmtree(ext_path)
            raise
    
    def uninstall_extension(self, name):
        """Uninstall an extension."""
        if name in self.extensions:
            self._unload_extension_module(name)
        
        if name in self.extension_info:
            del self.extension_info[name]
        
        if name in self.disabled_extensions:
            self.disabled_extensions.discard(name)
            self._save_disabled_extensions()
        
        installed = self.get_installed_extensions()
        if name in installed:
            installed.remove(name)
            self._save_installed_extensions(installed)
        
        ext_path = self._get_extension_path(name)
        if ext_path.exists():
            shutil.rmtree(ext_path)
        
        legacy_py = self.extensions_dir / f"{name}.py"
        if legacy_py.exists():
            legacy_py.unlink()
    
    def reload_extension(self, name):
        """Reload an extension (useful for development)."""
        if name not in self.extensions:
            raise ValueError(f"Extension '{name}' is not loaded")
        
        self._unload_extension_module(name)
        return self._load_extension(name)
    
    def get_extension_source(self, name):
        """Get the main.py source code of an extension."""
        main_py = self._get_main_py_path(name)
        if main_py.exists():
            return main_py.read_text(encoding='utf-8')
        return None
    
    def get_extension_style(self, name):
        """Get the style.qss content of an extension."""
        style_qss = self._get_style_qss_path(name)
        if style_qss.exists():
            return style_qss.read_text(encoding='utf-8')
        return ""
    
    def save_extension_source(self, name, source):
        """Save main.py source code."""
        main_py = self._get_main_py_path(name)
        main_py.write_text(source, encoding='utf-8')
    
    def save_extension_style(self, name, style):
        """Save style.qss content."""
        style_qss = self._get_style_qss_path(name)
        if style.strip():
            style_qss.write_text(style, encoding='utf-8')
        elif style_qss.exists():
            style_qss.unlink()
    
    def export_extension(self, name, dest_path):
        """Export an extension as a zip file."""
        ext_path = self._get_extension_path(name)
        if not ext_path.exists():
            raise FileNotFoundError(f"Extension '{name}' not found")
        
        with zipfile.ZipFile(dest_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file in ext_path.rglob('*'):
                if file.is_file():
                    arcname = file.relative_to(ext_path)
                    zf.write(file, arcname)
        
        return dest_path


class ExtensionsDialog(QDialog):
    """Dialog for managing extensions."""
    
    def __init__(self, extension_manager, parent=None):
        super().__init__(parent)
        self.ext_manager = extension_manager
        self.setWindowTitle("Extensions")
        self.setMinimumSize(800, 550)
        self._setup_ui()
        self._refresh_list()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        warning = QLabel(
            "⚠️ WARNING: Extensions have FULL ACCESS to the browser and your system. "
            "Only install extensions from sources you trust!"
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("""
            QLabel {
                background: #3d2020;
                color: #ff9999;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
        """)
        layout.addWidget(warning)
        
        content_layout = QHBoxLayout()
        
        list_group = QGroupBox("Installed Extensions")
        list_layout = QVBoxLayout(list_group)
        
        self.ext_list = QListWidget()
        self.ext_list.setIconSize(QSize(24, 24))
        self.ext_list.currentItemChanged.connect(self._on_selection_changed)
        list_layout.addWidget(self.ext_list)
        
        list_btn_layout = QHBoxLayout()
        
        self.install_btn = QPushButton("Install...")
        self.install_btn.clicked.connect(self._install_extension)
        list_btn_layout.addWidget(self.install_btn)
        
        self.create_btn = QPushButton("Create New...")
        self.create_btn.clicked.connect(self._create_extension)
        list_btn_layout.addWidget(self.create_btn)
        
        self.uninstall_btn = QPushButton("Uninstall")
        self.uninstall_btn.clicked.connect(self._uninstall_extension)
        self.uninstall_btn.setEnabled(False)
        list_btn_layout.addWidget(self.uninstall_btn)
        
        list_layout.addLayout(list_btn_layout)
        content_layout.addWidget(list_group, 1)
        
        details_group = QGroupBox("Extension Details")
        details_layout = QVBoxLayout(details_group)
        
        header_layout = QHBoxLayout()
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(48, 48)
        self.icon_label.setScaledContents(True)
        header_layout.addWidget(self.icon_label)
        
        name_layout = QVBoxLayout()
        self.name_label = QLabel("Select an extension")
        self.name_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        name_layout.addWidget(self.name_label)
        self.version_label = QLabel("")
        name_layout.addWidget(self.version_label)
        header_layout.addLayout(name_layout, 1)
        details_layout.addLayout(header_layout)
        
        self.author_label = QLabel("")
        details_layout.addWidget(self.author_label)
        
        self.desc_label = QLabel("")
        self.desc_label.setWordWrap(True)
        details_layout.addWidget(self.desc_label)
        
        self.source_label = QLabel("")
        self.source_label.setOpenExternalLinks(True)
        self.source_label.setStyleSheet("color: #6090e0;")
        details_layout.addWidget(self.source_label)
        
        details_layout.addStretch()
        
        self.enable_btn = QPushButton("Enable Extension")
        self.enable_btn.clicked.connect(self._toggle_extension)
        self.enable_btn.setEnabled(False)
        details_layout.addWidget(self.enable_btn)
        
        self.reload_btn = QPushButton("Reload Extension")
        self.reload_btn.clicked.connect(self._reload_extension)
        self.reload_btn.setEnabled(False)
        details_layout.addWidget(self.reload_btn)
        
        self.edit_btn = QPushButton("Edit Extension Files")
        self.edit_btn.clicked.connect(self._edit_extension)
        self.edit_btn.setEnabled(False)
        details_layout.addWidget(self.edit_btn)
        
        self.export_btn = QPushButton("Export as .zip")
        self.export_btn.clicked.connect(self._export_extension)
        self.export_btn.setEnabled(False)
        details_layout.addWidget(self.export_btn)
        
        self.open_folder_btn = QPushButton("Open Extensions Folder")
        self.open_folder_btn.clicked.connect(self._open_folder)
        details_layout.addWidget(self.open_folder_btn)
        
        content_layout.addWidget(details_group, 1)
        layout.addLayout(content_layout)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
    
    def _refresh_list(self):
        """Refresh the extension list."""
        self.ext_list.clear()
        
        installed = self.ext_manager.get_installed_extensions()
        
        for name in installed:
            info = self.ext_manager.extension_info.get(name, {})
            display_name = info.get('name', name)
            version = info.get('version', '?')
            
            is_disabled = name in self.ext_manager.disabled_extensions
            is_loaded = name in self.ext_manager.extensions
            
            item = QListWidgetItem(f"{display_name} (v{version})")
            item.setData(Qt.ItemDataRole.UserRole, name)
            
            icon = self.ext_manager.get_extension_icon(name)
            if icon:
                item.setIcon(icon)
            else:
                item.setIcon(QIcon())
            
            if is_disabled:
                item.setForeground(Qt.GlobalColor.gray)
                item.setText(f"{display_name} (v{version}) - DISABLED")
            elif is_loaded:
                item.setForeground(Qt.GlobalColor.green)
            else:
                item.setForeground(Qt.GlobalColor.red)
                item.setText(f"{display_name} (v{version}) - FAILED TO LOAD")
            
            self.ext_list.addItem(item)
        
        if not installed:
            item = QListWidgetItem("No extensions installed")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            item.setForeground(Qt.GlobalColor.gray)
            self.ext_list.addItem(item)
    
    def _on_selection_changed(self, current, previous):
        """Handle selection change."""
        if current is None:
            self._clear_details()
            return
        
        name = current.data(Qt.ItemDataRole.UserRole)
        if name is None:
            self._clear_details()
            return
        
        info = self.ext_manager.extension_info.get(name, {
            'name': name,
            'version': '?',
            'author': 'Unknown',
            'description': 'No information available'
        })
        
        icon = self.ext_manager.get_extension_icon(name)
        if icon:
            self.icon_label.setPixmap(icon.pixmap(48, 48))
        else:
            self.icon_label.clear()
            self.icon_label.setText("🧩")
            self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.name_label.setText(info.get('name', name))
        self.version_label.setText(f"Version: {info.get('version', '?')}")
        self.author_label.setText(f"Author: {info.get('author', 'Unknown')}")
        self.desc_label.setText(info.get('description', 'No description'))
        
        source_url = info.get('source', '')
        if source_url:
            self.source_label.setText(f'<a href="{source_url}">📦 View Source Code</a>')
        else:
            self.source_label.setText("")
        
        is_enabled = self.ext_manager.is_extension_enabled(name)
        self.enable_btn.setText("Disable Extension" if is_enabled else "Enable Extension")
        self.enable_btn.setEnabled(True)
        
        self.uninstall_btn.setEnabled(True)
        self.reload_btn.setEnabled(name in self.ext_manager.extensions)
        self.edit_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
    
    def _clear_details(self):
        """Clear the details panel."""
        self.icon_label.clear()
        self.name_label.setText("Select an extension")
        self.version_label.setText("")
        self.author_label.setText("")
        self.desc_label.setText("")
        self.source_label.setText("")
        self.enable_btn.setEnabled(False)
        self.uninstall_btn.setEnabled(False)
        self.reload_btn.setEnabled(False)
        self.edit_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
    
    def _toggle_extension(self):
        """Enable or disable the selected extension."""
        current = self.ext_list.currentItem()
        if not current:
            return
        
        name = current.data(Qt.ItemDataRole.UserRole)
        if not name:
            return
        
        is_enabled = self.ext_manager.is_extension_enabled(name)
        
        try:
            if is_enabled:
                self.ext_manager.disable_extension(name)
                QMessageBox.information(
                    self, "Extension Disabled",
                    f"'{name}' has been disabled."
                )
            else:
                self.ext_manager.enable_extension(name)
                QMessageBox.information(
                    self, "Extension Enabled",
                    f"'{name}' has been enabled and loaded."
                )
            self._refresh_list()
        except Exception as e:
            QMessageBox.critical(
                self, "Error",
                f"Failed to {'disable' if is_enabled else 'enable'} extension:\n{e}"
            )
    
    def _install_extension(self):
        """Install a new extension."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Extension File",
            "", "Extension Packages (*.zip);;Python Files (*.py);;All Files (*)"
        )
        
        if not file_path:
            return
        
        reply = QMessageBox.warning(
            self, "Security Warning",
            f"You are about to install an extension from:\n{file_path}\n\n"
            "Extensions have FULL ACCESS to the browser and can execute any code.\n"
            "Only install extensions you trust!\n\n"
            "Do you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            info = self.ext_manager.install_extension(file_path)
            QMessageBox.information(
                self, "Extension Installed",
                f"Successfully installed: {info.get('name', 'Extension')}"
            )
            self._refresh_list()
        except Exception as e:
            QMessageBox.critical(
                self, "Installation Failed",
                f"Failed to install extension:\n{e}"
            )
    
    def _uninstall_extension(self):
        """Uninstall selected extension."""
        current = self.ext_list.currentItem()
        if not current:
            return
        
        name = current.data(Qt.ItemDataRole.UserRole)
        if not name:
            return
        
        reply = QMessageBox.question(
            self, "Confirm Uninstall",
            f"Are you sure you want to uninstall '{name}'?\n"
            "The extension will be completely removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.ext_manager.uninstall_extension(name)
                QMessageBox.information(
                    self, "Extension Removed",
                    f"'{name}' has been uninstalled."
                )
                self._refresh_list()
            except Exception as e:
                QMessageBox.critical(
                    self, "Uninstall Failed",
                    f"Failed to uninstall extension:\n{e}"
                )
    
    def _reload_extension(self):
        """Reload selected extension."""
        current = self.ext_list.currentItem()
        if not current:
            return
        
        name = current.data(Qt.ItemDataRole.UserRole)
        if not name:
            return
        
        try:
            self.ext_manager.reload_extension(name)
            QMessageBox.information(
                self, "Extension Reloaded",
                f"'{name}' has been reloaded."
            )
            self._refresh_list()
        except Exception as e:
            QMessageBox.critical(
                self, "Reload Failed",
                f"Failed to reload extension:\n{e}"
            )
    
    def _edit_extension(self):
        """Open editor dialog for extension files."""
        current = self.ext_list.currentItem()
        if not current:
            return
        
        name = current.data(Qt.ItemDataRole.UserRole)
        if not name:
            return
        
        dialog = ExtensionEditorDialog(name, self.ext_manager, self)
        dialog.exec()
        self._refresh_list()
    
    def _export_extension(self):
        """Export extension as zip file."""
        current = self.ext_list.currentItem()
        if not current:
            return
        
        name = current.data(Qt.ItemDataRole.UserRole)
        if not name:
            return
        
        dest_path, _ = QFileDialog.getSaveFileName(
            self, "Export Extension",
            f"{name}.zip", "Zip Files (*.zip)"
        )
        
        if not dest_path:
            return
        
        try:
            self.ext_manager.export_extension(name, dest_path)
            QMessageBox.information(
                self, "Export Complete",
                f"Extension exported to:\n{dest_path}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Export Failed",
                f"Failed to export extension:\n{e}"
            )
    
    def _create_extension(self):
        """Create a new extension from template."""
        name, ok = QInputDialog.getText(
            self, "Create Extension",
            "Enter extension name (no spaces, letters/numbers/underscores only):"
        )
        
        if not ok or not name:
            return
        
        import re
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
            QMessageBox.warning(
                self, "Invalid Name",
                "Extension name must start with a letter or underscore,\n"
                "and contain only letters, numbers, and underscores."
            )
            return
        
        ext_path = self.ext_manager._get_extension_path(name)
        if ext_path.exists():
            QMessageBox.warning(
                self, "Already Exists",
                f"An extension named '{name}' already exists."
            )
            return
        
        ext_path.mkdir(parents=True, exist_ok=True)
        
        main_template = f'''# Extension: {name}
# A custom extension for Swift Browser

extension_info = {{
    "name": "{name.replace('_', ' ').title()}",
    "version": "1.0",
    "author": "You",
    "description": "A custom extension for Swift Browser.",
    "source": "https://github.com/yourusername/{name}"  # GPL required - link to source code
}}

def on_load(browser):
    """Called when the extension is loaded.
    
    Args:
        browser: The main Browser instance. Access:
            - browser.tabs: Tab widget
            - browser.current_web_view(): Current page
            - browser.toolbar: Main toolbar
            - browser.status_bar: Status bar
            - browser.new_tab(url): Open new tab
            - browser.setStyleSheet(qss): Apply styles
    """
    print(f"{{extension_info['name']}} loaded!")
    browser.status_bar.showMessage(f"{{extension_info['name']}} loaded!", 3000)

def on_unload(browser):
    """Called when the extension is unloaded or disabled.
    
    Clean up any UI elements or resources here.
    """
    print(f"{{extension_info['name']}} unloaded!")
'''
        
        style_template = '''/* Extension Stylesheet */
/* Add your custom styles here */
/* These will be applied when the extension is loaded */

/* Example:
#addressBar {
    border: 2px solid #ff6b6b;
}
*/
'''
        
        try:
            (ext_path / "main.py").write_text(main_template, encoding='utf-8')
            (ext_path / "style.qss").write_text(style_template, encoding='utf-8')
            
            installed = self.ext_manager.get_installed_extensions()
            installed.append(name)
            self.ext_manager._save_installed_extensions(installed)
            
            self.ext_manager._load_extension(name)
            
            QMessageBox.information(
                self, "Extension Created",
                f"Extension '{name}' has been created!\n\n"
                "Files created:\n"
                "• main.py - Extension code\n"
                "• style.qss - Custom styling\n\n"
                "Click 'Edit Extension Files' to customize."
            )
            self._refresh_list()
            
        except Exception as e:
            if ext_path.exists():
                shutil.rmtree(ext_path)
            QMessageBox.critical(
                self, "Error",
                f"Failed to create extension:\n{e}"
            )
    
    def _open_folder(self):
        """Open extensions folder in file explorer."""
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ext_manager.extensions_dir)))


class ExtensionEditorDialog(QDialog):
    """Dialog for editing extension files (main.py, style.qss)."""
    
    def __init__(self, ext_name, ext_manager, parent=None):
        super().__init__(parent)
        self.ext_name = ext_name
        self.ext_manager = ext_manager
        self.setWindowTitle(f"Edit Extension: {ext_name}")
        self.setMinimumSize(900, 700)
        self._setup_ui()
        self._load_files()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        info = QLabel("⚠️ Changes require reloading the extension to take effect.")
        info.setStyleSheet("color: #ffcc00; padding: 5px; background: #2a2a40; border-radius: 4px;")
        layout.addWidget(info)
        
        self.tabs = QTabWidget()
        
        main_tab = QWidget()
        main_layout = QVBoxLayout(main_tab)
        self.main_edit = QPlainTextEdit()
        self.main_edit.setStyleSheet("""
            QPlainTextEdit {
                font-family: Consolas, Monaco, 'Courier New', monospace;
                font-size: 12px;
                background: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
            }
        """)
        main_layout.addWidget(self.main_edit)
        self.tabs.addTab(main_tab, "📄 main.py")
        
        style_tab = QWidget()
        style_layout = QVBoxLayout(style_tab)
        style_info = QLabel("Define custom QSS styles here. They'll be applied when the extension loads.")
        style_info.setStyleSheet("color: #888;")
        style_layout.addWidget(style_info)
        self.style_edit = QPlainTextEdit()
        self.style_edit.setStyleSheet("""
            QPlainTextEdit {
                font-family: Consolas, Monaco, 'Courier New', monospace;
                font-size: 12px;
                background: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
            }
        """)
        style_layout.addWidget(self.style_edit)
        self.tabs.addTab(style_tab, "🎨 style.qss")
        
        layout.addWidget(self.tabs)
        
        btn_layout = QHBoxLayout()
        
        save_btn = QPushButton("Save All")
        save_btn.clicked.connect(self._save_files)
        btn_layout.addWidget(save_btn)
        
        save_reload_btn = QPushButton("Save && Reload")
        save_reload_btn.clicked.connect(self._save_and_reload)
        btn_layout.addWidget(save_reload_btn)
        
        btn_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
    
    def _load_files(self):
        """Load extension files into editors."""
        source = self.ext_manager.get_extension_source(self.ext_name)
        if source:
            self.main_edit.setPlainText(source)
        
        style = self.ext_manager.get_extension_style(self.ext_name)
        self.style_edit.setPlainText(style)
    
    def _save_files(self):
        """Save all extension files."""
        try:
            self.ext_manager.save_extension_source(self.ext_name, self.main_edit.toPlainText())
            self.ext_manager.save_extension_style(self.ext_name, self.style_edit.toPlainText())
            QMessageBox.information(self, "Saved", "Extension files saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")
    
    def _save_and_reload(self):
        """Save files and reload extension."""
        try:
            self.ext_manager.save_extension_source(self.ext_name, self.main_edit.toPlainText())
            self.ext_manager.save_extension_style(self.ext_name, self.style_edit.toPlainText())
            
            if self.ext_name in self.ext_manager.extensions:
                self.ext_manager.reload_extension(self.ext_name)
                QMessageBox.information(self, "Success", "Extension saved and reloaded!")
            else:
                QMessageBox.information(self, "Saved", "Files saved. Enable the extension to load it.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed:\n{e}")


extension_manager = ExtensionManager()
