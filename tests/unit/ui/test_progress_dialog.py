from __future__ import annotations

import importlib
import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6 import QtWidgets, QtCore


def _stub(name: str) -> MagicMock:
    module = MagicMock()
    module.__name__ = name
    module.__spec__ = None
    return module


@pytest.fixture(scope="module")
def progress_dialog_module():
    stubbed_modules = {
        "send2trash": _stub("send2trash"),
        "app.helpers": _stub("app.helpers"),
        "app.ui.widgets.actions": _stub("app.ui.widgets.actions"),
        "app.ui.widgets.actions.common_actions": _stub(
            "app.ui.widgets.actions.common_actions"
        ),
        "app.ui.widgets.actions.video_control_actions": _stub(
            "app.ui.widgets.actions.video_control_actions"
        ),
        "app.ui.widgets.actions.graphics_view_actions": _stub(
            "app.ui.widgets.actions.graphics_view_actions"
        ),
        "app.ui.widgets.actions.card_actions": _stub(
            "app.ui.widgets.actions.card_actions"
        ),
        "app.ui.widgets.actions.save_load_actions": _stub(
            "app.ui.widgets.actions.save_load_actions"
        ),
        "app.helpers.miscellaneous": _stub("app.helpers.miscellaneous"),
    }
    stubbed_modules["send2trash"].send2trash = MagicMock()
    stubbed_modules["app.helpers.miscellaneous"].get_video_rotation = MagicMock(
        return_value=0
    )

    saved_modules = {
        name: sys.modules.get(name)
        for name in [*stubbed_modules, "app.ui.widgets.widget_components"]
    }
    saved_package_attrs: dict[tuple[str, str], tuple[bool, object | None]] = {}

    for module_name in [*stubbed_modules, "app.ui.widgets.widget_components"]:
        parent_name, _, attr_name = module_name.rpartition(".")
        if not parent_name:
            continue
        parent_module = sys.modules.get(parent_name)
        had_attr = parent_module is not None and hasattr(parent_module, attr_name)
        saved_package_attrs[(parent_name, attr_name)] = (
            had_attr,
            getattr(parent_module, attr_name) if had_attr else None,
        )

    try:
        for name, module in stubbed_modules.items():
            sys.modules[name] = module

        for module_name, module in stubbed_modules.items():
            parent_name, _, attr_name = module_name.rpartition(".")
            parent_module = sys.modules.get(parent_name)
            if parent_module is not None and attr_name:
                setattr(parent_module, attr_name, module)

        sys.modules.pop("app.ui.widgets.widget_components", None)
        module = importlib.import_module("app.ui.widgets.widget_components")
        yield module
    finally:
        for name, original_module in saved_modules.items():
            if original_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original_module

        for (parent_name, attr_name), (
            had_attr,
            original_value,
        ) in saved_package_attrs.items():
            parent_module = sys.modules.get(parent_name)
            if parent_module is None:
                continue
            if had_attr:
                setattr(parent_module, attr_name, original_value)
            elif hasattr(parent_module, attr_name):
                delattr(parent_module, attr_name)


@pytest.fixture
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


class _FakePromptBox:
    Warning = QtWidgets.QMessageBox.Warning
    Yes = QtWidgets.QMessageBox.Yes
    No = QtWidgets.QMessageBox.No
    next_result = Yes
    instances: list["_FakePromptBox"] = []

    def __init__(self, _parent=None):
        self.window_title = None
        self.text = None
        self.informative_text = None
        _FakePromptBox.instances.append(self)

    def setIcon(self, _icon):
        return None

    def setWindowTitle(self, value):
        self.window_title = value

    def setText(self, value):
        self.text = value

    def setInformativeText(self, value):
        self.informative_text = value

    def setStandardButtons(self, _buttons):
        return None

    def setDefaultButton(self, _button):
        return None

    def setWindowFlag(self, *_args):
        return None

    def exec(self):
        return _FakePromptBox.next_result


def _flush_qt_events(app):
    app.processEvents()
    QtCore.QCoreApplication.sendPostedEvents(None, 0)
    app.processEvents()


@pytest.mark.qt
def test_progress_dialog_stop_preserves_cancel_state(progress_dialog_module, qapp):
    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 2)
    dialog.show()
    _flush_qt_events(qapp)

    assert dialog.stop_button.geometry().right() < dialog.cancel_button.x()
    assert dialog.runtime_label.geometry().right() < dialog.stop_button.x()
    dialog.stop_button.click()

    assert dialog.stop_requested
    assert not dialog.confirmedCanceled()
    assert not dialog.stop_button.isEnabled()
    assert not dialog.cancel_button.isEnabled()
    dialog.close_without_confirmation()


@pytest.mark.qt
def test_batch_media_properties_update_without_job_data(progress_dialog_module, qapp):
    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 3)
    dialog.show()
    dialog.set_media_properties(["Alice", "Bob"], 90000, 25)
    _flush_qt_events(qapp)
    labels = dialog.media_report_labels
    assert labels["Embedding:"][1].text() == "Alice, Bob"
    assert labels["Frames:"][1].text() == "90,000"
    assert labels["Frame rate:"][1].text() == "25 fps"
    assert labels["Length:"][1].text() == "01:00:00"
    assert labels["Length:"][1].isVisible()
    title = dialog.findChild(QtWidgets.QLabel)
    bar = dialog.findChild(QtWidgets.QProgressBar)
    assert title.geometry().bottom() < bar.y()
    assert bar.geometry().bottom() < dialog.media_report.y()
    assert dialog.media_report.geometry().bottom() < dialog.remove_completed_checkbox.y()
    assert len(dialog.media_report.findChildren(QtWidgets.QFrame, options=QtCore.Qt.FindDirectChildrenOnly)) >= 2

    dialog.setLabelText("photo.png")
    dialog.set_media_properties([], 1, 0)
    assert labels["Embedding:"][1].text() == ""
    assert labels["Frames:"][1].text() == "1"
    assert not labels["Frame rate:"][1].isVisible()
    assert not labels["Length:"][1].isVisible()
    dialog.set_media_properties(["Carol"], 48, 24)
    assert labels["Length:"][1].isVisible()
    assert labels["Length:"][1].text() == "00:00:02"
    dialog.close_without_confirmation()


@pytest.mark.qt
def test_progress_dialog_close_without_confirmation_skips_prompt(
    monkeypatch, progress_dialog_module, qapp
):
    _FakePromptBox.instances = []
    monkeypatch.setattr(progress_dialog_module.QtWidgets, "QMessageBox", _FakePromptBox)

    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 1)
    dialog.show()
    _flush_qt_events(qapp)

    dialog.close_without_confirmation()
    _flush_qt_events(qapp)

    assert _FakePromptBox.instances == []
    assert dialog.confirmedCanceled() is False
    assert dialog.isVisible() is False


@pytest.mark.qt
def test_progress_dialog_queued_cancel_is_ignored_after_programmatic_close(
    monkeypatch, progress_dialog_module, qapp
):
    _FakePromptBox.instances = []
    monkeypatch.setattr(progress_dialog_module.QtWidgets, "QMessageBox", _FakePromptBox)

    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 1)
    dialog.show()
    _flush_qt_events(qapp)

    dialog.canceled.emit()
    dialog.close_without_confirmation()
    _flush_qt_events(qapp)

    assert _FakePromptBox.instances == []
    assert dialog.confirmedCanceled() is False
    assert dialog.isVisible() is False


@pytest.mark.qt
def test_progress_dialog_cancel_confirm_yes_marks_confirmed_cancel(
    monkeypatch, progress_dialog_module, qapp
):
    _FakePromptBox.instances = []
    _FakePromptBox.next_result = _FakePromptBox.Yes
    monkeypatch.setattr(progress_dialog_module.QtWidgets, "QMessageBox", _FakePromptBox)

    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 1)
    dialog.show()
    _flush_qt_events(qapp)

    dialog.findChild(QtWidgets.QPushButton).click()
    _flush_qt_events(qapp)

    assert len(_FakePromptBox.instances) == 1
    prompt = _FakePromptBox.instances[0]
    assert prompt.window_title == "Confirm stop"
    assert prompt.text == "Stop the current task?"
    assert (
        prompt.informative_text
        == "Processing will stop immediately.\nOutputs may be incomplete."
    )
    assert dialog.confirmedCanceled() is True


@pytest.mark.qt
def test_progress_dialog_cancel_confirm_no_restores_dialog(
    monkeypatch, progress_dialog_module, qapp
):
    _FakePromptBox.instances = []
    _FakePromptBox.next_result = _FakePromptBox.No
    monkeypatch.setattr(progress_dialog_module.QtWidgets, "QMessageBox", _FakePromptBox)

    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 3)
    dialog.setValue(1)
    dialog.show()
    _flush_qt_events(qapp)

    dialog.findChild(QtWidgets.QPushButton).click()
    _flush_qt_events(qapp)

    assert len(_FakePromptBox.instances) == 1
    assert dialog.confirmedCanceled() is False
    assert dialog.isVisible() is True


@pytest.mark.qt
def test_progress_dialog_keeps_one_batch_clock_across_items_and_minimize(
    monkeypatch, progress_dialog_module, qapp
):
    clock = MagicMock(elapsed=MagicMock(return_value=0))
    monkeypatch.setattr(progress_dialog_module.QtCore, "QElapsedTimer", lambda: clock)
    parent = QtWidgets.QWidget()
    parent.show()
    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 4, parent)
    batch_button = QtWidgets.QPushButton(parent)
    batch_button.setCheckable(True)
    dialog.minimizedChanged.connect(batch_button.setChecked)
    assert dialog.runtime_timer.isActive()
    assert dialog.runtime_timer.interval() == 1000
    dialog.setWindowModality(QtCore.Qt.WindowModal)
    dialog.setValue(1)
    dialog.show()
    _flush_qt_events(qapp)
    assert qapp.activeModalWidget() is dialog

    bar = dialog.findChild(QtWidgets.QProgressBar)
    assert not batch_button.isChecked()
    cancel_button = dialog.findChild(QtWidgets.QPushButton)
    checkbox = dialog.remove_completed_checkbox
    assert not checkbox.isChecked()
    label = dialog.findChild(QtWidgets.QLabel)
    assert label.height() >= label.sizeHint().height()
    assert label.geometry().bottom() < bar.y()
    assert checkbox.y() > bar.geometry().bottom()
    assert checkbox.geometry().bottom() < dialog.runtime_label.y()
    assert checkbox.geometry().bottom() < cancel_button.y()
    stop_checkbox = dialog.stop_after_completion_checkbox
    assert not stop_checkbox.isChecked()
    assert checkbox.geometry().bottom() < stop_checkbox.y()
    assert stop_checkbox.geometry().bottom() < dialog.runtime_label.y()
    stop_checkbox.setChecked(True)
    assert dialog.runtime_label.y() > bar.geometry().bottom()
    assert not dialog.runtime_label.geometry().intersects(cancel_button.geometry())

    dialog.showMinimized()
    dialog.setValue(2)
    dialog.setLabelText("second.png")
    clock.elapsed.return_value = 3661000
    dialog.runtime_timer.timeout.emit()
    assert dialog.runtime_label.text() == "Runtime: 01:01:01"
    _flush_qt_events(qapp)
    assert not dialog.isVisible()
    assert batch_button.isChecked()
    assert qapp.activeModalWidget() is None
    assert not dialog.confirmedCanceled()

    dialog.show()
    _flush_qt_events(qapp)
    assert dialog.isVisible()
    assert dialog.value() == 2
    assert stop_checkbox.isChecked()
    assert checkbox.y() > bar.geometry().bottom()
    assert checkbox.geometry().bottom() < cancel_button.y()
    assert not batch_button.isChecked()
    assert qapp.activeModalWidget() is dialog
    clock.elapsed.return_value = 3662000
    dialog.close_without_confirmation()
    clock.start.assert_called_once()
    assert not dialog.runtime_timer.isActive()
    assert dialog.runtime_label.text() == "Runtime: 01:01:02"
    parent.close()
    next_dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 4)
    assert not next_dialog.stop_after_completion_checkbox.isChecked()
    next_dialog.close_without_confirmation()


@pytest.mark.qt
@pytest.mark.parametrize("total_items", [None, 3])
def test_progress_dialog_item_labels_use_completed_progress(
    progress_dialog_module, qapp, total_items
):
    dialog = progress_dialog_module.ProgressDialog(
        "Starting", "Cancel", 0, 3, total_items=total_items
    )
    assert dialog.labelText() == "Starting"
    for completed in range(3):
        dialog.setValue(completed)
        dialog.setLabelText("image.png")
        expected = (
            f"Processing ({completed + 1}/3): image.png"
            if total_items is not None
            else "image.png"
        )
        assert dialog.labelText() == expected
    dialog.close_without_confirmation()


@pytest.mark.qt
def test_skip_discards_without_cancel_confirmation(progress_dialog_module, qapp):
    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 2)
    dialog.show()
    _flush_qt_events(qapp)
    assert dialog.runtime_label.geometry().right() < dialog.skip_button.x()
    assert dialog.skip_button.geometry().right() < dialog.stop_button.x()
    assert dialog.stop_button.geometry().right() < dialog.cancel_button.x()
    dialog.remove_completed_checkbox.setChecked(True)
    dialog.stop_after_completion_checkbox.setChecked(True)
    dialog.skip_button.click()
    assert dialog.skip_requested
    assert not dialog.stop_requested
    assert not dialog.confirmedCanceled()
    assert not dialog.skip_button.isEnabled()
    assert not dialog.stop_button.isEnabled()
    assert not dialog.cancel_button.isEnabled()
    dialog.close_without_confirmation()
