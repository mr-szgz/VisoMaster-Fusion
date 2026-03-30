from PySide6.QtCore import QCoreApplication, QSize, Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QDockWidget, QLineEdit, QListWidget, QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget


# Step: UI builder class for main window sections | Pattern: app/ui/core/main_window.py:24-25
class Ui_MainWindow(object):
    # Step: Build Import panel widgets in setup phase | Pattern: app/ui/core/main_window.py:25-448
    def setup_import_media_panel(self, MainWindow):
        # Step: Create top-bar panel visibility checkbox | Pattern: app/ui/core/main_window.py:84-87
        self.ImportMediaCheckBox = QCheckBox(self.mediaLayout)
        # Step: Stable Qt object name for signal/lookup | Pattern: app/ui/core/main_window.py:85
        self.ImportMediaCheckBox.setObjectName("ImportMediaCheckBox")
        # Step: Default panel enabled | Pattern: app/ui/core/main_window.py:86
        self.ImportMediaCheckBox.setChecked(True)
        # Step: Place checkbox in panel visibility row | Pattern: app/ui/core/main_window.py:87
        self.panelVisibilityCheckBoxLayout.addWidget(self.ImportMediaCheckBox)

        # Step: Create dock container for panel | Pattern: app/ui/core/main_window.py:376-377
        self.import_Media_DockWidget = QDockWidget(MainWindow)
        # Step: Stable dock object name | Pattern: app/ui/core/main_window.py:377
        self.import_Media_DockWidget.setObjectName("import_Media_DockWidget")
        # Step: Match existing media dock min size | Pattern: app/ui/core/main_window.py:383
        self.import_Media_DockWidget.setMinimumSize(QSize(324, 230))
        # Step: Match existing dock movability/floatability | Pattern: app/ui/core/main_window.py:384
        self.import_Media_DockWidget.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )

        # Step: Create dock content root | Pattern: app/ui/core/main_window.py:385-390
        self.dockWidgetContents_ImportMedia = QWidget()
        # Step: Vertical root layout for panel | Pattern: app/ui/core/main_window.py:389-390
        self.vboxLayout_ImportMedia = QVBoxLayout(self.dockWidgetContents_ImportMedia)

        # Step: Create top-level Browser/Settings tabs | Pattern: app/ui/core/main_window.py:1152-1200
        self.importMediaPanelTabWidget = QTabWidget(self.dockWidgetContents_ImportMedia)
        # Step: Create nested media-type tabs for browser | Pattern: app/ui/core/main_window.py:1152-1200
        self.importMediaBrowserTypeTabs = QTabWidget()

        # Step: Video browser search input | Pattern: app/ui/core/main_window.py:416-418
        self.importVideosSearchBox = QLineEdit()
        # Step: Video browser action button | Pattern: app/ui/core/main_window.py:401-411
        self.buttonImportVideosSearch = QPushButton()
        # Step: Video browser results list | Pattern: app/ui/core/main_window.py:441-445
        self.importVideosList = QListWidget()

        # Step: Image browser search input | Pattern: app/ui/core/main_window.py:416-418
        self.importImagesSearchBox = QLineEdit()
        # Step: Image browser action button | Pattern: app/ui/core/main_window.py:401-411
        self.buttonImportImagesSearch = QPushButton()
        # Step: Image browser results list | Pattern: app/ui/core/main_window.py:441-445
        self.importImagesList = QListWidget()

        # Step: Refresh saved video searches/items | Pattern: app/ui/core/main_window.py:401-411
        self.buttonImportSavedVideosRefresh = QPushButton()
        # Step: Saved video results list | Pattern: app/ui/core/main_window.py:441-445
        self.importSavedVideosList = QListWidget()

        # Step: Refresh saved image searches/items | Pattern: app/ui/core/main_window.py:401-411
        self.buttonImportSavedImagesRefresh = QPushButton()
        # Step: Saved image results list | Pattern: app/ui/core/main_window.py:441-445
        self.importSavedImagesList = QListWidget()

        # Step: Provider selector control | Pattern: app/ui/core/main_window.py:1250-1268 (generated from settings tab)
        self.remoteImportProviderComboBox = QComboBox()
        # Step: Endpoint/location text input | Pattern: app/ui/core/main_window.py:1254-1258 (generated from settings tab)
        self.remoteImportEndpointLineEdit = QLineEdit()
        # Step: Video query/settings editor | Pattern: app/ui/core/main_window.py:1250-1268 (generated from settings tab)
        self.remoteImportVideoQueryPlainText = QPlainTextEdit()
        # Step: Image query/settings editor | Pattern: app/ui/core/main_window.py:1250-1268 (generated from settings tab)
        self.remoteImportImageQueryPlainText = QPlainTextEdit()
        # Step: Saved-search query/settings editor | Pattern: app/ui/core/main_window.py:1250-1268 (generated from settings tab)
        self.remoteImportSavedSearchesQueryPlainText = QPlainTextEdit()
        # Step: Apply settings action | Pattern: app/ui/core/main_window.py:1261-1264 (generated from settings tab)
        self.buttonRemoteImportApplySettings = QPushButton()

        # Step: Mount tab widget into panel root layout | Pattern: app/ui/core/main_window.py:446-447
        self.vboxLayout_ImportMedia.addWidget(self.importMediaPanelTabWidget)
        # Step: Bind content widget to dock container | Pattern: app/ui/core/main_window.py:447
        self.import_Media_DockWidget.setWidget(self.dockWidgetContents_ImportMedia)
        # Step: Add dock to left side area | Pattern: app/ui/core/main_window.py:448
        MainWindow.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.import_Media_DockWidget)

    # Step: Apply translated UI strings | Pattern: app/ui/core/main_window.py:700-819
    def retranslate_import_media_panel(self):
        # Step: Translate panel toggle text | Pattern: app/ui/core/main_window.py:714
        self.ImportMediaCheckBox.setText(
            QCoreApplication.translate("MainWindow", "Import Videos/Images", None)
        )
        # Step: Translate dock title text | Pattern: app/ui/core/main_window.py:791
        self.import_Media_DockWidget.setWindowTitle(
            QCoreApplication.translate("MainWindow", "Import Videos/Images", None)
        )
