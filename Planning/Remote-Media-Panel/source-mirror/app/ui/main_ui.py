from functools import partial

from PySide6 import QtWidgets

from app.ui.widgets.actions import layout_actions


# Step: Main window UI behavior hooks | Pattern: app/ui/main_ui.py:67-75
class MainWindow:
    # Step: Wire Import panel widgets and list behavior | Pattern: app/ui/main_ui.py:175-214, 349-364
    def initialize_widgets_import_media_panel(self):
        # Step: Bind panel toggle checkbox to dock show/hide action | Pattern: app/ui/main_ui.py:356-358
        self.ImportMediaCheckBox.toggled.connect(
            partial(layout_actions.show_hide_import_media_panel, self)
        )

        # Step: Apply existing media list layout behavior to Import lists | Pattern: app/ui/main_ui.py:177-184
        for list_widget in [
            self.importVideosList,
            self.importImagesList,
            self.importSavedVideosList,
            self.importSavedImagesList,
        ]:
            # Step: Horizontal card/list flow | Pattern: app/ui/main_ui.py:177,182
            list_widget.setFlow(QtWidgets.QListWidget.LeftToRight)
            # Step: Wrap items into rows | Pattern: app/ui/main_ui.py:178,183
            list_widget.setWrapping(True)
            # Step: Auto-adjust layout as size changes | Pattern: app/ui/main_ui.py:179,184
            list_widget.setResizeMode(QtWidgets.QListWidget.Adjust)
