import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize("platform", ["offscreen", "windows"])
def test_batch_save_minimize_is_independent(platform):
    script = textwrap.dedent('''
        from PySide6 import QtCore, QtWidgets, QtTest
        from app.ui.widgets.batch_save_jobs_dialog import BatchSaveJobsDialog
        import tempfile
        from app.ui.widgets import batch_save_jobs_dialog

        settings_dir = tempfile.TemporaryDirectory()
        def isolated_settings(namespace, parent):
            settings = QtCore.QSettings(settings_dir.name + "/settings.ini", QtCore.QSettings.IniFormat, parent)
            settings.beginGroup(namespace)
            return settings
        batch_save_jobs_dialog.settings_group = isolated_settings

        app = QtWidgets.QApplication([])
        parent = QtWidgets.QWidget()
        parent.show()
        dialog = BatchSaveJobsDialog(parent, [])
        events = []
        dialog.minimizedChanged.connect(events.append)
        assert callable(dialog.finished.connect)
        assert dialog.windowModality() == QtCore.Qt.NonModal
        assert dialog.windowFlags() & QtCore.Qt.WindowMinimizeButtonHint
        dialog.show()
        QtTest.QTest.qWait(100)
        dialog.showMinimized()
        QtTest.QTest.qWait(100)
        assert dialog.isMinimized()
        assert not dialog.isHidden()
        assert not parent.isMinimized()
        assert events == [True]
        assert not dialog.cancel_requested
        dialog.showNormal()
        QtTest.QTest.qWait(100)
        assert events == [True, False]
        parent.showMinimized()
        QtTest.QTest.qWait(100)
        assert parent.isMinimized()
        assert not dialog.isMinimized()
        assert events == [True, False]
        parent.showNormal()
        QtTest.QTest.qWait(100)
        assert not dialog.isMinimized()
        assert events == [True, False]
        assert not dialog.timer.isActive()
        assert dialog.start_button.isEnabled()
        assert not dialog.pause_button.isEnabled()
        dialog.timer.stop()
        dialog.is_finished = True
        dialog.close()
        parent.close()
    ''')
    result = subprocess.run(
        [sys.executable, "-u", "-c", script],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": platform},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("remove_completed", [False, True])
def test_batch_save_jobs_dialog_with_real_qt(tmp_path, remove_completed):
    script = textwrap.dedent('''
        import json
        from pathlib import Path
        import sys
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch
        from PySide6 import QtCore, QtWidgets
        from app.ui.widgets.batch_save_jobs_dialog import BatchSaveJobsDialog
        import tempfile
        from app.ui.widgets import batch_save_jobs_dialog

        settings_dir = tempfile.TemporaryDirectory()
        def isolated_settings(namespace, parent):
            settings = QtCore.QSettings(settings_dir.name + "/settings.ini", QtCore.QSettings.IniFormat, parent)
            settings.beginGroup(namespace)
            return settings
        batch_save_jobs_dialog.settings_group = isolated_settings
        from app.ui.widgets import actions

        app = QtWidgets.QApplication([])
        root = Path(sys.argv[1])
        remove_completed = sys.argv[2] == "True"
        for mode in ("complete", "stop", "limit_one", "limit_two", "limit_large", "limit_unchecked", "cancel", "cancel_before", "empty", "pause_resume", "pause_cancel", "stop_button", "pause_stop"):
            jobs = root / mode
            jobs.mkdir()
            existing = jobs / "sample.json"
            existing.write_text("existing")
            window = QtWidgets.QWidget()
            window.control = {"ClusterOutputBySourceToggle": True}
            media = [SimpleNamespace(media_id=str(i), media_path="sample.png", file_type="image") for i in range(3)]
            if mode == "empty":
                media = []
            window.targetVideosList = QtWidgets.QListWidget(window)
            window.target_videos = {item.media_id: item for item in media}
            window.selected_video_button = media[0] if media else None
            window.placeholder_update_signal = MagicMock()
            for item in media:
                list_item = QtWidgets.QListWidgetItem(item.media_id, window.targetVideosList)
                item.get_item_position = lambda entry=list_item: window.targetVideosList.row(entry)
                item.deleteLater = MagicMock()
            workspace = {"target_faces_data": {"face": {"parameters": {"strength": 75}}}}
            manager = SimpleNamespace(
                _serialize_job_data=MagicMock(return_value=workspace),
                get_jobs_dir=lambda mw: jobs,
                refresh_new_jobs=MagicMock(),
            )
            settings = isolated_settings("Dialogs/BatchSaveJobs", window)
            settings.clear()
            settings.setValue("stop_after_completion_checkbox", True)
            dialog = BatchSaveJobsDialog(window, media)
            assert not dialog.stop_after_completion_checkbox.isChecked()
            assert not settings.contains("stop_after_completion_checkbox")
            assert dialog.stop_after_processing_spinbox.value() == 100
            assert not dialog.stop_after_processing_spinbox.isEnabled()
            assert not dialog.stop_after_processing_checkbox.isChecked()
            assert not dialog.remove_completed_checkbox.isChecked()
            dialog.remove_completed_checkbox.setChecked(remove_completed)
            limit = {"limit_one": 1, "limit_two": 2, "limit_large": 100, "limit_unchecked": 1}.get(mode, 100)
            dialog.stop_after_processing_spinbox.setValue(limit)
            limited = mode in ("limit_one", "limit_two", "limit_large")
            dialog.stop_after_processing_checkbox.setChecked(limited)
            assert dialog.stop_after_processing_spinbox.isEnabled() == limited
            dialog.resize(700, 360)
            completed = []
            review_timer = QtCore.QTimer()
            def review_completion():
                if not dialog.is_finished:
                    return
                review_timer.stop()
                assert dialog.isVisible()
                assert dialog.windowTitle() == "Batch Saving Jobs..."
                assert len(dialog.findChildren(QtWidgets.QFormLayout)) == 2
                assert dialog.cancel_button.text() == "Close"
                assert dialog.cancel_button.isEnabled()
                assert not dialog.timer.isActive()
                assert dialog.report_labels["Queued:"].text() == str(len(media))
                assert dialog.report_labels["Saved:"].text() == str(len(dialog.saved_names))
                assert dialog.report_labels["Cancelled:"].text() == str(dialog.started_count - len(dialog.saved_names))
                assert dialog.report_labels["Not started:"].text() == str(len(media) - dialog.started_count)
                assert dialog.details.toPlainText() == "\\n".join(dialog.saved_names)
                if dialog.cancel_requested:
                    assert dialog.status_label.text() == "Cancelled."
                elif len(dialog.saved_names) < len(media):
                    assert dialog.status_label.text() == "Stopped."
                else:
                    assert dialog.status_label.text() == "Done."
                    assert dialog.progress_bar.value() == dialog.progress_bar.maximum()
                    assert "100%" in dialog.progress_bar.text()
                completed.append(True)
                dialog.cancel_button.click()
            review_timer.timeout.connect(review_completion)
            review_timer.start(10)
            encoder = json.JSONEncoder.iterencode
            resumed_after_cancel = []
            def interrupted_encoding(self, value):
                QtCore.QTimer.singleShot(0, dialog.cancel)
                QtCore.QThread.msleep(25)
                yield "{"
                resumed_after_cancel.append(True)
                yield "}"
            stopped_during_save = []
            def stop_during_encoding(self, value):
                def request_stop():
                    assert list(jobs.glob("*.part"))
                    assert not list(jobs.glob("sample_*.json"))
                    assert dialog.stop_button.isEnabled()
                    if mode == "pause_stop":
                        dialog.pause_button.click()
                        QtCore.QTimer.singleShot(50, dialog.stop_button.click)
                    else:
                        dialog.stop_button.click()
                    stopped_during_save.append(True)
                QtCore.QTimer.singleShot(0, request_stop)
                QtCore.QThread.msleep(25)
                yield from encoder(self, value)
            if mode == "stop":
                dialog.stop_after_completion_checkbox.setChecked(True)
            if mode == "cancel_before":
                QtCore.QTimer.singleShot(0, dialog.reject)
            else:
                def begin():
                    assert not list(jobs.glob("sample_*.json"))
                    manager._serialize_job_data.assert_not_called()
                    assert dialog.start_button.isEnabled()
                    assert not dialog.pause_button.isEnabled()
                    assert not dialog.stop_button.isEnabled()
                    assert not dialog.timer.isActive()
                    assert f"Found {len(media)} images and 0 videos" in dialog.summary_label.text()
                    dialog.start_button.click()
                QtCore.QTimer.singleShot(0, begin)
            pauses = []
            if mode in ("pause_resume", "pause_cancel"):
                def check_paused():
                    assert len(dialog.saved_names) == 1
                    assert len(list(jobs.glob("sample_*.json"))) == 1
                    assert dialog.start_button.isEnabled()
                    assert not dialog.pause_button.isEnabled()
                    assert "Paused" in dialog.status_label.text()
                    pauses.append(True)
                    if mode == "pause_cancel":
                        dialog.cancel_button.click()
                    else:
                        dialog.start_button.click()
                        assert not dialog.start_button.isEnabled()
                        assert dialog.pause_button.isEnabled()
                def pause_after_first(value):
                    if value == 1:
                        dialog.pause_button.click()
                        QtCore.QTimer.singleShot(50, check_paused)
                dialog.progress_bar.valueChanged.connect(pause_after_first)
            with patch.object(actions, "job_manager_actions", manager, create=True), \
                 patch.object(json.JSONEncoder, "iterencode", interrupted_encoding if mode == "cancel" else stop_during_encoding if mode in ("stop_button", "pause_stop") else encoder):
                dialog.run()
            saved = {path.name: json.loads(path.read_text()) for path in jobs.glob("sample_*.json")}
            expected = {"complete": 3, "stop": 1, "limit_one": 1, "limit_two": 2, "limit_large": 3, "limit_unchecked": 3, "cancel": 0, "cancel_before": 0, "empty": 0, "pause_resume": 3, "pause_cancel": 1, "stop_button": 1, "pause_stop": 1}[mode]
            assert stopped_during_save == ([True] if mode in ("stop_button", "pause_stop") else [])
            assert not dialog.stop_button.isEnabled()
            assert pauses == ([True] if mode in ("pause_resume", "pause_cancel") else [])
            assert len(saved) == expected
            removed = expected if remove_completed else 0
            assert list(window.target_videos) == [item.media_id for item in media[removed:]]
            assert window.targetVideosList.count() == len(media) - removed
            assert window.selected_video_button is (None if removed or not media else media[0])
            for index, item in enumerate(media):
                assert item.deleteLater.call_count == int(index < removed)
            if removed and removed == len(media):
                window.placeholder_update_signal.emit.assert_called_once_with(window.targetVideosList, False)
            else:
                window.placeholder_update_signal.emit.assert_not_called()
            assert dialog.progress_bar.value() == (1 if mode == "empty" else expected)
            assert dialog.is_finished and not dialog.timer.isActive()
            assert not list(jobs.glob("*.part"))
            assert existing.read_text() == "existing"
            assert not resumed_after_cancel
            assert completed == [True]
            assert not dialog.isVisible()
            if mode == "cancel_before":
                manager._serialize_job_data.assert_not_called()
            if expected:
                manager._serialize_job_data.assert_called_once_with(window)
                manager.refresh_new_jobs.assert_called_once_with(
                    window, selected_job_name=f"sample_{expected}",
                    saved_jobs={Path(name).stem: data for name, data in saved.items()},
                )
                for i, data in enumerate(saved.values()):
                    assert data["selected_media_id"] == str(i)
                    assert data["target_medias_data"] == [{"media_id": str(i), "media_path": "sample.png"}]
                    assert data["restore_selected_face"] is True
                    assert data["use_job_name_for_output"] is True
                    assert data["output_file_name"] is None
                    assert data["target_faces_data"] == workspace["target_faces_data"]
            else:
                manager.refresh_new_jobs.assert_not_called()
            reopened = BatchSaveJobsDialog(window, media)
            reopened.show()
            app.processEvents()
            assert not reopened.stop_after_completion_checkbox.isChecked()
            assert reopened.remove_completed_checkbox.isChecked() == remove_completed
            assert reopened.stop_after_processing_checkbox.isChecked() == limited
            assert reopened.stop_after_processing_spinbox.value() == limit
            assert reopened.stop_after_processing_spinbox.isEnabled() == limited
            reopened.stop_after_processing_checkbox.setChecked(not limited)
            assert reopened.stop_after_processing_spinbox.isEnabled() != limited
            assert reopened.size() == dialog.size()
            assert reopened.pos() == dialog.pos()
            reopened.stop_after_completion_checkbox.setChecked(True)
            assert not settings.contains("stop_after_completion_checkbox")
            reopened.timer.stop()
            reopened.deleteLater()
            dialog.deleteLater()
            window.deleteLater()
            app.processEvents()
    ''')
    result = subprocess.run(
        [sys.executable, "-u", "-c", script, str(tmp_path), str(remove_completed)],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
