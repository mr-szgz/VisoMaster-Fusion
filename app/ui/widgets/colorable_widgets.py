from __future__ import annotations

import enum
from typing import TYPE_CHECKING
from PySide6 import QtWidgets, QtGui

if TYPE_CHECKING:
    from app.ui.main_ui import MainWindow


class ColorableDataRole(enum.IntEnum):
    ButtonColorRole = 0x190


class ColorableCard:
    """Mixin that adds button-color styling to a QPushButton subclass."""

    def setButtonColor(self, color_name: str | None) -> None:
        self.setProperty("buttonColor", color_name)
        self.style().unpolish(self)
        self.style().polish(self)

    def buttonColor(self) -> str | None:
        return self.property("buttonColor")


class ColorableListWidget(QtWidgets.QListWidget):
    """QListWidget that applies an item's button color to its item widget."""

    def setItemWidget(
        self,
        item: "ColorableListWidgetItem",
        widget: ColorableCard,
    ) -> None:
        super().setItemWidget(item, widget)
        widget.setButtonColor(item.buttonColor())


class InputEmbeddingsList(ColorableListWidget):
    """Promoted class for MainWindow.ui's inputEmbeddingsList."""


class ColorableListWidgetItem(QtWidgets.QListWidgetItem):
    def buttonColor(self) -> str | None:
        return self.data(ColorableDataRole.ButtonColorRole)

    def setButtonColor(self, color_name: str | None) -> None:
        self.setData(ColorableDataRole.ButtonColorRole, color_name)

        if list_widget := self.listWidget():
            button = list_widget.itemWidget(self)
            button.setButtonColor(color_name)


class ColorLabelDialog(QtWidgets.QDialog):
    def __init__(self, main_window: "MainWindow"):
        super().__init__(main_window)
        self.setWindowTitle("Color Label Embeddings")
        self.setWindowIcon(QtGui.QIcon(":/media/media/visomaster_small.png"))

        self.color_combobox = QtWidgets.QComboBox(self)
        for label, color_name in [
            ("None", None),
            ("red", "red"),
            ("orange", "orange"),
            ("amber", "amber"),
            ("yellow", "yellow"),
            ("lime", "lime"),
            ("green", "green"),
            ("teal", "teal"),
            ("cyan", "cyan"),
            ("blue", "blue"),
            ("indigo", "indigo"),
            ("purple", "purple"),
            ("pink", "pink"),
            ("brown", "brown"),
            ("brunette", "brunette"),
            ("blonde", "blonde"),
            ("dark blonde", "dark_blonde"),
            ("black hair", "black_hair"),
            ("silver", "silver"),
            ("platinum", "platinum"),
            ("grey", "grey"),
        ]:
            self.color_combobox.addItem(label, color_name)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.color_combobox)
        layout.addWidget(button_box)

    def selectedColor(self) -> str | None:
        return self.color_combobox.currentData()
