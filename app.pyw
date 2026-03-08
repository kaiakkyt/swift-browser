import sys
import os
import re
from pathlib import Path
from functools import partial

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from PyQt6.QtCore import (
    Qt, QUrl, QSize, QThread, pyqtSignal, QTimer, QSettings, QByteArray,
    QStringListModel, QBuffer, QIODevice, QProcess, QPropertyAnimation,
    QEasingCurve
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTabBar, QLineEdit, QToolBar, QToolButton, QMenu,
    QStatusBar, QProgressBar, QDialog, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QFileDialog, QMessageBox, QSplitter, QFrame, QStyle,
    QStyleOptionTab, QStylePainter, QCompleter, QScrollArea, QSizePolicy,
    QInputDialog, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QComboBox, QGroupBox, QTextEdit, QDockWidget, QPlainTextEdit,
    QGraphicsBlurEffect
)
from PyQt6.QtGui import (
    QAction, QIcon, QKeySequence, QShortcut, QFont, QPalette, QColor,
    QDesktopServices, QPixmap, QClipboard
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage, QWebEngineSettings,
    QWebEngineUrlRequestInterceptor, QWebEngineDownloadRequest
)
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog

from extensions import extension_manager, ExtensionsDialog

SEARCH_ENGINES = {
    "Google": "https://www.google.com/search?q=",
    "Bing": "https://www.bing.com/search?q=",
    "DuckDuckGo": "https://duckduckgo.com/?q=",
    "Yahoo": "https://search.yahoo.com/search?p=",
    "Ecosia": "https://www.ecosia.org/search?q=",
}

SITE_POPUPS = {
    "twitter.com": ("🐦 Bird App", "Touch grass? Never heard of it."),
    "x.com": ("🐦 Bird App", "Touch grass? Never heard of it."),
    "tiktok.com": ("⏰ Time Machine", "Spending 12 hours a day on this?"),
    "instagram.com": ("📸 Two Sides", "Racist reels or comparisons?"),
    "pinterest.com": ("📌 DIY Delusions", "I'll totally make that..."),
    "twitch.tv": ("🎮 Donation Station", "Just one more stream..."),
    "amazon.com": ("🛒 Wallet Destroyer", "Your bank account is crying btw!"),
    "pornhub.com": ("🤨 Caught in 4K", "Down bad, huh?"),
    "rule34.xxx": ("😭 Caught in 8K", "I mean I guess bro, whatever you like.."),
    "chatgpt.com": ("🤖 AI Overlords", "Asking for homework help again?"),
    "discord.com": ("🎧 Touch Grass Simulator", "Friends? In THIS economy?"),
    "spotify.com": ("🎵 Music Lover", "It better be a banger?"),
    "yahoo.com": ("⏳ Time Traveler", "Welcome back to 2005!"),
    "theshooter.pages.dev": ("😮 Wait what?", "Is that my game!?"),
    "thestarfields.pages.dev": ("😮 Wait what?", "Is that my website!?"),
}

class AdBlocker(QWebEngineUrlRequestInterceptor):
    BLOCKED_DOMAINS = {
        'doubleclick.net', 'googlesyndication.com', 'googleadservices.com',
        'google-analytics.com', 'googletagmanager.com', 'googletagservices.com',
        'facebook.com/tr', 'connect.facebook.net', 'pixel.facebook.com',
        'ads.twitter.com', 'analytics.twitter.com',
        'adservice.google.com', 'pagead2.googlesyndication.com',
        'adsserver.', 'adserver.', 'tracking.', 'tracker.',
        'analytics.', 'telemetry.', 'metrics.', 'beacon.',
        'taboola.com', 'outbrain.com', 'criteo.com', 'quantserve.com',
        'scorecardresearch.com', 'chartbeat.com', 'optimizely.com',
        'hotjar.com', 'mouseflow.com', 'fullstory.com', 'crazyegg.com',
        'mixpanel.com', 'segment.com', 'amplitude.com',
        'pubmatic.com', 'rubiconproject.com', 'openx.net',
        'adnxs.com', 'adsrvr.org', 'demdex.net', 'krxd.net',
        'bluekai.com', 'exelator.com', 'eyeota.net',
        'moatads.com', 'doubleverify.com', 'adsafeprotected.com',
        'newrelic.com', 'nr-data.net',
        'sentry.io', 'sentry-cdn.com',
        'bugsnag.com', 'rollbar.com',
        'omtrdc.net', 'demdex.com', '2o7.net',
        'branch.io', 'app.link',
        'appsflyer.com', 'adjust.com', 'kochava.com',
        'onetrust.com', 'cookielaw.org',
        'consensu.org', 'trustarc.com',
        'clarity.ms', 'mouseflow.com',
        'ipify.org', 'ipinfo.io', 'ipapi.co',
    }
    
    BLOCKED_PATTERNS = [
        r'/ads/', r'/ad/', r'/advertisement/', r'/tracking/',
        r'/tracker/', r'/analytics/', r'/telemetry/', r'/beacon/',
        r'\.gif\?.*track', r'pixel\.', r'/pixel/', r'_track',
        r'/collect\?', r'/log\?', r'/event\?',
        r'/fingerprint', r'\.fingerprint\.',
        r'/identify\?', r'/session\?', r'/visitor\?',
        r'canvas.*fingerprint', r'webgl.*fingerprint',
    ]
    
    def __init__(self, enabled=True):
        super().__init__()
        self.enabled = enabled
        self.blocked_count = 0
        self._compiled_patterns = [re.compile(p, re.I) for p in self.BLOCKED_PATTERNS]
    
    def interceptRequest(self, info):
        if not self.enabled:
            return
        
        url = info.requestUrl().toString().lower()
        host = info.requestUrl().host().lower()
        
        for domain in self.BLOCKED_DOMAINS:
            if domain in host or domain in url:
                info.block(True)
                self.blocked_count += 1
                return
        
        for pattern in self._compiled_patterns:
            if pattern.search(url):
                info.block(True)
                self.blocked_count += 1
                return


class BrowserPage(QWebEnginePage):
    """Custom web page with enhanced control over navigation."""
    
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.featurePermissionRequested.connect(self._handle_permission)
    
    def _handle_permission(self, url, feature):
        """Auto-grant permissions for media playback and other features."""
        auto_grant = [
            QWebEnginePage.Feature.MediaAudioCapture,
            QWebEnginePage.Feature.MediaVideoCapture,
            QWebEnginePage.Feature.MediaAudioVideoCapture,
            QWebEnginePage.Feature.Geolocation,
            QWebEnginePage.Feature.DesktopVideoCapture,
            QWebEnginePage.Feature.DesktopAudioVideoCapture,
            QWebEnginePage.Feature.Notifications,
        ]
        
        if feature in auto_grant:
            self.setFeaturePermission(url, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser)
        else:
            self.setFeaturePermission(url, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser)
    
    def certificateError(self, error):
        return False
    
    def javaScriptConsoleMessage(self, level, message, line, source):
        pass


class LazyWebView(QWebEngineView):
    """Web view with lazy loading - only loads URL when activated."""
    
    title_changed = pyqtSignal(str)
    icon_changed = pyqtSignal()
    load_started = pyqtSignal()
    load_finished = pyqtSignal(bool)
    url_changed = pyqtSignal(QUrl)
    
    def __init__(self, profile, url=None, parent=None):
        super().__init__(parent)
        self._profile = profile
        self._pending_url = url
        self._loaded = False
        self._page = None
        
        self.titleChanged.connect(self.title_changed.emit)
        self.iconChanged.connect(self.icon_changed.emit)
        self.loadStarted.connect(self.load_started.emit)
        self.loadFinished.connect(self._on_load_finished)
        self.urlChanged.connect(self.url_changed.emit)
    
    def _on_load_finished(self, ok):
        self._loaded = True
        self.load_finished.emit(ok)
    
    def activate(self):
        """Called when tab becomes active - loads content if not yet loaded."""
        if not self._loaded and self._pending_url:
            self._ensure_page()
            self.setUrl(QUrl(self._pending_url))
            self._pending_url = None
    
    def _ensure_page(self):
        """Create page on demand to save memory."""
        if self._page is None:
            self._page = BrowserPage(self._profile, self)
            self.setPage(self._page)
            self._configure_settings()
    
    def _configure_settings(self):
        """Configure web settings for performance and security."""
        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
    
    def navigate(self, url):
        """Navigate to URL, creating page if needed."""
        self._ensure_page()
        if not url.startswith(('http://', 'https://', 'file://')):
            if '.' in url and ' ' not in url:
                url = 'https://' + url
            else:
                url = f'https://www.google.com/search?q={url.replace(" ", "+")}'
        self.setUrl(QUrl(url))
    
    def navigate_with_search(self, url, search_url):
        """Navigate to URL with custom search engine."""
        self._ensure_page()
        if not url.startswith(('http://', 'https://', 'file://')):
            if '.' in url and ' ' not in url:
                url = 'https://' + url
            else:
                url = f'{search_url}{url.replace(" ", "+")}'
        self.setUrl(QUrl(url))
    
    def is_loaded(self):
        return self._loaded


class DownloadItem(QWidget):
    """Widget representing a single download."""
    
    def __init__(self, download: QWebEngineDownloadRequest, parent=None):
        super().__init__(parent)
        self.download = download
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        
        info_layout = QVBoxLayout()
        self.name_label = QLabel(Path(self.download.downloadFileName()).name)
        self.name_label.setObjectName("downloadFileName")
        self.status_label = QLabel("Starting...")
        self.status_label.setObjectName("downloadStatus")
        info_layout.addWidget(self.name_label)
        info_layout.addWidget(self.status_label)
        
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(200)
        self.progress.setMaximumHeight(16)
        
        self.cancel_btn = QToolButton()
        self.cancel_btn.setText("✕")
        self.cancel_btn.setObjectName("downloadCancel")
        self.cancel_btn.clicked.connect(self.download.cancel)
        
        self.open_btn = QToolButton()
        self.open_btn.setText("📂")
        self.open_btn.setObjectName("downloadOpen")
        self.open_btn.clicked.connect(self._open_file)
        self.open_btn.setVisible(False)
        
        layout.addLayout(info_layout, 1)
        layout.addWidget(self.progress)
        layout.addWidget(self.cancel_btn)
        layout.addWidget(self.open_btn)
    
    def _connect_signals(self):
        self.download.receivedBytesChanged.connect(self._update_progress)
        self.download.stateChanged.connect(self._update_state)
    
    def _update_progress(self):
        received = self.download.receivedBytes()
        total = self.download.totalBytes()
        if total > 0:
            self.progress.setValue(int(received * 100 / total))
            self.status_label.setText(f"{self._format_bytes(received)} / {self._format_bytes(total)}")
        else:
            self.status_label.setText(f"{self._format_bytes(received)}")
    
    def _update_state(self, state):
        if state == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            self.status_label.setText("Complete")
            self.progress.setValue(100)
            self.cancel_btn.setVisible(False)
            self.open_btn.setVisible(True)
        elif state == QWebEngineDownloadRequest.DownloadState.DownloadCancelled:
            self.status_label.setText("Cancelled")
            self.cancel_btn.setVisible(False)
        elif state == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
            self.status_label.setText("Failed")
            self.cancel_btn.setVisible(False)
    
    def _open_file(self):
        path = self.download.downloadDirectory() + "/" + self.download.downloadFileName()
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    
    @staticmethod
    def _format_bytes(size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


class DownloadManager(QDialog):
    """Dialog for managing downloads."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloads")
        self.setMinimumSize(500, 400)
        self._setup_ui()
        self.downloads = []
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        header = QHBoxLayout()
        header.addWidget(QLabel("Downloads"))
        header.addStretch()
        
        clear_btn = QPushButton("Clear Completed")
        clear_btn.clicked.connect(self._clear_completed)
        header.addWidget(clear_btn)
        layout.addLayout(header)
        
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.list_layout.setSpacing(4)
        
        layout.addWidget(self.list_widget, 1)
        
        self.empty_label = QLabel("No downloads yet")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setObjectName("emptyDownloads")
        layout.addWidget(self.empty_label)
    
    def add_download(self, download: QWebEngineDownloadRequest):
        self.empty_label.hide()
        item = DownloadItem(download, self)
        self.list_layout.addWidget(item)
        self.downloads.append(item)
        download.accept()
    
    def _clear_completed(self):
        for item in self.downloads[:]:
            state = item.download.state()
            if state in (
                QWebEngineDownloadRequest.DownloadState.DownloadCompleted,
                QWebEngineDownloadRequest.DownloadState.DownloadCancelled,
                QWebEngineDownloadRequest.DownloadState.DownloadInterrupted
            ):
                item.setParent(None)
                item.deleteLater()
                self.downloads.remove(item)
        
        if not self.downloads:
            self.empty_label.show()


class FindBar(QFrame):
    """Find-in-page toolbar."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("findBar")
        self._web_view = None
        self._setup_ui()
        self.hide()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Find in page...")
        self.search_input.setMaximumWidth(300)
        self.search_input.textChanged.connect(self._find)
        self.search_input.returnPressed.connect(self._find_next)
        
        self.prev_btn = QToolButton()
        self.prev_btn.setText("▲")
        self.prev_btn.clicked.connect(self._find_prev)
        
        self.next_btn = QToolButton()
        self.next_btn.setText("▼")
        self.next_btn.clicked.connect(self._find_next)
        
        self.match_label = QLabel()
        self.match_label.setObjectName("findMatchCount")
        
        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.clicked.connect(self.close_find)
        
        layout.addWidget(self.search_input)
        layout.addWidget(self.prev_btn)
        layout.addWidget(self.next_btn)
        layout.addWidget(self.match_label)
        layout.addStretch()
        layout.addWidget(self.close_btn)
    
    def set_web_view(self, web_view):
        self._web_view = web_view
    
    def show_find(self):
        self.show()
        self.search_input.setFocus()
        self.search_input.selectAll()
    
    def close_find(self):
        self.hide()
        if self._web_view:
            self._web_view.findText("")
    
    def _find(self, text=None):
        if self._web_view and text:
            self._web_view.findText(text)
    
    def _find_next(self):
        if self._web_view:
            self._web_view.findText(self.search_input.text())
    
    def _find_prev(self):
        if self._web_view:
            self._web_view.findText(
                self.search_input.text(),
                QWebEnginePage.FindFlag.FindBackward
            )


class BrowserTabBar(QTabBar):
    """Custom tab bar with close buttons and new tab button."""
    
    new_tab_requested = pyqtSignal()
    mute_tab_requested = pyqtSignal(int)
    pin_tab_requested = pyqtSignal(int)
    duplicate_tab_requested = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMovable(True)
        self.setTabsClosable(True)
        self.setExpanding(False)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.setDocumentMode(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
    
    def _show_context_menu(self, pos):
        """Show tab context menu."""
        index = self.tabAt(pos)
        if index >= 0:
            menu = QMenu(self)
            
            mute_action = QAction("🔇 Mute/Unmute Tab", self)
            mute_action.triggered.connect(lambda: self.mute_tab_requested.emit(index))
            menu.addAction(mute_action)
            
            pin_action = QAction("📌 Pin/Unpin Tab", self)
            pin_action.triggered.connect(lambda: self.pin_tab_requested.emit(index))
            menu.addAction(pin_action)
            
            menu.addSeparator()
            
            dup_action = QAction("Duplicate Tab", self)
            dup_action.triggered.connect(lambda: self.duplicate_tab_requested.emit(index))
            menu.addAction(dup_action)
            
            menu.addSeparator()
            
            close_action = QAction("Close Tab", self)
            close_action.triggered.connect(lambda: self.tabCloseRequested.emit(index))
            menu.addAction(close_action)
            
            menu.exec(self.mapToGlobal(pos))
    
    def mouseDoubleClickEvent(self, event):
        if self.tabAt(event.pos()) == -1:
            self.new_tab_requested.emit()
        super().mouseDoubleClickEvent(event)


class Browser(QMainWindow):
    """Main browser window with tabs, navigation, and all features."""
    
    HOME_PAGE = "https://www.google.com"
    MAX_HISTORY = 500
    MAX_CLOSED_TABS = 25
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Swift Browser")
        self.setMinimumSize(1200, 800)
        
        self._setup_profile()
        
        self.history = []
        self.history_model = QStringListModel()
        self._load_history()
        
        self.bookmarks = []
        self._load_bookmarks()
        
        self.closed_tabs = []
        self.pinned_tabs = set()
        self.muted_tabs = set()
        self.split_mode = False
        self.split_view = None
        self.shown_popups = set()
        
        self.site_permissions = {}
        self._load_site_permissions()
        
        self.download_manager = DownloadManager(self)
        
        self.clipboard_history = []
        self._load_clipboard_history()
        self.privacy_blur_active = False
        self.blur_effects = {}
        self.search_engine = "Google"
        self._load_search_engine_setting()
        
        self._load_home_page_setting()
        
        self._setup_ui()
        self._setup_shortcuts()
        self._load_stylesheet()
        
        self._restore_window_geometry()
        self._load_session()
        
        self._init_extensions()
        
        self._setup_clipboard_monitor()
        
        self._setup_side_panels()
    
    def _init_extensions(self):
        """Initialize and load extensions."""
        extension_manager.set_browser(self)
        loaded, failed = extension_manager.load_all_extensions()
        
        if loaded:
            print(f"Loaded {len(loaded)} extension(s): {', '.join(loaded)}")
        if failed:
            for name, error in failed:
                print(f"Failed to load extension '{name}': {error}")
    
    def _setup_profile(self):
        """Configure browser profile with ad blocking and persistent login."""
        storage_path = Path.home() / ".swift_browser" / "profile"
        storage_path.mkdir(parents=True, exist_ok=True)
        
        self.profile = QWebEngineProfile("SwiftBrowser", self)
        
        self.profile.setPersistentStoragePath(str(storage_path))
        
        cache_path = Path.home() / ".swift_browser" / "cache"
        cache_path.mkdir(parents=True, exist_ok=True)
        self.profile.setCachePath(str(cache_path))
        
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        
        self.profile.settings().setAttribute(
            QWebEngineSettings.WebAttribute.WebGLEnabled, True
        )
        self.profile.settings().setAttribute(
            QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True
        )
        self.profile.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalStorageEnabled, True
        )
        self.profile.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self.profile.settings().setAttribute(
            QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
        )
        self.profile.settings().setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True
        )
        self.profile.settings().setAttribute(
            QWebEngineSettings.WebAttribute.AllowWindowActivationFromJavaScript, True
        )
        
        self.profile.setHttpUserAgent(
            self.profile.httpUserAgent() + " DNT/1"
        )
        self.profile.settings().setAttribute(
            QWebEngineSettings.WebAttribute.HyperlinkAuditingEnabled, False
        )
        self.profile.settings().setAttribute(
            QWebEngineSettings.WebAttribute.ScreenCaptureEnabled, False
        )
        
        self.ad_blocker = AdBlocker(enabled=True)
        self.profile.setUrlRequestInterceptor(self.ad_blocker)
        
        self.profile.downloadRequested.connect(self._handle_download)
    
    def _setup_ui(self):
        """Build the main UI."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self._setup_toolbar()
        layout.addWidget(self.toolbar)
        
        self._setup_bookmark_bar()
        layout.addWidget(self.bookmark_bar)
        
        self.tabs = QTabWidget()
        self.tab_bar = BrowserTabBar(self.tabs)
        self.tabs.setTabBar(self.tab_bar)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setIconSize(QSize(18, 18))
        
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tab_bar.new_tab_requested.connect(lambda: self.new_tab())
        self.tab_bar.mute_tab_requested.connect(self._toggle_mute_tab)
        self.tab_bar.pin_tab_requested.connect(self._toggle_pin_tab)
        self.tab_bar.duplicate_tab_requested.connect(self._duplicate_tab)
        
        layout.addWidget(self.tabs, 1)
        
        self.find_bar = FindBar()
        layout.addWidget(self.find_bar)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(150)
        self.progress_bar.setMaximumHeight(16)
        self.progress_bar.hide()
        self.status_bar.addPermanentWidget(self.progress_bar)
        
        self.blocked_label = QLabel("🛡️ 0 blocked")
        self.blocked_label.setObjectName("blockedLabel")
        self.status_bar.addPermanentWidget(self.blocked_label)
    
    def _setup_toolbar(self):
        """Create navigation toolbar."""
        self.toolbar = QToolBar()
        self.toolbar.setObjectName("navigationBar")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        
        self.back_btn = QToolButton()
        self.back_btn.setText("←")
        self.back_btn.setObjectName("navButton")
        self.back_btn.setToolTip("Back (Alt+Left)")
        self.back_btn.clicked.connect(self._go_back)
        self.toolbar.addWidget(self.back_btn)
        
        self.forward_btn = QToolButton()
        self.forward_btn.setText("→")
        self.forward_btn.setObjectName("navButton")
        self.forward_btn.setToolTip("Forward (Alt+Right)")
        self.forward_btn.clicked.connect(self._go_forward)
        self.toolbar.addWidget(self.forward_btn)
        
        self.refresh_btn = QToolButton()
        self.refresh_btn.setText("↻")
        self.refresh_btn.setObjectName("navButton")
        self.refresh_btn.setToolTip("Refresh (F5)")
        self.refresh_btn.clicked.connect(self._refresh)
        self.toolbar.addWidget(self.refresh_btn)
        
        self.home_btn = QToolButton()
        self.home_btn.setText("⌂")
        self.home_btn.setObjectName("navButton")
        self.home_btn.setToolTip("Home (Alt+Home)")
        self.home_btn.clicked.connect(self._go_home)
        self.toolbar.addWidget(self.home_btn)
        
        self.ai_btn = QToolButton()
        self.ai_btn.setText("✨")
        self.ai_btn.setObjectName("aiButton")
        self.ai_btn.setToolTip("AI Mode - Google AI Search")
        self.ai_btn.clicked.connect(self._open_ai_mode)
        self.toolbar.addWidget(self.ai_btn)
        
        self.new_tab_btn = QToolButton()
        self.new_tab_btn.setText("+")
        self.new_tab_btn.setObjectName("newTabButton")
        self.new_tab_btn.setToolTip("New Tab (Ctrl+T)")
        self.new_tab_btn.clicked.connect(lambda: self.new_tab())
        self.toolbar.addWidget(self.new_tab_btn)
        
        self.toolbar.addSeparator()
        
        self.address_bar = QLineEdit()
        self.address_bar.setObjectName("addressBar")
        self.address_bar.setPlaceholderText("Enter URL or search...")
        self.address_bar.returnPressed.connect(self._navigate_to_url)
        
        self.completer = QCompleter(self.history_model, self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.setMaxVisibleItems(10)
        self.address_bar.setCompleter(self.completer)
        
        self.toolbar.addWidget(self.address_bar)
        
        self.toolbar.addSeparator()
        
        self.adblock_btn = QToolButton()
        self.adblock_btn.setText("🛡️")
        self.adblock_btn.setObjectName("adblockButton")
        self.adblock_btn.setToolTip("Toggle Ad Blocker")
        self.adblock_btn.setCheckable(True)
        adblock_enabled = self._load_adblock_setting()
        self.adblock_btn.setChecked(adblock_enabled)
        self.ad_blocker.enabled = adblock_enabled
        self.adblock_btn.clicked.connect(self._toggle_adblock)
        self.toolbar.addWidget(self.adblock_btn)
        
        self.search_engine_btn = QToolButton()
        self.search_engine_btn.setText("🔍")
        self.search_engine_btn.setObjectName("navButton")
        self.search_engine_btn.setToolTip("Search Engine")
        self.search_engine_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._setup_search_engine_menu()
        self.toolbar.addWidget(self.search_engine_btn)
        
        self.taskman_btn = QToolButton()
        self.taskman_btn.setText("📊")
        self.taskman_btn.setObjectName("navButton")
        self.taskman_btn.setToolTip("Task Manager (Shift+Esc)")
        self.taskman_btn.clicked.connect(self._show_task_manager)
        self.toolbar.addWidget(self.taskman_btn)
        
        self.notepad_btn = QToolButton()
        self.notepad_btn.setText("📝")
        self.notepad_btn.setObjectName("navButton")
        self.notepad_btn.setToolTip("Quick Notepad")
        self.notepad_btn.clicked.connect(self._toggle_notepad)
        self.toolbar.addWidget(self.notepad_btn)
        
        self.clipboard_btn = QToolButton()
        self.clipboard_btn.setText("📋")
        self.clipboard_btn.setObjectName("navButton")
        self.clipboard_btn.setToolTip("Clipboard History")
        self.clipboard_btn.setCheckable(True)
        self.clipboard_btn.clicked.connect(self._toggle_clipboard_panel)
        self.toolbar.addWidget(self.clipboard_btn)
        
        self.blur_btn = QToolButton()
        self.blur_btn.setText("🔒")
        self.blur_btn.setObjectName("navButton")
        self.blur_btn.setToolTip("Privacy Blur (Ctrl+B)")
        self.blur_btn.setCheckable(True)
        self.blur_btn.clicked.connect(self._toggle_privacy_blur)
        self.toolbar.addWidget(self.blur_btn)
        
        self.extensions_btn = QToolButton()
        self.extensions_btn.setText("🧩")
        self.extensions_btn.setObjectName("navButton")
        self.extensions_btn.setToolTip("Extensions")
        self.extensions_btn.clicked.connect(self._show_extensions)
        self.toolbar.addWidget(self.extensions_btn)
        
        self.downloads_btn = QToolButton()
        self.downloads_btn.setText("⬇")
        self.downloads_btn.setObjectName("navButton")
        self.downloads_btn.setToolTip("Downloads (Ctrl+J)")
        self.downloads_btn.clicked.connect(self._show_downloads)
        self.toolbar.addWidget(self.downloads_btn)
        
        self.menu_btn = QToolButton()
        self.menu_btn.setText("☰")
        self.menu_btn.setObjectName("menuButton")
        self.menu_btn.setToolTip("Menu")
        self.menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._setup_menu()
        self.toolbar.addWidget(self.menu_btn)
        
        self.split_btn = QToolButton()
        self.split_btn.setText("⊞")
        self.split_btn.setObjectName("navButton")
        self.split_btn.setToolTip("Toggle Split View")
        self.split_btn.setCheckable(True)
        self.split_btn.clicked.connect(self._toggle_split_view)
        self.toolbar.addWidget(self.split_btn)
    
    def _setup_menu(self):
        """Create main menu."""
        menu = QMenu(self)
        
        def add_action(text, slot, shortcut=None):
            action = QAction(text, self)
            action.triggered.connect(slot)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            menu.addAction(action)
            return action
        
        add_action("New Tab", lambda: self.new_tab(), "Ctrl+T")
        add_action("New Private Tab", self._new_private_tab, "Ctrl+Shift+N")
        add_action("Reopen Closed Tab", self._reopen_closed_tab, "Ctrl+Shift+T")
        menu.addSeparator()
        add_action("Print Page", self._print_page, "Ctrl+P")
        menu.addSeparator()
        add_action("Bookmark This Page", self._bookmark_current_page, "Ctrl+D")
        add_action("Manage Bookmarks", self._manage_bookmarks)
        menu.addSeparator()
        add_action("History", self._show_history, "Ctrl+H")
        
        self.recently_closed_menu = menu.addMenu("Recently Closed")
        self._update_recently_closed_menu()
        
        add_action("Find in Page", self._show_find, "Ctrl+F")
        add_action("Downloads", self._show_downloads, "Ctrl+J")
        menu.addSeparator()
        
        add_action("Mute/Unmute Tab", self._toggle_mute_current_tab, "Ctrl+M")
        add_action("Pin/Unpin Tab", self._toggle_pin_current_tab, "Ctrl+Shift+P")
        menu.addSeparator()
        
        add_action("View Page Source", self._view_page_source, "Ctrl+U")
        add_action("Toggle Split View", self._toggle_split_view)
        menu.addSeparator()
        
        add_action("Screenshot Page", self._take_screenshot, "Ctrl+Shift+S")
        menu.addSeparator()
        
        tools_menu = menu.addMenu("More Tools")
        task_action = QAction("Task Manager", self)
        task_action.setShortcut(QKeySequence("Shift+Esc"))
        task_action.triggered.connect(self._show_task_manager)
        tools_menu.addAction(task_action)
        
        perms_action = QAction("Site Permissions", self)
        perms_action.triggered.connect(self._show_site_permissions)
        tools_menu.addAction(perms_action)
        
        shortcuts_action = QAction("Keyboard Shortcuts", self)
        shortcuts_action.setShortcut(QKeySequence("F1"))
        shortcuts_action.triggered.connect(self._show_shortcuts_help)
        tools_menu.addAction(shortcuts_action)
        
        tools_menu.addSeparator()
        
        settings_action = QAction("Home Page Settings", self)
        settings_action.triggered.connect(self._show_home_settings)
        tools_menu.addAction(settings_action)
        
        tools_menu.addSeparator()
        
        extensions_action = QAction("Extensions", self)
        extensions_action.triggered.connect(self._show_extensions)
        tools_menu.addAction(extensions_action)
        
        google_menu = menu.addMenu("Google Services")
        google_services = [
            ("Gmail", "https://mail.google.com"),
            ("Drive", "https://drive.google.com"),
            ("YouTube", "https://www.youtube.com"),
            ("Maps", "https://maps.google.com"),
            ("Calendar", "https://calendar.google.com"),
            ("Photos", "https://photos.google.com"),
            ("Translate", "https://translate.google.com"),
            ("News", "https://news.google.com"),
        ]
        for name, url in google_services:
            action = QAction(name, self)
            action.triggered.connect(lambda checked, u=url: self.new_tab(u))
            google_menu.addAction(action)
        
        menu.addSeparator()
        add_action("Zoom In", self._zoom_in, "Ctrl++")
        add_action("Zoom Out", self._zoom_out, "Ctrl+-")
        add_action("Reset Zoom", self._zoom_reset, "Ctrl+0")
        menu.addSeparator()
        add_action("Full Screen", self._toggle_fullscreen, "F11")
        menu.addSeparator()
        add_action("Clear Browsing Data", self._clear_data)
        menu.addSeparator()
        add_action("About", self._show_about)
        
        self.menu_btn.setMenu(menu)
    
    def _setup_shortcuts(self):
        """Set up keyboard shortcuts."""
        QShortcut(QKeySequence("Ctrl+T"), self, self.new_tab)
        QShortcut(QKeySequence("Ctrl+W"), self, self._close_current_tab)
        QShortcut(QKeySequence("Ctrl+Tab"), self, self._next_tab)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, self._prev_tab)
        QShortcut(QKeySequence("Ctrl+L"), self, self._focus_address_bar)
        QShortcut(QKeySequence("Alt+Left"), self, self._go_back)
        QShortcut(QKeySequence("Alt+Right"), self, self._go_forward)
        QShortcut(QKeySequence("F5"), self, self._refresh)
        QShortcut(QKeySequence("Ctrl+R"), self, self._refresh)
        QShortcut(QKeySequence("Escape"), self, self._escape_pressed)
        QShortcut(QKeySequence("Ctrl+F"), self, self._show_find)
        QShortcut(QKeySequence("Ctrl+H"), self, self._show_history)
        QShortcut(QKeySequence("Ctrl+D"), self, self._bookmark_current_page)
        QShortcut(QKeySequence("F11"), self, self._toggle_fullscreen)
        QShortcut(QKeySequence("Alt+Home"), self, self._go_home)
        QShortcut(QKeySequence("Ctrl+Shift+T"), self, self._reopen_closed_tab)
        QShortcut(QKeySequence("Ctrl+U"), self, self._view_page_source)
        QShortcut(QKeySequence("Ctrl+M"), self, self._toggle_mute_current_tab)
        QShortcut(QKeySequence("Ctrl+Shift+P"), self, self._toggle_pin_current_tab)
        QShortcut(QKeySequence("Ctrl+P"), self, self._print_page)
        QShortcut(QKeySequence("Shift+Esc"), self, self._show_task_manager)
        QShortcut(QKeySequence("F1"), self, self._show_shortcuts_help)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, self._take_screenshot)
        QShortcut(QKeySequence("Ctrl+Shift+N"), self, self._new_private_tab)
        QShortcut(QKeySequence("Ctrl+B"), self, self._toggle_privacy_blur)
    
    def _setup_bookmark_bar(self):
        """Create bookmark bar below toolbar."""
        self.bookmark_bar = QFrame()
        self.bookmark_bar.setObjectName("bookmarkBar")
        self.bookmark_bar.setFixedHeight(36)
        
        layout = QHBoxLayout(self.bookmark_bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        
        self.bookmark_container = QWidget()
        self.bookmark_layout = QHBoxLayout(self.bookmark_container)
        self.bookmark_layout.setContentsMargins(0, 0, 0, 0)
        self.bookmark_layout.setSpacing(4)
        self.bookmark_layout.addStretch()
        
        layout.addWidget(self.bookmark_container, 1)
        
        self._update_bookmark_bar()
    
    def _load_bookmarks(self):
        """Load bookmarks from settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        saved = settings.value("bookmarks", [])
        if saved:
            self.bookmarks = saved
    
    def _save_bookmarks(self):
        """Save bookmarks to settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        settings.setValue("bookmarks", self.bookmarks)
    
    def _save_session(self):
        """Save current session (open tabs, pinned, muted) to settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        
        tabs_data = []
        for i in range(self.tabs.count()):
            web_view = self.tabs.widget(i)
            if isinstance(web_view, LazyWebView):
                url = web_view.url().toString() if web_view.url() else ""
                if url and url not in ("about:blank", ""):
                    tabs_data.append({
                        "url": url,
                        "pinned": i in self.pinned_tabs,
                        "muted": i in self.muted_tabs
                    })
        
        settings.setValue("session_tabs", tabs_data)
    
    def _load_session(self):
        """Load previous session (open tabs, pinned, muted) from settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        tabs_data = settings.value("session_tabs", [])
        
        if tabs_data:
            for i, tab_info in enumerate(tabs_data):
                url = tab_info.get("url", self.HOME_PAGE)
                web_view = self.new_tab(url)
                
                if tab_info.get("pinned", False):
                    self.pinned_tabs.add(i)
                
                if tab_info.get("muted", False):
                    self.muted_tabs.add(i)
                    web_view.load_finished.connect(
                        lambda ok, idx=i: self._apply_mute_on_load(idx)
                    )
            
            for i in range(self.tabs.count()):
                self._update_tab_mute_icon(i)
            
            if self.tabs.count() > 0:
                self.tabs.setCurrentIndex(0)
        else:
            self.new_tab(self.HOME_PAGE)
    
    def _apply_mute_on_load(self, index):
        """Apply mute state after tab loads."""
        if index in self.muted_tabs:
            web_view = self.tabs.widget(index)
            if isinstance(web_view, LazyWebView) and web_view._page:
                web_view.page().setAudioMuted(True)
    
    def closeEvent(self, event):
        """Save session and window geometry before closing."""
        self._save_session()
        self._save_window_geometry()
        self._save_all_preferences()
        event.accept()
    
    def _save_all_preferences(self):
        """Save all user preferences."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        settings.setValue("adblock_enabled", self.ad_blocker.enabled)
        settings.setValue("clipboard_history", self.clipboard_history)
    
    def _load_clipboard_history(self):
        """Load clipboard history from settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        saved = settings.value("clipboard_history", [])
        if saved:
            self.clipboard_history = saved
    
    def _load_adblock_setting(self):
        """Load ad blocker state from settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        enabled = settings.value("adblock_enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.lower() == 'true'
        return enabled if isinstance(enabled, bool) else True
    
    def _save_window_geometry(self):
        """Save window position and size."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        settings.setValue("window_geometry", self.saveGeometry())
        settings.setValue("window_state", self.saveState())
    
    def _restore_window_geometry(self):
        """Restore window position and size."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        geometry = settings.value("window_geometry")
        state = settings.value("window_state")
        if geometry:
            self.restoreGeometry(geometry)
        if state:
            self.restoreState(state)
    
    def _update_bookmark_bar(self):
        """Refresh bookmark bar buttons."""
        while self.bookmark_layout.count() > 1:
            item = self.bookmark_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        for i, bm in enumerate(self.bookmarks):
            btn = QToolButton()
            btn.setText(bm.get("title", "Bookmark")[:20])
            btn.setObjectName("bookmarkButton")
            btn.setToolTip(bm.get("url", ""))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            
            if bm.get("favicon"):
                try:
                    icon = QIcon()
                    pixmap = QPixmap()
                    pixmap.loadFromData(bm["favicon"])
                    icon.addPixmap(pixmap)
                    btn.setIcon(icon)
                except:
                    pass
            
            btn.clicked.connect(lambda checked, url=bm.get("url"): self._open_bookmark(url))
            
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, idx=i: self._bookmark_context_menu(idx, pos))
            
            self.bookmark_layout.insertWidget(self.bookmark_layout.count() - 1, btn)
    
    def _bookmark_current_page(self):
        """Add current page to bookmarks."""
        web_view = self.tabs.currentWidget()
        if not isinstance(web_view, LazyWebView):
            return
        
        url = web_view.url().toString()
        title = web_view.title() or url
        
        for bm in self.bookmarks:
            if bm.get("url") == url:
                self.status_bar.showMessage("Already bookmarked!", 2000)
                return
        
        favicon_bytes = None
        icon = web_view.icon()
        if not icon.isNull():
            pixmap = icon.pixmap(16, 16)
            ba = QByteArray()
            buffer = QBuffer(ba)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            pixmap.save(buffer, "PNG")
            favicon_bytes = bytes(ba)
        
        self.bookmarks.append({
            "url": url,
            "title": title,
            "favicon": favicon_bytes
        })
        self._save_bookmarks()
        self._update_bookmark_bar()
        self.status_bar.showMessage(f"Bookmarked: {title[:30]}", 2000)
    
    def _open_bookmark(self, url):
        """Open bookmark in current tab."""
        web_view = self.tabs.currentWidget()
        if isinstance(web_view, LazyWebView):
            web_view.navigate(url)
    
    def _bookmark_context_menu(self, index, pos):
        """Show context menu for bookmark."""
        menu = QMenu(self)
        
        delete_action = QAction("Delete Bookmark", self)
        delete_action.triggered.connect(lambda: self._delete_bookmark(index))
        menu.addAction(delete_action)
        
        edit_action = QAction("Edit Bookmark", self)
        edit_action.triggered.connect(lambda: self._edit_bookmark(index))
        menu.addAction(edit_action)
        
        menu.exec(self.sender().mapToGlobal(pos))
    
    def _delete_bookmark(self, index):
        """Delete a bookmark."""
        if 0 <= index < len(self.bookmarks):
            del self.bookmarks[index]
            self._save_bookmarks()
            self._update_bookmark_bar()
    
    def _edit_bookmark(self, index):
        """Edit bookmark title."""
        if 0 <= index < len(self.bookmarks):
            current_title = self.bookmarks[index].get("title", "")
            new_title, ok = QInputDialog.getText(
                self, "Edit Bookmark", "Title:", text=current_title
            )
            if ok and new_title:
                self.bookmarks[index]["title"] = new_title
                self._save_bookmarks()
                self._update_bookmark_bar()
    
    def _manage_bookmarks(self):
        """Show bookmark management dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Bookmarks")
        dialog.setMinimumSize(500, 400)
        
        layout = QVBoxLayout(dialog)
        
        bookmark_list = QListWidget()
        for bm in self.bookmarks:
            item = QListWidgetItem(f"{bm.get('title', 'Untitled')} - {bm.get('url', '')}")
            bookmark_list.addItem(item)
        layout.addWidget(bookmark_list)
        
        btn_layout = QHBoxLayout()
        
        delete_btn = QPushButton("Delete Selected")
        delete_btn.clicked.connect(lambda: self._delete_selected_bookmark(bookmark_list, dialog))
        btn_layout.addWidget(delete_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        dialog.exec()
    
    def _delete_selected_bookmark(self, list_widget, dialog):
        """Delete selected bookmark from manager."""
        row = list_widget.currentRow()
        if row >= 0:
            del self.bookmarks[row]
            self._save_bookmarks()
            self._update_bookmark_bar()
            list_widget.takeItem(row)
    
    def _load_stylesheet(self):
        """Load QSS stylesheet."""
        qss_path = Path(__file__).parent / "app.qss"
        if qss_path.exists():
            with open(qss_path, "r") as f:
                self.setStyleSheet(f.read())
    
    def new_tab(self, url=None):
        """Create a new tab."""
        if url is None:
            url = self.HOME_PAGE
        
        web_view = LazyWebView(self.profile, url)
        web_view.title_changed.connect(partial(self._update_tab_title, web_view))
        web_view.url_changed.connect(partial(self._update_url, web_view))
        web_view.icon_changed.connect(partial(self._update_tab_icon, web_view))
        web_view.load_started.connect(self._on_load_started)
        web_view.load_finished.connect(self._on_load_finished)
        web_view.page().fullScreenRequested.connect(self._handle_fullscreen_request) if web_view._page else None
        
        web_view.loadProgress.connect(self._update_progress)
        
        index = self.tabs.addTab(web_view, "New Tab")
        self.tabs.setCurrentIndex(index)
        
        return web_view
    
    def _new_private_tab(self):
        """Create a new private browsing tab (incognito mode)."""
        private_profile = QWebEngineProfile(self)
        private_profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        private_profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
        )
        private_profile.setUrlRequestInterceptor(self.ad_blocker)
        
        private_profile.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalStorageEnabled, True
        )
        private_profile.settings().setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptEnabled, True
        )
        
        web_view = LazyWebView(private_profile, self.HOME_PAGE)
        web_view._is_private = True
        web_view.title_changed.connect(partial(self._update_private_tab_title, web_view))
        web_view.url_changed.connect(partial(self._update_url, web_view))
        web_view.icon_changed.connect(partial(self._update_tab_icon, web_view))
        web_view.load_started.connect(self._on_load_started)
        web_view.load_finished.connect(self._on_load_finished)
        
        index = self.tabs.addTab(web_view, "🕶️ Private")
        self.tabs.setCurrentIndex(index)
        self.status_bar.showMessage("Private tab opened - no history or cookies will be saved", 3000)
    
    def _update_private_tab_title(self, web_view, title):
        """Update private tab title with incognito indicator."""
        index = self.tabs.indexOf(web_view)
        if index >= 0:
            display_title = title[:18] + "..." if len(title) > 18 else title
            self.tabs.setTabText(index, f"🕶️ {display_title}")
            if index == self.tabs.currentIndex():
                self.setWindowTitle(f"🕶️ {title} - Swift Browser (Private)")
    
    def close_tab(self, index):
        """Close a tab."""
        if index in self.pinned_tabs and self.tabs.count() > 1:
            self.status_bar.showMessage("Cannot close pinned tab. Unpin it first.", 3000)
            return
            
        if self.tabs.count() > 1:
            widget = self.tabs.widget(index)
            
            if isinstance(widget, LazyWebView):
                url = widget.url().toString() if widget.url() else ""
                title = self.tabs.tabText(index)
                icon = self.tabs.tabIcon(index)
                if url and url not in ("about:blank", ""):
                    self.closed_tabs.insert(0, {
                        "url": url,
                        "title": title,
                        "icon": icon
                    })
                    self.closed_tabs = self.closed_tabs[:self.MAX_CLOSED_TABS]
            
            new_pinned = set()
            for i in self.pinned_tabs:
                if i < index:
                    new_pinned.add(i)
                elif i > index:
                    new_pinned.add(i - 1)
            self.pinned_tabs = new_pinned
            
            new_muted = set()
            for i in self.muted_tabs:
                if i < index:
                    new_muted.add(i)
                elif i > index:
                    new_muted.add(i - 1)
            self.muted_tabs = new_muted
            
            self.tabs.removeTab(index)
            widget.deleteLater()
        else:
            self.close()
    
    def _close_current_tab(self):
        """Close the current tab."""
        self.close_tab(self.tabs.currentIndex())
    
    def _next_tab(self):
        """Switch to next tab."""
        index = (self.tabs.currentIndex() + 1) % self.tabs.count()
        self.tabs.setCurrentIndex(index)
    
    def _prev_tab(self):
        """Switch to previous tab."""
        index = (self.tabs.currentIndex() - 1) % self.tabs.count()
        self.tabs.setCurrentIndex(index)
    
    def _duplicate_tab(self, index):
        """Duplicate a tab."""
        web_view = self.tabs.widget(index)
        if isinstance(web_view, LazyWebView):
            url = web_view.url().toString() if web_view.url() else self.HOME_PAGE
            self.new_tab(url)
            self.status_bar.showMessage("Tab duplicated", 2000)
    
    def _on_tab_changed(self, index):
        """Handle tab change - activate lazy loading."""
        if index >= 0:
            web_view = self.tabs.widget(index)
            if isinstance(web_view, LazyWebView):
                web_view.activate()
                self._update_navigation_state()
                self._update_url(web_view, web_view.url())
                self.find_bar.set_web_view(web_view)
    
    def _update_tab_title(self, web_view, title):
        """Update tab title."""
        index = self.tabs.indexOf(web_view)
        if index >= 0:
            prefix = ""
            if index in self.pinned_tabs:
                prefix += "📌 "
            if index in self.muted_tabs:
                prefix += "🔇 "
            
            display_title = title[:20] + "..." if len(title) > 20 else title
            self.tabs.setTabText(index, prefix + display_title)
            if index == self.tabs.currentIndex():
                self.setWindowTitle(f"{title} - Swift Browser")
    
    def _update_tab_icon(self, web_view):
        """Update tab favicon."""
        index = self.tabs.indexOf(web_view)
        if index >= 0:
            icon = web_view.icon()
            if not icon.isNull():
                self.tabs.setTabIcon(index, icon)
    
    def _navigate_to_url(self):
        """Navigate to URL in address bar with calculator support."""
        url = self.address_bar.text().strip()
        if url:
            calc_result = self._try_calculate(url)
            if calc_result is not None:
                self.status_bar.showMessage(f"= {calc_result}", 5000)
            
            web_view = self.tabs.currentWidget()
            if isinstance(web_view, LazyWebView):
                search_url = SEARCH_ENGINES.get(self.search_engine, SEARCH_ENGINES["Google"])
                web_view.navigate_with_search(url, search_url)
    
    def _update_url(self, web_view, url):
        """Update address bar when URL changes."""
        if web_view == self.tabs.currentWidget():
            self.address_bar.setText(url.toString())
            self.address_bar.setCursorPosition(0)
            self._update_navigation_state()
    
    def _update_navigation_state(self):
        """Update back/forward button states."""
        web_view = self.tabs.currentWidget()
        if isinstance(web_view, LazyWebView) and web_view._page:
            history = web_view.history()
            self.back_btn.setEnabled(history.canGoBack())
            self.forward_btn.setEnabled(history.canGoForward())
    
    def _go_back(self):
        """Navigate back."""
        web_view = self.tabs.currentWidget()
        if isinstance(web_view, LazyWebView):
            web_view.back()
    
    def _go_forward(self):
        """Navigate forward."""
        web_view = self.tabs.currentWidget()
        if isinstance(web_view, LazyWebView):
            web_view.forward()
    
    def _refresh(self):
        """Refresh current page."""
        web_view = self.tabs.currentWidget()
        if isinstance(web_view, LazyWebView):
            web_view.reload()
    
    def _go_home(self):
        """Navigate to home page."""
        web_view = self.tabs.currentWidget()
        if isinstance(web_view, LazyWebView):
            web_view.navigate(self.HOME_PAGE)
    
    def _open_ai_mode(self):
        """Open Google AI search mode in new tab."""
        ai_url = "https://www.google.com/search?q=&udm=50"
        self.new_tab(ai_url)
    
    def _focus_address_bar(self):
        """Focus and select address bar."""
        self.address_bar.setFocus()
        self.address_bar.selectAll()
    
    def _on_load_started(self):
        """Handle page load start."""
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.refresh_btn.setText("✕")
    
    def _on_load_finished(self, ok):
        """Handle page load finish."""
        self.progress_bar.hide()
        self.refresh_btn.setText("↻")
        self._update_navigation_state()
        self._update_blocked_count()
        
        if ok:
            web_view = self.tabs.currentWidget()
            if isinstance(web_view, LazyWebView) and web_view.url():
                self._add_to_history(web_view.url())
                self._check_site_popup(web_view.url().toString())
    
    def _check_site_popup(self, url):
        """Check if URL matches a joke popup site and show it."""
        url_lower = url.lower()
        for domain, (title, message) in SITE_POPUPS.items():
            if domain in url_lower and domain not in self.shown_popups:
                self.shown_popups.add(domain)
                self._show_toast(title, message)
                break
    
    def _show_toast(self, title, message):
        """Show a toast notification popup."""
        self._current_toast = QDialog(self)
        toast = self._current_toast
        toast.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        toast.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        frame = QFrame(toast)
        frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a1a2e, stop:1 #16213e);
                border: 1px solid #4a4a6a;
                border-radius: 12px;
                padding: 15px;
            }
            QLabel#toastTitle {
                color: #ffffff;
                font-size: 16px;
                font-weight: bold;
            }
            QLabel#toastMessage {
                color: #a0a0b0;
                font-size: 13px;
            }
        """)
        
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 12, 15, 12)
        
        title_label = QLabel(title)
        title_label.setObjectName("toastTitle")
        layout.addWidget(title_label)
        
        msg_label = QLabel(message)
        msg_label.setObjectName("toastMessage")
        layout.addWidget(msg_label)
        
        toast_layout = QVBoxLayout(toast)
        toast_layout.setContentsMargins(0, 0, 0, 0)
        toast_layout.addWidget(frame)
        
        toast.adjustSize()
        
        main_geo = self.frameGeometry()
        toast.move(
            main_geo.x() + main_geo.width() - toast.width() - 20,
            main_geo.y() + main_geo.height() - toast.height() - 80
        )
        
        toast.show()
        toast.raise_()
        toast.activateWindow()
        
        QTimer.singleShot(4000, toast.close)
    
    def _update_progress(self, progress):
        """Update loading progress bar."""
        self.progress_bar.setValue(progress)
    
    def _update_blocked_count(self):
        """Update blocked requests count in status bar."""
        self.blocked_label.setText(f"🛡️ {self.ad_blocker.blocked_count} blocked")
    
    def _toggle_adblock(self, checked):
        """Toggle ad blocker."""
        self.ad_blocker.enabled = checked
        settings = QSettings("SwiftBrowser", "Swift Browser")
        settings.setValue("adblock_enabled", checked)
        self.status_bar.showMessage(
            "Ad blocker enabled" if checked else "Ad blocker disabled",
            3000
        )
    
    def _show_downloads(self):
        """Show download manager."""
        self.download_manager.show()
        self.download_manager.raise_()
    
    def _handle_download(self, download: QWebEngineDownloadRequest):
        """Handle download request."""
        suggested_name = download.downloadFileName()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save File", suggested_name
        )
        
        if path:
            download.setDownloadDirectory(str(Path(path).parent))
            download.setDownloadFileName(Path(path).name)
            self.download_manager.add_download(download)
            self.download_manager.show()
        else:
            download.cancel()
    
    def _show_find(self):
        """Show find bar."""
        web_view = self.tabs.currentWidget()
        if isinstance(web_view, LazyWebView):
            self.find_bar.set_web_view(web_view)
            self.find_bar.show_find()
    
    def _escape_pressed(self):
        """Handle escape key."""
        if self.find_bar.isVisible():
            self.find_bar.close_find()
        elif self.isFullScreen():
            self.showNormal()
    
    def _zoom_in(self):
        """Zoom in current page."""
        web_view = self.tabs.currentWidget()
        if isinstance(web_view, LazyWebView):
            web_view.setZoomFactor(web_view.zoomFactor() + 0.1)
    
    def _zoom_out(self):
        """Zoom out current page."""
        web_view = self.tabs.currentWidget()
        if isinstance(web_view, LazyWebView):
            web_view.setZoomFactor(max(0.25, web_view.zoomFactor() - 0.1))
    
    def _zoom_reset(self):
        """Reset zoom to default."""
        web_view = self.tabs.currentWidget()
        if isinstance(web_view, LazyWebView):
            web_view.setZoomFactor(1.0)
    
    def _toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
    
    def _handle_fullscreen_request(self, request):
        """Handle fullscreen request from web page."""
        if request.toggleOn():
            self.showFullScreen()
        else:
            self.showNormal()
        request.accept()
    
    def _clear_data(self):
        """Clear browsing data."""
        reply = QMessageBox.question(
            self, "Clear Browsing Data",
            "This will clear all cookies, cache, and browsing history.\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.profile.clearHttpCache()
            self.profile.cookieStore().deleteAllCookies()
            self.history.clear()
            self._save_history()
            self.status_bar.showMessage("Browsing data cleared", 3000)
    
    def _load_history(self):
        """Load browsing history from settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        self.history = settings.value("history", []) or []
        self.history_model.setStringList(self.history)
    
    def _save_history(self):
        """Save browsing history to settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        settings.setValue("history", self.history[:self.MAX_HISTORY])
        self.history_model.setStringList(self.history[:self.MAX_HISTORY])
    
    def _add_to_history(self, url):
        """Add URL to browsing history."""
        url_str = url if isinstance(url, str) else url.toString()
        if url_str and url_str not in ("about:blank", "") and not url_str.startswith("data:"):
            if url_str in self.history:
                self.history.remove(url_str)
            self.history.insert(0, url_str)
            self.history = self.history[:self.MAX_HISTORY]
            self._save_history()
    
    def _show_history(self):
        """Show browsing history dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Browsing History")
        dialog.setMinimumSize(500, 400)
        
        layout = QVBoxLayout(dialog)
        
        history_list = QListWidget()
        history_list.addItems(self.history[:100])
        layout.addWidget(history_list)
        
        btn_layout = QHBoxLayout()
        
        open_btn = QPushButton("Open")
        open_btn.clicked.connect(lambda: self._open_history_item(history_list, dialog))
        btn_layout.addWidget(open_btn)
        
        clear_btn = QPushButton("Clear History")
        clear_btn.clicked.connect(lambda: self._clear_history(dialog))
        btn_layout.addWidget(clear_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        history_list.itemDoubleClicked.connect(
            lambda item: (self.new_tab(item.text()), dialog.close())
        )
        
        dialog.exec()
    
    def _open_history_item(self, history_list, dialog):
        """Open selected history item."""
        item = history_list.currentItem()
        if item:
            self.new_tab(item.text())
            dialog.close()
    
    def _clear_history(self, dialog):
        """Clear all history."""
        self.history.clear()
        self._save_history()
        dialog.close()
        self.status_bar.showMessage("History cleared", 3000)
    
    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self, "About Swift Browser",
            "Swift Browser v1.0\n\n"
            "A lightweight Chromium-based browser\n"
            "Built with PyQt6 + QtWebEngine\n\n"
            "Features:\n"
            "• Built-in ad blocker\n"
            "• Lazy tab loading\n"
            "• Hardware acceleration\n"
            "• Private browsing\n"
            "• Download manager\n"
            "• Bookmarks with bar\n"
            "• History with autocomplete\n"
            "• View page source (Ctrl+U)\n"
            "• Mute/Pin tabs\n"
            "• Reopen closed tabs (Ctrl+Shift+T)\n"
            "• Split view mode\n"
            "• Task Manager\n"
            "• Site Permissions\n"
            "• Page Screenshot\n"
            "• Customizable Home Page\n"
            "• Extension Support"
        )
    
    
    def _print_page(self):
        """Print current page."""
        web_view = self.tabs.currentWidget()
        if isinstance(web_view, LazyWebView) and web_view._page:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            dialog = QPrintDialog(printer, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                web_view.page().print(printer, lambda ok: self.status_bar.showMessage(
                    "Printed successfully" if ok else "Print failed", 3000
                ))
    
    
    def _show_task_manager(self):
        """Show task manager with tab resource usage."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Task Manager - Swift Browser")
        dialog.setMinimumSize(700, 500)
        
        layout = QVBoxLayout(dialog)
        
        system_info = ""
        if HAS_PSUTIL:
            try:
                process = psutil.Process()
                mem_info = process.memory_info()
                cpu_percent = process.cpu_percent(interval=0.1)
                system_info = f"Browser Memory: {mem_info.rss / 1024 / 1024:.1f} MB | CPU: {cpu_percent:.1f}%"
            except:
                system_info = "System info unavailable"
        else:
            system_info = "Install psutil for accurate memory info (pip install psutil)"
        
        info_label = QLabel(system_info)
        info_label.setStyleSheet("color: #888; font-size: 11px; margin-bottom: 8px;")
        layout.addWidget(info_label)
        
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Tab", "URL", "Status", "Memory", "🔥 Impact"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSortingEnabled(True)
        
        tab_data = []
        for i in range(self.tabs.count()):
            web_view = self.tabs.widget(i)
            title = self.tabs.tabText(i)
            
            if isinstance(web_view, LazyWebView):
                url = web_view.url().toString() if web_view.url() else "Not loaded"
                is_loaded = web_view._loaded
                
                if not is_loaded:
                    mem_estimate = 5
                    impact = "Low"
                else:
                    url_lower = url.lower()
                    if any(x in url_lower for x in ['youtube', 'video', 'netflix', 'twitch']):
                        mem_estimate = 250
                        impact = "High"
                    elif any(x in url_lower for x in ['facebook', 'twitter', 'instagram', 'reddit']):
                        mem_estimate = 180
                        impact = "High"
                    elif any(x in url_lower for x in ['docs.google', 'sheets', 'drive']):
                        mem_estimate = 150
                        impact = "Medium"
                    elif 'google.com/search' in url_lower:
                        mem_estimate = 80
                        impact = "Low"
                    else:
                        mem_estimate = 100
                        impact = "Medium"
                
                tab_data.append({
                    'index': i,
                    'title': title,
                    'url': url,
                    'loaded': is_loaded,
                    'memory': mem_estimate,
                    'impact': impact
                })
        
        tab_data.sort(key=lambda x: x['memory'], reverse=True)
        
        table.setRowCount(len(tab_data))
        total_memory = 0
        
        for row, data in enumerate(tab_data):
            title_item = QTableWidgetItem(data['title'])
            title_item.setData(Qt.ItemDataRole.UserRole, data['index'])
            table.setItem(row, 0, title_item)
            
            url_text = data['url'][:60] + "..." if len(data['url']) > 60 else data['url']
            url_item = QTableWidgetItem(url_text)
            table.setItem(row, 1, url_item)
            
            status = "Active" if data['loaded'] else "Suspended"
            status_item = QTableWidgetItem(status)
            if data['loaded']:
                status_item.setForeground(QColor("#90EE90"))
            else:
                status_item.setForeground(QColor("#888"))
            table.setItem(row, 2, status_item)
            
            mem_item = QTableWidgetItem(f"{data['memory']} MB")
            mem_item.setData(Qt.ItemDataRole.UserRole, data['memory'])
            table.setItem(row, 3, mem_item)
            
            impact_item = QTableWidgetItem(data['impact'])
            if data['impact'] == "High":
                impact_item.setForeground(QColor("#FF6B6B"))
            elif data['impact'] == "Medium":
                impact_item.setForeground(QColor("#FFD93D"))
            else:
                impact_item.setForeground(QColor("#6BCB77"))
            table.setItem(row, 4, impact_item)
            
            total_memory += data['memory']
        
        layout.addWidget(table)
        
        highest_tab = tab_data[0]['title'] if tab_data else "None"
        summary = QLabel(
            f"Total tabs: {self.tabs.count()} | Estimated browser memory: ~{total_memory} MB\n"
            f"Highest impact tab: {highest_tab[:30]}"
        )
        summary.setStyleSheet("color: #aaa; font-size: 12px; margin-top: 8px;")
        layout.addWidget(summary)
        
        btn_layout = QHBoxLayout()
        
        end_btn = QPushButton("End Process")
        end_btn.clicked.connect(lambda: self._end_tab_process_new(table, tab_data, dialog))
        btn_layout.addWidget(end_btn)
        
        suspend_btn = QPushButton("Suspend Tab")
        suspend_btn.setToolTip("Unload tab to free memory")
        suspend_btn.clicked.connect(lambda: self._suspend_tab(table, tab_data, dialog))
        btn_layout.addWidget(suspend_btn)
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(lambda: (dialog.close(), self._show_task_manager()))
        btn_layout.addWidget(refresh_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        dialog.exec()
    
    def _end_tab_process_new(self, table, tab_data, dialog):
        """Close selected tab from task manager."""
        row = table.currentRow()
        if row >= 0 and row < len(tab_data):
            original_index = tab_data[row]['index']
            self.close_tab(original_index)
            dialog.close()
            self._show_task_manager()
    
    def _suspend_tab(self, table, tab_data, dialog):
        """Suspend a tab to free memory (reload when accessed)."""
        row = table.currentRow()
        if row >= 0 and row < len(tab_data):
            original_index = tab_data[row]['index']
            web_view = self.tabs.widget(original_index)
            if isinstance(web_view, LazyWebView) and web_view._loaded:
                url = web_view.url().toString()
                web_view._pending_url = url
                web_view._loaded = False
                if web_view._page:
                    web_view.setPage(None)
                    web_view._page = None
                self.status_bar.showMessage(f"Tab suspended: {tab_data[row]['title']}", 2000)
                dialog.close()
                self._show_task_manager()
    
    def _end_tab_process(self, table, dialog):
        """Close selected tab from task manager."""
        row = table.currentRow()
        if row >= 0:
            self.close_tab(row)
            dialog.close()
            self._show_task_manager()
    
    
    def _load_site_permissions(self):
        """Load saved site permissions."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        saved = settings.value("site_permissions", {})
        if isinstance(saved, dict):
            self.site_permissions = saved
    
    def _save_site_permissions(self):
        """Save site permissions."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        settings.setValue("site_permissions", self.site_permissions)
    
    def _show_site_permissions(self):
        """Show site permissions manager."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Site Permissions")
        dialog.setMinimumSize(600, 500)
        
        layout = QVBoxLayout(dialog)
        
        current_group = QGroupBox("Current Site")
        current_layout = QVBoxLayout(current_group)
        
        web_view = self.tabs.currentWidget()
        current_host = ""
        if isinstance(web_view, LazyWebView) and web_view.url():
            current_host = web_view.url().host()
        
        if current_host:
            host_label = QLabel(f"Site: {current_host}")
            host_label.setStyleSheet("font-weight: bold;")
            current_layout.addWidget(host_label)
            
            perms = self.site_permissions.get(current_host, {})
            
            for perm_name, perm_label in [
                ("javascript", "JavaScript"),
                ("images", "Images"),
                ("cookies", "Cookies"),
                ("popups", "Pop-ups"),
                ("notifications", "Notifications"),
            ]:
                row = QHBoxLayout()
                label = QLabel(perm_label)
                combo = QComboBox()
                combo.addItems(["Allow", "Block", "Ask"])
                combo.setCurrentText(perms.get(perm_name, "Allow"))
                combo.currentTextChanged.connect(
                    lambda val, h=current_host, p=perm_name: self._set_site_permission(h, p, val)
                )
                row.addWidget(label)
                row.addStretch()
                row.addWidget(combo)
                current_layout.addLayout(row)
        else:
            current_layout.addWidget(QLabel("No site loaded"))
        
        layout.addWidget(current_group)
        
        all_group = QGroupBox("All Site Permissions")
        all_layout = QVBoxLayout(all_group)
        
        sites_list = QListWidget()
        for host, perms in self.site_permissions.items():
            perm_str = ", ".join(f"{k}={v}" for k, v in perms.items())
            sites_list.addItem(f"{host}: {perm_str}")
        all_layout.addWidget(sites_list)
        
        clear_btn = QPushButton("Clear Selected Site")
        clear_btn.clicked.connect(lambda: self._clear_site_permission(sites_list))
        all_layout.addWidget(clear_btn)
        
        layout.addWidget(all_group)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        dialog.exec()
    
    def _set_site_permission(self, host, permission, value):
        """Set a permission for a site."""
        if host not in self.site_permissions:
            self.site_permissions[host] = {}
        self.site_permissions[host][permission] = value
        self._save_site_permissions()
        self.status_bar.showMessage(f"Set {permission} to {value} for {host}", 2000)
    
    def _clear_site_permission(self, list_widget):
        """Clear permissions for selected site."""
        item = list_widget.currentItem()
        if item:
            host = item.text().split(":")[0]
            if host in self.site_permissions:
                del self.site_permissions[host]
                self._save_site_permissions()
                list_widget.takeItem(list_widget.currentRow())
                self.status_bar.showMessage(f"Cleared permissions for {host}", 2000)
    
    
    def _show_extensions(self):
        """Show extensions manager dialog."""
        dialog = ExtensionsDialog(extension_manager, self)
        dialog.exec()
    
    
    def _show_shortcuts_help(self):
        """Show keyboard shortcuts help dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Keyboard Shortcuts")
        dialog.setMinimumSize(500, 600)
        
        layout = QVBoxLayout(dialog)
        
        shortcuts_text = """
<h2>Keyboard Shortcuts</h2>

<h3>Navigation</h3>
<table>
<tr><td><b>Alt+Left</b></td><td>Go back</td></tr>
<tr><td><b>Alt+Right</b></td><td>Go forward</td></tr>
<tr><td><b>F5 / Ctrl+R</b></td><td>Refresh page</td></tr>
<tr><td><b>Alt+Home</b></td><td>Go to homepage</td></tr>
<tr><td><b>Ctrl+L</b></td><td>Focus address bar</td></tr>
</table>

<h3>Tabs</h3>
<table>
<tr><td><b>Ctrl+T</b></td><td>New tab</td></tr>
<tr><td><b>Ctrl+W</b></td><td>Close tab</td></tr>
<tr><td><b>Ctrl+Shift+T</b></td><td>Reopen closed tab</td></tr>
<tr><td><b>Ctrl+Tab</b></td><td>Next tab</td></tr>
<tr><td><b>Ctrl+Shift+Tab</b></td><td>Previous tab</td></tr>
<tr><td><b>Ctrl+M</b></td><td>Mute/Unmute tab</td></tr>
<tr><td><b>Ctrl+Shift+P</b></td><td>Pin/Unpin tab</td></tr>
</table>

<h3>Features</h3>
<table>
<tr><td><b>Ctrl+F</b></td><td>Find in page</td></tr>
<tr><td><b>Ctrl+H</b></td><td>History</td></tr>
<tr><td><b>Ctrl+D</b></td><td>Bookmark page</td></tr>
<tr><td><b>Ctrl+J</b></td><td>Downloads</td></tr>
<tr><td><b>Ctrl+P</b></td><td>Print page</td></tr>
<tr><td><b>Ctrl+U</b></td><td>View page source</td></tr>
</table>

<h3>View</h3>
<table>
<tr><td><b>Ctrl++</b></td><td>Zoom in</td></tr>
<tr><td><b>Ctrl+-</b></td><td>Zoom out</td></tr>
<tr><td><b>Ctrl+0</b></td><td>Reset zoom</td></tr>
<tr><td><b>F11</b></td><td>Fullscreen</td></tr>
</table>

<h3>Tools</h3>
<table>
<tr><td><b>Ctrl+Shift+S</b></td><td>Screenshot page</td></tr>
<tr><td><b>Ctrl+Shift+N</b></td><td>New private tab</td></tr>
<tr><td><b>Shift+Esc</b></td><td>Task Manager</td></tr>
<tr><td><b>F1</b></td><td>This help</td></tr>
<tr><td><b>Escape</b></td><td>Close find bar / Exit fullscreen</td></tr>
</table>
"""
        
        text_edit = QTextEdit()
        text_edit.setHtml(shortcuts_text)
        text_edit.setReadOnly(True)
        layout.addWidget(text_edit)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        dialog.exec()
    
    
    
    def _open_devtools(self):
        """Open developer tools for current page."""
        web_view = self.tabs.currentWidget()
        if isinstance(web_view, LazyWebView) and web_view._page:
            if not hasattr(web_view, '_devtools_page') or web_view._devtools_page is None:
                devtools_view = QWebEngineView()
                devtools_page = QWebEnginePage(self.profile, devtools_view)
                devtools_view.setPage(devtools_page)
                web_view._devtools_view = devtools_view
                web_view._devtools_page = devtools_page
                web_view.page().setDevToolsPage(devtools_page)
            
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Developer Tools - {web_view.title()}")
            dialog.setMinimumSize(900, 600)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(web_view._devtools_view)
            
            dialog.show()
        else:
            self.status_bar.showMessage("No page loaded for DevTools", 2000)
    
    
    def _take_screenshot(self):
        """Take screenshot of current page."""
        web_view = self.tabs.currentWidget()
        if isinstance(web_view, LazyWebView):
            pixmap = web_view.grab()
            
            default_name = f"screenshot_{web_view.title()[:20]}.png".replace(" ", "_")
            default_name = "".join(c for c in default_name if c.isalnum() or c in "._-")
            
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Screenshot", default_name,
                "PNG Images (*.png);;JPEG Images (*.jpg);;All Files (*)"
            )
            
            if path:
                if pixmap.save(path):
                    self.status_bar.showMessage(f"Screenshot saved: {path}", 3000)
                    reply = QMessageBox.question(
                        self, "Screenshot Saved",
                        "Screenshot saved successfully. Open file location?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))
                else:
                    self.status_bar.showMessage("Failed to save screenshot", 3000)
    
    
    def _load_home_page_setting(self):
        """Load home page from settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        saved_home = settings.value("home_page", "https://www.google.com")
        self.HOME_PAGE = saved_home
    
    def _save_home_page_setting(self, url):
        """Save home page to settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        settings.setValue("home_page", url)
        self.HOME_PAGE = url
    
    def _show_home_settings(self):
        """Show home page settings dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Home Page Settings")
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout(dialog)
        
        info_label = QLabel(f"Current home page: {self.HOME_PAGE}")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        input_layout = QHBoxLayout()
        url_input = QLineEdit()
        url_input.setText(self.HOME_PAGE)
        url_input.setPlaceholderText("Enter home page URL...")
        input_layout.addWidget(url_input)
        layout.addLayout(input_layout)
        
        preset_group = QGroupBox("Quick Presets")
        preset_layout = QVBoxLayout(preset_group)
        
        presets = [
            ("Google", "https://www.google.com"),
            ("Bing", "https://www.bing.com"),
            ("DuckDuckGo", "https://duckduckgo.com"),
            ("Yahoo", "https://www.yahoo.com"),
            ("Blank Page", "about:blank"),
            ("Use Current Page", None),
        ]
        
        for name, url in presets:
            btn = QPushButton(name)
            if url is None:
                web_view = self.tabs.currentWidget()
                if isinstance(web_view, LazyWebView) and web_view.url():
                    current_url = web_view.url().toString()
                    btn.clicked.connect(lambda checked, u=current_url: url_input.setText(u))
                else:
                    btn.setEnabled(False)
            else:
                btn.clicked.connect(lambda checked, u=url: url_input.setText(u))
            preset_layout.addWidget(btn)
        
        layout.addWidget(preset_group)
        
        btn_layout = QHBoxLayout()
        
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(lambda: (
            self._save_home_page_setting(url_input.text().strip()),
            self.status_bar.showMessage(f"Home page set to: {url_input.text().strip()}", 3000),
            dialog.accept()
        ))
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        dialog.exec()
    
    
    def _view_page_source(self):
        """View page source code."""
        web_view = self.tabs.currentWidget()
        if isinstance(web_view, LazyWebView) and web_view._page:
            web_view.page().toHtml(self._show_source_dialog)
    
    def _show_source_dialog(self, html):
        """Show source code in a dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Page Source")
        dialog.setMinimumSize(800, 600)
        
        layout = QVBoxLayout(dialog)
        
        from PyQt6.QtWidgets import QPlainTextEdit
        source_view = QPlainTextEdit()
        source_view.setPlainText(html)
        source_view.setReadOnly(True)
        source_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = source_view.font()
        font.setFamily("Consolas, Monaco, monospace")
        font.setPointSize(10)
        source_view.setFont(font)
        layout.addWidget(source_view)
        
        btn_layout = QHBoxLayout()
        
        copy_btn = QPushButton("Copy All")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(html))
        btn_layout.addWidget(copy_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        dialog.exec()
    
    def _toggle_mute_current_tab(self):
        """Mute/unmute current tab."""
        index = self.tabs.currentIndex()
        self._toggle_mute_tab(index)
    
    def _toggle_mute_tab(self, index):
        """Mute/unmute a specific tab."""
        web_view = self.tabs.widget(index)
        if isinstance(web_view, LazyWebView) and web_view._page:
            is_muted = web_view.page().isAudioMuted()
            web_view.page().setAudioMuted(not is_muted)
            
            if not is_muted:
                self.muted_tabs.add(index)
            else:
                self.muted_tabs.discard(index)
            
            self._update_tab_mute_icon(index)
            self.status_bar.showMessage(
                "Tab muted" if not is_muted else "Tab unmuted", 2000
            )
    
    def _update_tab_mute_icon(self, index):
        """Update tab text to show mute indicator."""
        web_view = self.tabs.widget(index)
        if isinstance(web_view, LazyWebView):
            title = web_view.title() or "New Tab"
            is_pinned = index in self.pinned_tabs
            is_muted = index in self.muted_tabs
            
            prefix = ""
            if is_pinned:
                prefix += "📌 "
            if is_muted:
                prefix += "🔇 "
            
            display_title = title[:20] + "..." if len(title) > 20 else title
            self.tabs.setTabText(index, prefix + display_title)
    
    def _toggle_pin_current_tab(self):
        """Pin/unpin current tab."""
        index = self.tabs.currentIndex()
        self._toggle_pin_tab(index)
    
    def _toggle_pin_tab(self, index):
        """Pin/unpin a specific tab."""
        if index in self.pinned_tabs:
            self.pinned_tabs.discard(index)
            self.status_bar.showMessage("Tab unpinned", 2000)
        else:
            self.pinned_tabs.add(index)
            if index > 0:
                target = 0
                for i in sorted(self.pinned_tabs):
                    if i < index:
                        target = i + 1
                if target < index:
                    self.tabs.tabBar().moveTab(index, target)
                    self.pinned_tabs.discard(index)
                    self.pinned_tabs.add(target)
                    index = target
            self.status_bar.showMessage("Tab pinned", 2000)
        
        self._update_tab_mute_icon(index)
    
    def _reopen_closed_tab(self):
        """Reopen the last closed tab."""
        if self.closed_tabs:
            tab_info = self.closed_tabs.pop(0)
            self.new_tab(tab_info["url"])
            self._update_recently_closed_menu()
            self.status_bar.showMessage(f"Reopened: {tab_info['title']}", 2000)
        else:
            self.status_bar.showMessage("No recently closed tabs", 2000)
    
    def _update_recently_closed_menu(self):
        """Update the recently closed tabs submenu."""
        if not hasattr(self, 'recently_closed_menu'):
            return
            
        self.recently_closed_menu.clear()
        
        if not self.closed_tabs:
            action = QAction("No recently closed tabs", self)
            action.setEnabled(False)
            self.recently_closed_menu.addAction(action)
            return
        
        for i, tab_info in enumerate(self.closed_tabs[:10]):
            title = tab_info.get("title", "Untitled")[:40]
            action = QAction(title, self)
            action.triggered.connect(lambda checked, idx=i: self._reopen_specific_tab(idx))
            self.recently_closed_menu.addAction(action)
        
        if len(self.closed_tabs) > 0:
            self.recently_closed_menu.addSeparator()
            clear_action = QAction("Clear Recently Closed", self)
            clear_action.triggered.connect(self._clear_recently_closed)
            self.recently_closed_menu.addAction(clear_action)
    
    def _reopen_specific_tab(self, index):
        """Reopen a specific closed tab."""
        if 0 <= index < len(self.closed_tabs):
            tab_info = self.closed_tabs.pop(index)
            self.new_tab(tab_info["url"])
            self._update_recently_closed_menu()
    
    def _clear_recently_closed(self):
        """Clear all recently closed tabs."""
        self.closed_tabs.clear()
        self._update_recently_closed_menu()
        self.status_bar.showMessage("Recently closed tabs cleared", 2000)
    
    def _toggle_split_view(self):
        """Toggle split view mode."""
        if not self.split_mode:
            self._enable_split_view()
        else:
            self._disable_split_view()
    
    def _enable_split_view(self):
        """Enable split view with a second web view."""
        self.split_mode = True
        self.split_btn.setChecked(True)
        
        central_widget = self.centralWidget()
        self.central_layout = central_widget.layout()
        
        tabs_index = self.central_layout.indexOf(self.tabs)
        
        from PyQt6.QtWidgets import QSplitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.central_layout.removeWidget(self.tabs)
        
        self.splitter.addWidget(self.tabs)
        
        self.split_view = LazyWebView(self.profile, self.HOME_PAGE)
        self.split_view.title_changed.connect(self._update_split_title)
        self.split_view.load_started.connect(self._on_load_started)
        self.split_view.load_finished.connect(self._on_load_finished)
        self.split_view.activate()
        
        self.split_frame = QFrame()
        self.split_frame.setObjectName("splitFrame")
        split_layout = QVBoxLayout(self.split_frame)
        split_layout.setContentsMargins(0, 0, 0, 0)
        
        self.split_address = QLineEdit()
        self.split_address.setObjectName("splitAddressBar")
        self.split_address.setPlaceholderText("Enter URL for split view...")
        self.split_address.returnPressed.connect(self._navigate_split_view)
        split_layout.addWidget(self.split_address)
        split_layout.addWidget(self.split_view, 1)
        
        self.splitter.addWidget(self.split_frame)
        self.splitter.setSizes([600, 600])
        
        self.central_layout.insertWidget(2, self.splitter, 1)
        
        self.status_bar.showMessage("Split view enabled", 2000)
    
    def _disable_split_view(self):
        """Disable split view."""
        if not self.split_mode:
            return
            
        self.split_mode = False
        self.split_btn.setChecked(False)
        
        if hasattr(self, 'splitter') and self.splitter:
            self.tabs.setParent(None)
            
            self.central_layout.removeWidget(self.splitter)
            
            if self.split_view:
                self.split_view.deleteLater()
                self.split_view = None
            
            if hasattr(self, 'split_frame') and self.split_frame:
                self.split_frame.deleteLater()
                self.split_frame = None
            
            self.splitter.deleteLater()
            self.splitter = None
            
            self.central_layout.insertWidget(2, self.tabs, 1)
        
        self.status_bar.showMessage("Split view disabled", 2000)
        
        self.status_bar.showMessage("Split view disabled", 2000)
    
    def _navigate_split_view(self):
        """Navigate the split view to entered URL."""
        if self.split_view and hasattr(self, 'split_address'):
            url = self.split_address.text().strip()
            if url:
                self.split_view.navigate(url)
    
    def _update_split_title(self, title):
        """Update split view title display."""
        if hasattr(self, 'split_address') and self.split_view:
            url = self.split_view.url().toString()
            self.split_address.setText(url)
            self.split_address.setCursorPosition(0)
    
    
    def _setup_search_engine_menu(self):
        """Setup search engine selection menu."""
        menu = QMenu(self)
        
        for engine_name in SEARCH_ENGINES.keys():
            action = QAction(engine_name, self)
            action.setCheckable(True)
            action.setChecked(engine_name == self.search_engine)
            action.triggered.connect(lambda checked, name=engine_name: self._set_search_engine(name))
            menu.addAction(action)
        
        self.search_engine_btn.setMenu(menu)
    
    def _set_search_engine(self, name):
        """Set the active search engine."""
        self.search_engine = name
        self._save_search_engine_setting()
        self._setup_search_engine_menu()
        self.status_bar.showMessage(f"Search engine: {name}", 2000)
    
    def _load_search_engine_setting(self):
        """Load search engine from settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        self.search_engine = settings.value("search_engine", "Google")
    
    def _save_search_engine_setting(self):
        """Save search engine to settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        settings.setValue("search_engine", self.search_engine)
    
    
    def _try_calculate(self, expression):
        """Try to evaluate a math expression. Returns result or None."""
        expr = expression.strip()
        
        if not re.search(r'[\d]', expr):
            return None
        if not re.search(r'[\+\-\*\/\^\(\)\%]', expr):
            return None
        
        expr = expr.replace('^', '**')
        expr = expr.replace('×', '*')
        expr = expr.replace('÷', '/')
        expr = expr.replace('x', '*')
        
        allowed = set('0123456789+-*/.()% ')
        if not all(c in allowed for c in expr):
            return None
        
        try:
            result = eval(expr, {"__builtins__": {}}, {})
            if isinstance(result, (int, float)):
                if isinstance(result, float) and result.is_integer():
                    return int(result)
                elif isinstance(result, float):
                    return round(result, 10)
                return result
        except:
            pass
        return None
    
    def _on_address_bar_text_changed(self, text):
        """Handle address bar text changes for live calculator."""
        result = self._try_calculate(text)
        if result is not None:
            self.calc_result_label.setText(f"= {result}")
            self.calc_result_label.show()
        else:
            self.calc_result_label.hide()
    
    
    def _setup_clipboard_monitor(self):
        """Setup clipboard monitoring."""
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self._on_clipboard_changed)
        self._last_clipboard_text = ""
    
    def _on_clipboard_changed(self):
        """Handle clipboard content changes."""
        text = self.clipboard.text()
        if text and text != self._last_clipboard_text:
            self._last_clipboard_text = text
            if text not in self.clipboard_history:
                self.clipboard_history.insert(0, text[:500])
                self.clipboard_history = self.clipboard_history[:50]
                self._update_clipboard_list()
    
    def _setup_side_panels(self):
        """Setup side panels (clipboard, notepad)."""
        self.clipboard_dock = QDockWidget("📋 Clipboard History", self)
        self.clipboard_dock.setObjectName("clipboardDock")
        self.clipboard_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        
        clipboard_widget = QWidget()
        clipboard_layout = QVBoxLayout(clipboard_widget)
        clipboard_layout.setContentsMargins(5, 5, 5, 5)
        
        self.clipboard_list = QListWidget()
        self.clipboard_list.setObjectName("clipboardList")
        self.clipboard_list.itemDoubleClicked.connect(self._copy_from_clipboard_history)
        clipboard_layout.addWidget(self.clipboard_list)
        
        clip_btn_layout = QHBoxLayout()
        copy_btn = QPushButton("Copy Selected")
        copy_btn.clicked.connect(lambda: self._copy_from_clipboard_history(self.clipboard_list.currentItem()))
        clip_btn_layout.addWidget(copy_btn)
        
        clear_clip_btn = QPushButton("Clear")
        clear_clip_btn.clicked.connect(self._clear_clipboard_history)
        clip_btn_layout.addWidget(clear_clip_btn)
        clipboard_layout.addLayout(clip_btn_layout)
        
        self.clipboard_dock.setWidget(clipboard_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.clipboard_dock)
        self.clipboard_dock.hide()
        
        self.notepad_dock = QDockWidget("📝 Quick Notes", self)
        self.notepad_dock.setObjectName("notepadDock")
        self.notepad_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        
        notepad_widget = QWidget()
        notepad_layout = QVBoxLayout(notepad_widget)
        notepad_layout.setContentsMargins(5, 5, 5, 5)
        
        self.notepad_edit = QPlainTextEdit()
        self.notepad_edit.setObjectName("notepadEdit")
        self.notepad_edit.setPlaceholderText("Write your notes here...")
        self._load_notepad_content()
        self.notepad_edit.textChanged.connect(self._save_notepad_content)
        notepad_layout.addWidget(self.notepad_edit)
        
        note_btn_layout = QHBoxLayout()
        clear_note_btn = QPushButton("Clear")
        clear_note_btn.clicked.connect(lambda: self.notepad_edit.clear())
        note_btn_layout.addWidget(clear_note_btn)
        
        copy_note_btn = QPushButton("Copy All")
        copy_note_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.notepad_edit.toPlainText()))
        note_btn_layout.addWidget(copy_note_btn)
        notepad_layout.addLayout(note_btn_layout)
        
        self.notepad_dock.setWidget(notepad_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.notepad_dock)
        self.notepad_dock.hide()
        
        self.calc_result_label = QLabel()
        self.calc_result_label.setObjectName("calcResult")
        self.calc_result_label.setStyleSheet("""
            QLabel {
                background: #2d5a2d;
                color: #90EE90;
                padding: 5px 10px;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        self.calc_result_label.hide()
        self.status_bar.addWidget(self.calc_result_label)
        
        self.address_bar.textChanged.connect(self._on_address_bar_text_changed)
    
    def _update_clipboard_list(self):
        """Update the clipboard list widget."""
        if hasattr(self, 'clipboard_list'):
            self.clipboard_list.clear()
            for text in self.clipboard_history:
                display = text[:100] + "..." if len(text) > 100 else text
                display = display.replace('\n', ' ')
                self.clipboard_list.addItem(display)
    
    def _copy_from_clipboard_history(self, item):
        """Copy selected item from clipboard history."""
        if item:
            row = self.clipboard_list.row(item)
            if 0 <= row < len(self.clipboard_history):
                self._last_clipboard_text = self.clipboard_history[row]
                QApplication.clipboard().setText(self.clipboard_history[row])
                self.status_bar.showMessage("Copied to clipboard", 2000)
    
    def _clear_clipboard_history(self):
        """Clear clipboard history."""
        self.clipboard_history.clear()
        self._update_clipboard_list()
    
    def _toggle_clipboard_panel(self):
        """Toggle clipboard panel visibility."""
        if self.clipboard_dock.isVisible():
            self.clipboard_dock.hide()
            self.clipboard_btn.setChecked(False)
        else:
            self.clipboard_dock.show()
            self.clipboard_btn.setChecked(True)
            self._update_clipboard_list()
    
    def _toggle_notepad(self):
        """Toggle notepad panel visibility."""
        if self.notepad_dock.isVisible():
            self.notepad_dock.hide()
        else:
            self.notepad_dock.show()
    
    def _load_notepad_content(self):
        """Load notepad content from settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        content = settings.value("notepad_content", "")
        if hasattr(self, 'notepad_edit'):
            self.notepad_edit.setPlainText(content)
    
    def _save_notepad_content(self):
        """Save notepad content to settings."""
        settings = QSettings("SwiftBrowser", "Swift Browser")
        settings.setValue("notepad_content", self.notepad_edit.toPlainText())
    
    
    def _toggle_privacy_blur(self):
        """Toggle privacy blur on current tab."""
        web_view = self.tabs.currentWidget()
        if not isinstance(web_view, LazyWebView):
            return
        
        index = self.tabs.currentIndex()
        
        if index in self.blur_effects:
            effect = self.blur_effects[index]
            self._animate_blur(effect, effect.blurRadius(), 0, remove_after=True)
            del self.blur_effects[index]
            self.privacy_blur_active = False
            self.blur_btn.setChecked(False)
            self.status_bar.showMessage("Privacy blur disabled", 100000)
        else:
            effect = QGraphicsBlurEffect(web_view)
            effect.setBlurRadius(0)
            web_view.setGraphicsEffect(effect)
            self.blur_effects[index] = effect
            self._animate_blur(effect, 0, 25)
            self.privacy_blur_active = True
            self.blur_btn.setChecked(True)
            self.status_bar.showMessage("Privacy blur enabled (Ctrl+B to toggle)", 100000)
    
    def _animate_blur(self, effect, start, end, remove_after=False):
        """Animate blur radius change."""
        steps = 10
        step_value = (end - start) / steps
        current_step = [0]
        
        def step():
            current_step[0] += 1
            new_radius = start + (step_value * current_step[0])
            effect.setBlurRadius(new_radius)
            
            if current_step[0] >= steps:
                timer.stop()
                if remove_after:
                    effect.setEnabled(False)
        
        timer = QTimer(self)
        timer.timeout.connect(step)
        timer.start(30)
    
    
    def _setup_enhanced_privacy(self):
        """Configure enhanced privacy settings."""
        pass
    


def main():
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--enable-gpu-rasterization "
        "--enable-native-gpu-memory-buffers "
        "--enable-accelerated-video-decode "
        "--enable-features=VaapiVideoDecoder "
        "--disable-background-networking "
        "--disable-client-side-phishing-detection "
        "--disable-default-apps "
        "--disable-extensions "
        "--disable-sync "
        "--disable-translate "
        "--metrics-recording-only "
        "--no-first-run "
        "--safebrowsing-disable-auto-update"
    )
    
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("Swift Browser")
    app.setOrganizationName("SwiftBrowser")
    
    icon_path = Path(__file__).parent / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    browser = Browser()
    browser.showMaximized()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
