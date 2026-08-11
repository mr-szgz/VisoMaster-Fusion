from __future__ import annotations

import enum
import re
from typing import TYPE_CHECKING
from PySide6 import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from app.ui.main_ui import MainWindow


COLOR_LABELS = (
    ("red", "red"),
    ("orange", "orange"),
    ("oxblood", "oxblood"),
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
    ("dark oak", "dark_oak"),
    ("black hair", "black_hair"),
    ("silver", "silver"),
    ("platinum blonde", "platinum_blonde"),
    ("grey", "grey"),
)
COLOR_NAMES = {color_name: label for label, color_name in COLOR_LABELS}


def natural_sort_key(text: str) -> list[str | int]:
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", text)
    ]


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


class ColorButton(ColorableCard, QtWidgets.QPushButton):
    """Checkable color control styled by its buttonColor property."""

    def __init__(
        self,
        color_name: str | None,
        show_text: bool = True,
        text: str | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._color_name = color_name
        self._display_text = text or color_name
        self._show_text = show_text
        self.setButtonColor(color_name)
        self.setCheckable(True)
        self.setChecked(True)
        self.setTextVisible(show_text)
        self.setToolTip(self._display_text)
        self.setAccessibleName(f"Show {self._display_text} embeddings")

    def colorName(self) -> str | None:
        return self._color_name

    def isTextVisible(self) -> bool:
        return self._show_text

    def setTextVisible(self, visible: bool) -> None:
        self._show_text = visible
        self.setText(self._display_text if visible else "")


class ColorableListWidget(QtWidgets.QListWidget):
    """QListWidget that applies an item's button color to its item widget."""

    colorFiltersChanged = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._color_filter_layout: QtWidgets.QBoxLayout | None = None
        self._color_filter_anchor: QtWidgets.QWidget | None = None
        self._color_filter_search_box: QtWidgets.QLineEdit | None = None
        self._color_filter_show_text = True
        self._color_filter_buttons: dict[str | None, ColorButton] = {}
        self._select_all_color_filters_button: QtWidgets.QPushButton | None = None
        self._reset_color_filters_button: QtWidgets.QPushButton | None = None

    def setColorFilterLayout(
        self,
        layout: QtWidgets.QBoxLayout,
        before_widget: QtWidgets.QWidget,
        search_box: QtWidgets.QLineEdit,
        show_text: bool = True,
    ) -> None:
        self._color_filter_layout = layout
        self._color_filter_anchor = before_widget
        self._color_filter_search_box = search_box
        self._color_filter_show_text = show_text

        button_parent = before_widget.parentWidget()
        self._select_all_color_filters_button = QtWidgets.QPushButton(
            "All", button_parent
        )
        self._select_all_color_filters_button.setAccessibleName(
            "Select all embedding color filters"
        )
        self._select_all_color_filters_button.clicked.connect(
            self.selectAllColorFilters
        )
        self._reset_color_filters_button = QtWidgets.QPushButton(
            "Reset", button_parent
        )
        self._reset_color_filters_button.setAccessibleName(
            "Deselect all embedding color filters"
        )
        self._reset_color_filters_button.clicked.connect(self.resetColorFilters)
        QtWidgets.QApplication.instance().focusChanged.connect(
            self.updateColorFilterControlsForFocus
        )
        self.syncColorFilterButtons()

    def colorFilterButtons(self) -> dict[str | None, ColorButton]:
        return self._color_filter_buttons.copy()

    def isColorVisible(self, color_name: str | None) -> bool:
        color_button = self._color_filter_buttons.get(color_name)
        return color_button is None or color_button.isChecked()

    def selectAllColorFilters(self) -> None:
        signal_blockers = [
            QtCore.QSignalBlocker(button)
            for button in self._color_filter_buttons.values()
        ]
        signal_blockers.append(QtCore.QSignalBlocker(self._color_filter_search_box))
        for button in self._color_filter_buttons.values():
            button.setChecked(True)
        self._color_filter_search_box.clear()
        del signal_blockers
        self.colorFiltersChanged.emit()

    def resetColorFilters(self) -> None:
        signal_blockers = [
            QtCore.QSignalBlocker(button)
            for button in self._color_filter_buttons.values()
        ]
        for button in self._color_filter_buttons.values():
            button.setChecked(False)
        del signal_blockers
        self.colorFiltersChanged.emit()

    def updateColorFilterControlsForFocus(
        self,
        _previous_widget: QtWidgets.QWidget | None,
        focused_widget: QtWidgets.QWidget | None,
    ) -> None:
        controls_visible = focused_widget is not self._color_filter_search_box
        for button in self._color_filter_buttons.values():
            button.setVisible(controls_visible)
        self._select_all_color_filters_button.setVisible(controls_visible)
        self._reset_color_filters_button.setVisible(controls_visible)

    def syncColorFilterButtons(self) -> None:
        if self._color_filter_layout is None or self._color_filter_anchor is None:
            return

        used_color_names = []
        for index in range(self.count()):
            color_name = self.item(index).buttonColor()
            if color_name and color_name not in used_color_names:
                used_color_names.append(color_name)

        for color_name in list(self._color_filter_buttons):
            if color_name is not None and color_name not in used_color_names:
                color_button = self._color_filter_buttons.pop(color_name)
                self._color_filter_layout.removeWidget(color_button)
                color_button.deleteLater()

        if None not in self._color_filter_buttons:
            color_button = ColorButton(
                None,
                show_text=self._color_filter_show_text,
                text="None",
                parent=self._color_filter_anchor.parentWidget(),
            )
            color_button.toggled.connect(self.colorFiltersChanged)
            self._color_filter_buttons[None] = color_button

        sorted_color_names = sorted(
            used_color_names,
            key=lambda color_name: natural_sort_key(COLOR_NAMES[color_name]),
        )
        for color_name in sorted_color_names:
            if color_name not in self._color_filter_buttons:
                color_button = ColorButton(
                    color_name,
                    show_text=self._color_filter_show_text,
                    text=COLOR_NAMES[color_name],
                    parent=self._color_filter_anchor.parentWidget(),
                )
                color_button.toggled.connect(self.colorFiltersChanged)
                self._color_filter_buttons[color_name] = color_button

        for color_name in [None, *sorted_color_names]:
            color_button = self._color_filter_buttons[color_name]
            self._color_filter_layout.removeWidget(color_button)
            anchor_index = self._color_filter_layout.indexOf(
                self._color_filter_anchor
            )
            self._color_filter_layout.insertWidget(anchor_index, color_button)

        for action_button in (
            self._select_all_color_filters_button,
            self._reset_color_filters_button,
        ):
            self._color_filter_layout.removeWidget(action_button)
            anchor_index = self._color_filter_layout.indexOf(
                self._color_filter_anchor
            )
            self._color_filter_layout.insertWidget(anchor_index, action_button)

        self.updateColorFilterControlsForFocus(
            None,
            QtWidgets.QApplication.focusWidget(),
        )
        self.colorFiltersChanged.emit()

    def setItemWidget(
        self,
        item: "ColorableListWidgetItem",
        widget: ColorableCard,
    ) -> None:
        super().setItemWidget(item, widget)
        widget.setButtonColor(item.buttonColor())
        self.syncColorFilterButtons()

    def takeItem(self, row: int) -> QtWidgets.QListWidgetItem:
        item = super().takeItem(row)
        self.syncColorFilterButtons()
        return item

    def clear(self) -> None:
        super().clear()
        self.syncColorFilterButtons()


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
            list_widget.syncColorFilterButtons()


class ColorLabelDialog(QtWidgets.QDialog):
    def __init__(self, main_window: "MainWindow"):
        super().__init__(main_window)
        self.setWindowTitle("Color Label Embeddings")
        self.setWindowIcon(QtGui.QIcon(":/media/media/visomaster_small.png"))

        self.color_combobox = QtWidgets.QComboBox(self)
        self.color_combobox.addItem("None", None)
        for label, color_name in sorted(
            COLOR_LABELS,
            key=lambda color_label: natural_sort_key(color_label[0]),
        ):
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
