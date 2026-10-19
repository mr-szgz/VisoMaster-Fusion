"""Exercise real Qt dialogs and the job worker without running GPU inference."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_job_progress_checkbox_preferences(tmp_path):
    script = textwrap.dedent('''
        import sys
        from PySide6 import QtCore, QtWidgets
        from app.ui.widgets import job_progress_dialog

        app = QtWidgets.QApplication([])
        def isolated_settings(namespace, parent):
            settings = QtCore.QSettings(sys.argv[1], QtCore.QSettings.IniFormat, parent)
            settings.beginGroup(namespace)
            return settings
        job_progress_dialog.settings_group = isolated_settings
        settings = isolated_settings("Dialogs/JobProcessing", app)
        for checked in (True, False):
            settings.setValue("stop_after_completion_checkbox", True)
            dialog = job_progress_dialog.JobProgressDialog(None, {})
            assert not dialog.stop_after_completion_checkbox.isChecked()
            assert not settings.contains("stop_after_completion_checkbox")
            dialog.stop_after_completion_checkbox.setChecked(True)
            assert not settings.contains("stop_after_completion_checkbox")
            dialog.save_partial_on_skip_checkbox.setChecked(not checked)
            dialog.save_partial_on_skip_checkbox.setChecked(checked)
            dialog.finish()
            reopened = job_progress_dialog.JobProgressDialog(None, {})
            assert not reopened.stop_after_completion_checkbox.isChecked()
            assert reopened.save_partial_on_skip_checkbox.isChecked() == checked
            assert settings.value("save_partial_on_skip_checkbox", type=bool) == checked
            reopened.finish()
            dialog.deleteLater()
            reopened.deleteLater()
            app.processEvents()
    ''')
    result = subprocess.run(
        [sys.executable, "-u", "-c", script, str(tmp_path / "dialogs.ini")],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_job_progress_lifecycle(tmp_path):
    script = textwrap.dedent('''
        import os
        import sys
        import threading
        import time
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        from PySide6 import QtCore, QtWidgets, QtTest
        import qdarktheme
        from app.ui.widgets.actions import job_manager_actions as actions
        from app.ui.widgets.job_list_widgets import JobDataRole as Role
        from app.ui.widgets import job_progress_dialog
        from app.ui.widgets.job_progress_dialog import JobProgressDialog

        app = QtWidgets.QApplication([])
        app.setStyleSheet(qdarktheme.load_stylesheet(theme="dark"))
        root = Path(sys.argv[1])
        def isolated_settings(namespace, parent):
            settings = QtCore.QSettings(str(root / "dialogs.ini"), QtCore.QSettings.IniFormat, parent)
            settings.beginGroup(namespace)
            return settings

        class Video(QtCore.QObject):
            processing_started_signal = QtCore.Signal()
            processing_stopped_signal = QtCore.Signal()
            processing_heartbeat_signal = QtCore.Signal()
            frame_processed_signal = QtCore.Signal()
            is_processing_segments = False
            recording = False
            def stop_processing(self):
                self.processing_stopped_signal.emit()

        def wait_for(predicate):
            deadline = time.monotonic() + 8
            while not predicate() and time.monotonic() < deadline:
                QtTest.QTest.qWait(10)
            assert predicate()

        for selected in (False, True):
            for outcome in ("success", "stop", "cancel", "load_failure"):
                window = QtWidgets.QMainWindow()
                window.project_root_path = root / f"{selected}-{outcome}"
                jobs = window.project_root_path / "jobs"
                jobs.mkdir(parents=True)
                window.video_processor = Video(window)
                window.job_processor = None
                window.job_progress_dialog = None
                window.job_processing_button = None
                window.batch_progress_dialog = object()
                batch_dialog = window.batch_progress_dialog
                window.is_batch_processing = False
                window.jobQueueList = QtWidgets.QListWidget(window)
                window.jobListLabelTemplateComboBox = QtWidgets.QComboBox(window)
                window.jobListLabelTemplateComboBox.addItem("{job_name}")
                for attr, label in (
                    ("buttonProcessAll", "Process All"),
                    ("buttonProcessSelected", "Process Selected"),
                    ("buttonStopProcessing", "Stop Processing"),
                    ("addJobButton", "Save Job"), ("loadJobButton", "Load Job"),
                    ("deleteJobButton", "Delete Job"), ("refreshJobListButton", "Refresh"),
                    ("checkNewJobListButton", "Check for New"),
                ):
                    setattr(window, attr, QtWidgets.QPushButton(label, window))
                for name, fps in (("A", 25.0), ("B", 0.0)):
                    (jobs / f"{name}.json").write_text("{}")
                    item = QtWidgets.QListWidgetItem(name)
                    for role, value in (
                        (Role.JobNameRole, name), (Role.FrameCountRole, 50 if fps else 1),
                        (Role.FrameRateRole, fps), (Role.TargetMediaPathRole, f"{name}.media"),
                        (Role.EmbeddingNamesRole, ["Saved embedding"]),
                        (Role.UseJobNameForOutputRole, name == "A"),
                        (Role.OutputFileNameRole, "custom-output"),
                        (Role.RestoreSelectedFaceRole, True),
                    ):
                        item.setData(role, value)
                    window.jobQueueList.addItem(item)
                window.jobQueueList.item(1).setSelected(True)
                actions.connect_job_manager_signals(window)
                actions.update_job_manager_buttons(window)
                assert not window.buttonStopProcessing.isEnabled()
                gates = {name: threading.Event() for name in ("A", "B")}
                restored = []
                reports = []
                summaries = []

                def capture_report(box):
                    summary = box.findChild(QtWidgets.QLabel).text()
                    reports.append(box.windowTitle())
                    summaries.append(summary)
                    assert box.findChild(QtWidgets.QPlainTextEdit).toPlainText().startswith("Queued jobs:")
                    assert "Runtime:" in summary
                    return QtWidgets.QDialog.Accepted

                def analyze(worker):
                    worker.job_data_list = [{"job_name_internal": name} for name in worker.jobs]
                    return {}

                def load_assets(mw, data):
                    if outcome != "load_failure":
                        mw.job_processor.master_assets_loaded_event.set()

                def process(worker, name):
                    window.video_processor.processing_started_signal.emit()
                    while not gates[name].wait(0.01):
                        if worker.cancel_requested_event.is_set() or worker.stop_requested_event.is_set():
                            return False
                    return True

                with patch.object(job_progress_dialog, "settings_group", isolated_settings), \
                     patch.object(actions, "_serialize_job_data", return_value={"snapshot": True}), \
                     patch.object(actions, "_restore_workspace_from_snapshot", side_effect=lambda *args: restored.append(True)), \
                     patch.object(actions.JobProcessor, "_analyze_job_batch", analyze), \
                     patch.object(actions.JobProcessor, "_trigger_and_wait_for_processing", process), \
                     patch.object(actions.JobProcessor, "MASTER_ASSETS_LOAD_TIMEOUT", 0.1), \
                     patch.object(actions, "load_master_assets", load_assets), \
                     patch.object(actions, "load_job_settings", side_effect=lambda mw, data: mw.job_processor.job_settings_loaded_event.set()), \
                     patch.object(actions, "clear_job_settings", side_effect=lambda mw: mw.job_processor.job_settings_cleared_event.set()), \
                     patch.object(actions, "refresh_job_list", side_effect=lambda mw: mw.jobQueueList.clear()), \
                     patch.object(actions.video_control_actions, "block_if_issue_scan_active", return_value=False), \
                     patch.object(actions.QMessageBox, "information", side_effect=lambda *args: reports.append(args[1])), \
                     patch.object(actions.QMessageBox, "warning", side_effect=lambda *args: reports.append(args[1])), \
                     patch.object(QtWidgets.QDialog, "exec", capture_report), \
                     patch.object(actions.QMessageBox, "critical", side_effect=lambda *args: reports.append(args[1])):
                    active = window.buttonProcessSelected if selected else window.buttonProcessAll
                    other = window.buttonProcessAll if selected else window.buttonProcessSelected
                    active.click()
                    worker = window.job_processor
                    dialog = window.job_progress_dialog
                    assert worker.jobs == (["B"] if selected else ["A", "B"])
                    assert active.isEnabled() and not other.isEnabled()
                    assert not window.loadJobButton.isEnabled()
                    assert not window.deleteJobButton.isEnabled()
                    assert window.buttonStopProcessing.isEnabled()
                    if outcome == "load_failure":
                        wait_for(lambda: window.job_progress_dialog is None)
                        assert "Job Processing Failed" in reports
                    else:
                        wait_for(lambda: dialog.current_index == 1)
                        assert dialog.report_labels["Embedding:"][1].text() == "Saved embedding"
                        assert dialog.report_labels["Frames:"][1].text() == ("1" if selected else "50")
                        assert dialog.report_labels["Frame rate:"][0].isVisible() is not selected
                        assert active.text().endswith("(1/1)" if selected else "(1/2)")
                        dialog.minimize()
                        assert not dialog.isVisible() and active.isChecked()
                        active.click()
                        assert window.job_processor is worker
                        assert window.job_progress_dialog is dialog
                        assert dialog.isVisible() and active.isChecked()
                        dialog.showMinimized()
                        app.processEvents()
                        assert dialog.isMinimized() and active.isChecked()
                        active.click()
                        dialog.reject()
                        assert not dialog.isVisible() and active.isChecked()
                        active.click()
                        if not selected and outcome == "success":
                            dialog.grab().save(str(Path(os.environ["TEMP"]) / "visomaster-job-progress.png"))
                        if outcome in ("stop", "cancel"):
                            button = dialog.stop_button if outcome == "stop" else dialog.cancel_button
                            button.click()
                            assert worker.stop_requested_event.is_set() == (outcome == "stop")
                            assert worker.cancel_requested_event.is_set() == (outcome == "cancel")
                            assert not button.isEnabled()
                            assert not window.buttonStopProcessing.isEnabled()
                        else:
                            dialog.minimize()
                            for index, name in enumerate(worker.jobs, 1):
                                wait_for(lambda: dialog.current_index == index)
                                assert not dialog.isVisible()
                                assert active.isChecked()
                                assert active.text().endswith(f"({index}/{len(worker.jobs)})")
                                assert dialog.current_job_name == name
                                gates[name].set()
                        wait_for(lambda: window.job_progress_dialog is None)
                        expected_title = {"stop": "Job Processing Stopped", "cancel": "Job Processing Cancelled", "success": "Job Processing Complete"}[outcome]
                        assert expected_title in reports
                    assert worker.isFinished()
                    assert len(summaries) == 1
                    assert summaries[0].startswith("Process Selected" if selected else "Process All")
                    total = 1 if selected else 2
                    assert f"Queued: {total}" in summaries[0]
                    assert f"Completed: {total if outcome == 'success' else 0}" in summaries[0]
                    assert "Failed: 0" in summaries[0]
                    assert "Skipped: 0" in summaries[0]
                    assert f"Stopped: {int(outcome == 'stop')}" in summaries[0]
                    assert f"Cancelled: {int(outcome == 'cancel')}" in summaries[0]
                    remaining = total if outcome == "load_failure" else total - 1 if outcome in ("stop", "cancel") else 0
                    assert f"Not started: {remaining}" in summaries[0]
                    assert restored == [True]
                    assert not active.isChecked() and not active.isCheckable()
                    assert window.buttonProcessAll.text() == "Process All"
                    assert window.buttonProcessSelected.text() == "Process Selected"
                    assert not window.buttonStopProcessing.isEnabled()
                    assert window.job_processing_button is None
                    assert window.batch_progress_dialog is batch_dialog
                    assert window.is_batch_processing is False
                window.close()
                window.deleteLater()
                app.processEvents()
        # Preflight errors are skipped, not double-counted as failed jobs.
        # A stopped job is separate from jobs never reached in the queue.
        for cancelled in (False, True):
            dialog = JobProgressDialog(None, {})
            dialog.started_job_names = {"Done", "Active"}
            dialog.completed_job_names = {"Done"}
            dialog.job_failed("Skipped", "Missing media")
            if not cancelled:
                dialog.job_failed("Active", "Recording failed")
            processor = SimpleNamespace(
                jobs=["Done", "Active", "Skipped", "Pending"],
                skipped_jobs=["Skipped: Missing media"],
                batch_cancelled=cancelled, batch_stopped=False, batch_succeeded=False,
                completed_dir=root / "completed",
            )
            dialog.finish()
            def check_counts(box):
                summary = box.findChild(QtWidgets.QLabel).text()
                details = box.findChild(QtWidgets.QPlainTextEdit).toPlainText()
                assert "Queued: 4" in summary
                assert "Completed: 1" in summary
                assert f"Failed: {0 if cancelled else 1}" in summary
                assert "Skipped: 1" in summary
                assert "Stopped: 0" in summary
                assert f"Cancelled: {int(cancelled)}" in summary
                assert "Not started: 1" in summary
                assert "Skipped: Missing media" in details
                assert "Completed job files:" in details
                return QtWidgets.QDialog.Accepted
            with patch.object(QtWidgets.QDialog, "exec", check_counts):
                dialog.show_result(processor, "Process All")
            dialog.deleteLater()
        print("PASS both job commands: progress, metadata, minimize, reopen, success, cancel, load failure, isolation")
    ''')
    result = subprocess.run(
        [sys.executable, "-u", "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "PASS both job commands" in result.stdout
