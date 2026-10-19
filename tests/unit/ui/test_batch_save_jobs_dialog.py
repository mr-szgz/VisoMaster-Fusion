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
        assert dialog.timer.isActive()
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
@pytest.mark.parametrize("suppress_notifications", [False, True])
def test_batch_save_jobs_dialog_with_real_qt(tmp_path, remove_completed, suppress_notifications):
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
        suppress_notifications = sys.argv[3] == "True"
        for mode in ("complete", "stop", "limit_one", "limit_two", "limit_large", "limit_unchecked", "cancel", "cancel_before", "empty"):
            jobs = root / mode
            jobs.mkdir()
            existing = jobs / "sample.json"
            existing.write_text("existing")
            window = QtWidgets.QWidget()
            window.control = {"ClusterOutputBySourceToggle": True}
            media = [SimpleNamespace(media_id=str(i), media_path="sample.png") for i in range(3)]
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
            assert not dialog.suppress_notifications_checkbox.isChecked()
            dialog.suppress_notifications_checkbox.setChecked(suppress_notifications)
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
            reports = []
            def inspect_report(report):
                reports.append((report.windowTitle(), report.findChild(QtWidgets.QLabel).text()))
                return QtWidgets.QDialog.Accepted
            encoder = json.JSONEncoder.iterencode
            resumed_after_cancel = []
            def interrupted_encoding(self, value):
                QtCore.QTimer.singleShot(0, dialog.cancel)
                QtCore.QThread.msleep(25)
                yield "{"
                resumed_after_cancel.append(True)
                yield "}"
            if mode == "stop":
                dialog.stop_after_completion_checkbox.setChecked(True)
            if mode == "cancel_before":
                QtCore.QTimer.singleShot(0, dialog.reject)
            with patch.object(actions, "job_manager_actions", manager, create=True), \
                 patch.object(QtWidgets.QDialog, "exec", inspect_report), \
                 patch.object(json.JSONEncoder, "iterencode", interrupted_encoding if mode == "cancel" else encoder):
                dialog.run()
            saved = {path.name: json.loads(path.read_text()) for path in jobs.glob("sample_*.json")}
            expected = {"complete": 3, "stop": 1, "limit_one": 1, "limit_two": 2, "limit_large": 3, "limit_unchecked": 3, "cancel": 0, "cancel_before": 0, "empty": 0}[mode]
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
            assert dialog.progress_bar.value() == expected
            assert dialog.is_finished and not dialog.timer.isActive()
            assert not list(jobs.glob("*.part"))
            assert existing.read_text() == "existing"
            assert not resumed_after_cancel
            assert len(reports) == int(not suppress_notifications)
            if not suppress_notifications:
                title, summary = reports[0]
                assert f"Saved: {expected}" in summary
                if mode == "cancel":
                    assert "Cancelled: 1" in summary and "Not started: 2" in summary
                    assert title.endswith("Cancelled")
                elif mode in ("stop", "limit_one", "limit_two"):
                    assert "Cancelled: 0" in summary and f"Not started: {3 - expected}" in summary
                    assert title.endswith("Stopped")
                elif mode == "cancel_before":
                    assert "Not started: 3" in summary
                else:
                    assert title.endswith("Complete")
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
            assert reopened.suppress_notifications_checkbox.isChecked() == suppress_notifications
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
        [sys.executable, "-u", "-c", script, str(tmp_path), str(remove_completed), str(suppress_notifications)],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
