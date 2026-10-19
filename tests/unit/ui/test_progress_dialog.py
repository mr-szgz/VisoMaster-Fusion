from __future__ import annotations

import importlib
import os
import sys
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from functools import wraps

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6 import QtWidgets, QtCore, QtGui


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


@pytest.fixture(autouse=True)
def isolated_dialog_settings(progress_dialog_module, monkeypatch, tmp_path):
    def settings_group(namespace, parent):
        settings = QtCore.QSettings(str(tmp_path / "dialogs.ini"), QtCore.QSettings.IniFormat, parent)
        settings.setFallbacksEnabled(False)
        settings.beginGroup(namespace)
        return settings
    monkeypatch.setattr(progress_dialog_module, "settings_group", settings_group)


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
@pytest.mark.parametrize("reply", [QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Cancel])
@pytest.mark.parametrize("save_partial", [False, True])
@pytest.mark.parametrize("frames, minimum_enabled", [(0, False), (29, True), (30, True), (31, True)])
def test_skip_button_batch_interrupt_wiring(progress_dialog_module, qapp, monkeypatch, reply, save_partial, frames, minimum_enabled):
    source = Path(__file__).resolve().parents[3] / "app/ui/widgets/actions/video_control_actions.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    handler = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "interrupt_skipped_media")
    connection = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
        and any(isinstance(arg, ast.Name) and arg.id == "interrupt_skipped_media" for arg in node.value.args)
    )
    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 2)
    dialog.save_partial_on_skip_checkbox.setChecked(save_partial)
    dialog.minimum_partial_frames_checkbox.setChecked(minimum_enabled)
    dialog.minimum_partial_frames_spinbox.setValue(30)
    processor = SimpleNamespace(
        frames_written=frames,
        recording=True, processing=True, is_processing_segments=False,
        stop_processing=MagicMock(), _finalize_default_style_recording=MagicMock(),
    )
    namespace = {"progress_dialog": dialog, "main_window": SimpleNamespace(video_processor=processor)}
    exec(compile(ast.Module(body=[handler, connection], type_ignores=[]), str(source), "exec"), namespace)
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", MagicMock(return_value=reply))

    dialog.skip_button.click()

    confirmed = reply == QtWidgets.QMessageBox.Yes
    assert dialog.skip_requested == confirmed
    save_output = save_partial and (not minimum_enabled or frames >= 30)
    assert processor.stop_processing.call_count == int(confirmed and not save_output)
    assert processor._finalize_default_style_recording.call_count == int(confirmed and save_output)
    assert dialog.skip_button.isEnabled() == (not confirmed)
    assert dialog.stop_button.isEnabled() == (not confirmed)
    assert dialog.cancel_button.isEnabled() == (not confirmed)
    assert not dialog.stop_requested
    assert not dialog.confirmedCanceled()
    dialog.close_without_confirmation()


@pytest.mark.qt
@pytest.mark.parametrize("reply", [QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Cancel])
def test_progress_dialog_stop_preserves_cancel_state(progress_dialog_module, qapp, monkeypatch, reply):
    prompt = MagicMock(return_value=reply)
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", prompt)
    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 2)
    dialog.show()
    _flush_qt_events(qapp)

    assert dialog.stop_button.geometry().right() < dialog.cancel_button.x()
    assert dialog.runtime_label.geometry().right() < dialog.stop_button.x()
    dialog.stop_button.click()

    confirmed = reply == QtWidgets.QMessageBox.Yes
    assert dialog.stop_requested == confirmed
    assert not dialog.skip_requested
    assert not dialog.confirmedCanceled()
    assert dialog.stop_button.isEnabled() == (not confirmed)
    assert dialog.skip_button.isEnabled() == (not confirmed)
    assert dialog.cancel_button.isEnabled() == (not confirmed)
    assert prompt.call_args.args[-1] == QtWidgets.QMessageBox.No
    dialog.close_without_confirmation()


@pytest.mark.qt
def test_batch_media_properties_update_without_job_data(progress_dialog_module, qapp):
    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 3)
    dialog.show()
    dialog.set_media_properties(["Alice", "Bob"], 90000, 25)
    _flush_qt_events(qapp)
    labels = dialog.media_report_labels
    assert labels["Embedding:"][1].text() == "Alice, Bob"
    assert labels["Frames:"][1].text() == "0 / 90,000"
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
    assert labels["Frames:"][1].text() == "0 / 1"
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
    clock = MagicMock(elapsed=MagicMock(return_value=0), isValid=MagicMock(return_value=False))
    monkeypatch.setattr(progress_dialog_module.QtCore, "QElapsedTimer", lambda: clock)
    parent = QtWidgets.QWidget()
    parent.show()
    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 4, parent)
    batch_button = QtWidgets.QPushButton(parent)
    batch_button.setCheckable(True)
    dialog.minimizedChanged.connect(batch_button.setChecked)
    assert dialog.runtime_timer.isActive()
    assert dialog.runtime_timer.interval() == 1000
    dialog.setWindowModality(QtCore.Qt.NonModal)
    dialog.setValue(1)
    dialog.show()
    _flush_qt_events(qapp)
    assert qapp.activeModalWidget() is None

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
    assert dialog.isMinimized()
    assert not dialog.isHidden()
    assert not parent.isMinimized()
    assert batch_button.isChecked()
    assert qapp.activeModalWidget() is None
    assert not dialog.confirmedCanceled()

    parent.showMinimized()
    _flush_qt_events(qapp)
    parent.showNormal()
    _flush_qt_events(qapp)
    dialog.showNormal()
    _flush_qt_events(qapp)
    assert dialog.isVisible()
    assert not dialog.isMinimized()
    assert dialog.value() == 2
    assert stop_checkbox.isChecked()
    assert checkbox.y() > bar.geometry().bottom()
    assert checkbox.geometry().bottom() < cancel_button.y()
    assert not batch_button.isChecked()
    assert qapp.activeModalWidget() is None
    parent.showMinimized()
    _flush_qt_events(qapp)
    assert not dialog.isMinimized()
    assert not batch_button.isChecked()
    parent.showNormal()
    _flush_qt_events(qapp)
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
        "Starting", "Cancel", 0, 3000, total_items=total_items
    )
    assert dialog.labelText() == "Starting"
    for completed in range(3):
        dialog.setValue(completed * 1000 + 500)
        dialog.setLabelText("image.png")
        expected = (
            f"Processing ({completed + 1}/3): image.png"
            if total_items is not None
            else "image.png"
        )
        assert dialog.labelText() == expected
    dialog.close_without_confirmation()


@pytest.mark.qt
@pytest.mark.parametrize("checked", [False, True])
def test_batch_checkbox_preferences_exclude_stop_after_current(progress_dialog_module, qapp, checked):
    settings = progress_dialog_module.settings_group("Dialogs/BatchProcessing", qapp)
    settings.setValue("stop_after_completion_checkbox", True)
    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 4)
    assert not dialog.stop_after_completion_checkbox.isChecked()
    assert not settings.contains("stop_after_completion_checkbox")
    dialog.stop_after_completion_checkbox.setChecked(True)
    assert not settings.contains("stop_after_completion_checkbox")
    names = (
        "remove_completed_checkbox", "stop_after_processing_checkbox",
        "save_skipped_checkbox", "save_partial_on_skip_checkbox",
        "minimum_partial_frames_checkbox", "clear_skipped_checkbox",
        "suppress_notifications_checkbox",
    )
    for name in names:
        checkbox = getattr(dialog, name)
        checkbox.setChecked(not checked)
        checkbox.setChecked(checked)
    dialog.close_without_confirmation()
    reopened = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 4)
    assert not reopened.stop_after_completion_checkbox.isChecked()
    for name in names:
        assert getattr(reopened, name).isChecked() == checked
        assert settings.value(name, type=bool) == checked
    reopened.close_without_confirmation()


@pytest.mark.qt
@pytest.mark.parametrize("outcome", ["complete", "stopped", "cancelled", "failed"])
def test_final_report_is_not_suppressed_by_finished_batch(
    progress_dialog_module, qapp, monkeypatch, outcome
):
    source = Path("app/ui/widgets/actions/common_actions.py")
    functions = [node for node in ast.parse(source.read_text(encoding="utf-8")).body
                 if isinstance(node, ast.FunctionDef) and node.name in (
                     "suppress_batch_notifications", "create_and_show_messagebox")]
    namespace = dict(QtCore=QtCore, QtWidgets=QtWidgets, QtGui=QtGui, wraps=wraps)
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)
    displayed = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec_", lambda box: displayed.append(box.text()))
    parent = QtWidgets.QWidget()
    parent.is_batch_processing = True
    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 1000, parent)
    dialog.suppress_notifications_checkbox.setChecked(True)
    display = namespace["create_and_show_messagebox"]
    display(parent, "Processing", "Intermediate notification", parent)
    assert displayed == []
    parent.is_batch_processing = False
    dialog.close_without_confirmation()
    dialog.deleteLater()
    # Deferred deletion leaves the checked checkbox alive when the report is sent.
    assert parent.findChildren(QtWidgets.QCheckBox, "suppressBatchNotificationsCheckbox")
    display(parent, "Batch Complete", f"Batch processing {outcome}.", parent)
    assert displayed == [f"Batch processing {outcome}."]
    _flush_qt_events(qapp)
    parent.close()


@pytest.mark.qt
@pytest.mark.parametrize("reply", [QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Cancel])
@pytest.mark.parametrize("save_partial", [True, False])
def test_skip_requires_confirmation(progress_dialog_module, qapp, monkeypatch, reply, save_partial):
    prompt = MagicMock(return_value=reply)
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", prompt)
    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 2)
    dialog.show()
    _flush_qt_events(qapp)
    assert dialog.runtime_label.geometry().right() < dialog.skip_button.x()
    assert dialog.skip_button.geometry().right() < dialog.stop_button.x()
    assert dialog.stop_button.geometry().right() < dialog.cancel_button.x()
    dialog.remove_completed_checkbox.setChecked(True)
    dialog.stop_after_completion_checkbox.setChecked(True)
    dialog.save_partial_on_skip_checkbox.setChecked(save_partial)
    dialog.skip_button.click()
    confirmed = reply == QtWidgets.QMessageBox.Yes
    assert dialog.skip_requested == confirmed
    assert not dialog.stop_requested
    assert not dialog.confirmedCanceled()
    assert dialog.skip_button.isEnabled() == (not confirmed)
    assert dialog.stop_button.isEnabled() == (not confirmed)
    assert dialog.cancel_button.isEnabled() == (not confirmed)
    assert prompt.call_args.args[-1] == QtWidgets.QMessageBox.No
    assert ("Save the partial recording only if at least 30 frames" if save_partial else "Discard the partial recording.") in prompt.call_args.args[2]
    dialog.close_without_confirmation()


@pytest.mark.qt
def test_batch_dialog_frame_rate_and_item_progress(progress_dialog_module, qapp):
    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 3000, total_items=3)
    dialog.setValue(1000)
    dialog.set_media_properties([], 100, 25)
    dialog.processing_started()
    for _ in range(25):
        dialog.frame_processed()
    assert dialog.processed_frames_since_update == 25
    clock = MagicMock(isValid=MagicMock(return_value=True), nsecsElapsed=MagicMock(return_value=2_000_000_000))
    dialog.processing_rate_clock = clock
    dialog.set_item_progress(25, 100)
    dialog.update_runtime()
    assert dialog.value() == 1250
    assert dialog.media_report_labels["Frames:"][1].text() == "25 / 100"
    assert dialog.media_report_labels["Item progress:"][1].text() == "25.0%"
    assert dialog.media_report_labels["it/s:"][1].text() == "12.50"
    assert dialog.processed_frames_since_update == 0
    clock.restart.assert_called_once()
    dialog.set_item_progress(100, 100)
    assert dialog.value() == 2000
    dialog.processing_stopped()
    clock.invalidate.assert_called_once()
    assert dialog.media_report_labels["it/s:"][1].text() == "0.00"
    clock.isValid.return_value = False
    dialog.set_media_properties([], 1, 0)
    assert dialog.media_report_labels["Frames:"][1].text() == "0 / 1"
    assert dialog.media_report_labels["Item progress:"][1].text() == "0.0%"
    dialog.set_item_progress(1, 1)
    assert dialog.value() == 3000
    dialog.close_without_confirmation()


@pytest.mark.qt
def test_stop_after_processing_settings_and_layout(progress_dialog_module, qapp):
    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 2000)
    assert not dialog.stop_after_processing_checkbox.isChecked()
    assert dialog.stop_after_processing_spinbox.value() == 100
    assert not dialog.stop_after_processing_spinbox.isEnabled()
    dialog.stop_after_processing_checkbox.setChecked(True)
    assert dialog.stop_after_processing_spinbox.isEnabled()
    assert not dialog.stop_after_completion_checkbox.isChecked()
    dialog.stop_after_processing_spinbox.setValue(25)
    dialog.show()
    _flush_qt_events(qapp)
    assert dialog.checkbox_separator.geometry().bottom() < dialog.stop_after_completion_checkbox.y()
    assert dialog.stop_after_completion_checkbox.geometry().bottom() < dialog.stop_after_processing_row.y()
    assert dialog.stop_after_processing_row.geometry().bottom() < dialog.suppress_notifications_checkbox.y()
    assert dialog.suppress_notifications_checkbox.geometry().bottom() < dialog.buttons_separator.y()
    dialog.close_without_confirmation()
    reopened = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 2000)
    assert reopened.stop_after_processing_checkbox.isChecked()
    assert reopened.stop_after_processing_spinbox.value() == 25
    assert reopened.stop_after_processing_spinbox.isEnabled()
    reopened.stop_after_processing_checkbox.setChecked(False)
    assert not reopened.stop_after_processing_spinbox.isEnabled()
    reopened.close_without_confirmation()


@pytest.mark.qt
def test_minimum_partial_frames_settings_and_layout(progress_dialog_module, qapp):
    dialog = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 2)
    assert dialog.minimum_partial_frames_spinbox.value() == 30
    assert dialog.minimum_partial_frames_checkbox.isChecked()
    dialog.save_partial_on_skip_checkbox.setChecked(False)
    assert not dialog.minimum_partial_frames_checkbox.isEnabled()
    assert not dialog.minimum_partial_frames_spinbox.isEnabled()
    dialog.save_partial_on_skip_checkbox.setChecked(True)
    assert dialog.minimum_partial_frames_checkbox.isEnabled()
    assert dialog.minimum_partial_frames_spinbox.isEnabled()
    dialog.minimum_partial_frames_checkbox.setChecked(False)
    assert not dialog.minimum_partial_frames_spinbox.isEnabled()
    dialog.minimum_partial_frames_checkbox.setChecked(True)
    dialog.minimum_partial_frames_spinbox.setValue(75)
    dialog.show()
    _flush_qt_events(qapp)
    assert dialog.save_partial_on_skip_checkbox.geometry().bottom() < dialog.minimum_partial_frames_row.y()
    assert dialog.minimum_partial_frames_row.geometry().bottom() < dialog.clear_skipped_checkbox.y()
    dialog.close_without_confirmation()
    reopened = progress_dialog_module.ProgressDialog("Working", "Cancel", 0, 2)
    assert reopened.minimum_partial_frames_spinbox.value() == 75
    assert reopened.minimum_partial_frames_checkbox.isChecked()
    assert reopened.minimum_partial_frames_spinbox.isEnabled()
    reopened.close_without_confirmation()
