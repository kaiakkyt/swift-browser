from PyQt6.QtGui import QCursor, QPixmap
from PyQt6.QtCore import Qt, QObject, QEvent
from PyQt6.QtWidgets import QApplication, QWidget
from pathlib import Path

extension_info = {
    "name": "ruby cursor",
    "version": "1.0",
    "author": "KaiakK",
    "description": "replaces the default cursor with ruby from bfdi",
    "source": "https://github.com/kaiakkyt"
}

_cursor_filter = None
_ruby_cursor = None

class CursorOverrideFilter(QObject):
    
    def __init__(self, cursor, browser):
        super().__init__()
        self.cursor = cursor
        self.browser = browser
    
    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Enter, QEvent.Type.MouseMove):
            if isinstance(obj, QWidget) and obj.cursor() != self.cursor:
                obj.setCursor(self.cursor)
        return False

def _apply_cursor_recursive(widget, cursor):

    widget.setCursor(cursor)
    for child in widget.findChildren(QWidget):
        child.setCursor(cursor)

def on_load(browser):

    global _cursor_filter, _ruby_cursor
    
    ext_dir = Path(__file__).parent
    ruby_path = ext_dir / "ruby.png"
    
    if not ruby_path.exists():
        browser.status_bar.showMessage("yeah idk what happened", 3000)
        return
    
    pixmap = QPixmap(str(ruby_path))
    
    if pixmap.width() > 40 or pixmap.height() > 40:
        pixmap = pixmap.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, 
                               Qt.TransformationMode.SmoothTransformation)
    
    _ruby_cursor = QCursor(pixmap, pixmap.width()//2, pixmap.height()//2)
    
    _apply_cursor_recursive(browser, _ruby_cursor)
    
    _cursor_filter = CursorOverrideFilter(_ruby_cursor, browser)
    QApplication.instance().installEventFilter(_cursor_filter)
    
    QApplication.setOverrideCursor(_ruby_cursor)

def on_unload(browser):

    global _cursor_filter, _ruby_cursor
    
    QApplication.restoreOverrideCursor()
    
    if _cursor_filter:
        QApplication.instance().removeEventFilter(_cursor_filter)
        _cursor_filter = None
    
    browser.unsetCursor()
    for widget in browser.findChildren(QWidget):
        widget.unsetCursor()
    
    _ruby_cursor = None
