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
        initial = job_progress_dialog.JobProgressDialog(None, {})
        assert not initial.suppress_notifications_checkbox.isChecked()
        assert not initial.stop_after_processing_checkbox.isChecked()
        assert initial.stop_after_processing_spinbox.value() == 100
        assert not initial.stop_after_processing_spinbox.isEnabled()
        initial.finish()
        for checked in (True, False):
            settings.setValue("stop_after_completion_checkbox", True)
            dialog = job_progress_dialog.JobProgressDialog(None, {})
            assert not dialog.stop_after_completion_checkbox.isChecked()
            assert not settings.contains("stop_after_completion_checkbox")
            dialog.stop_after_completion_checkbox.setChecked(True)
            assert not settings.contains("stop_after_completion_checkbox")
            dialog.save_partial_on_skip_checkbox.setChecked(not checked)
            dialog.save_partial_on_skip_checkbox.setChecked(checked)
            dialog.suppress_notifications_checkbox.setChecked(checked)
            dialog.stop_after_processing_checkbox.setChecked(checked)
            dialog.stop_after_processing_spinbox.setValue(25)
            assert dialog.stop_after_processing_spinbox.isEnabled() == checked
            dialog.show()
            app.processEvents()
            assert dialog.save_partial_on_skip_checkbox.geometry().bottom() < dialog.stop_after_processing_row.y()
            assert dialog.stop_after_processing_row.geometry().bottom() < dialog.suppress_notifications_checkbox.y()
            dialog.finish()
            reopened = job_progress_dialog.JobProgressDialog(None, {})
            assert not reopened.stop_after_completion_checkbox.isChecked()
            assert reopened.save_partial_on_skip_checkbox.isChecked() == checked
            assert reopened.suppress_notifications_checkbox.isChecked() == checked
            assert reopened.stop_after_processing_checkbox.isChecked() == checked
            assert reopened.stop_after_processing_spinbox.value() == 25
            assert reopened.stop_after_processing_spinbox.isEnabled() == checked
            reopened.stopping()
            assert not reopened.stop_after_processing_row.isEnabled()
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
            max_frame_number = 49
            next_frame_to_display = 0
            media_pipeline = SimpleNamespace(absolute_frames_processed=0)
            def stop_processing(self):
                self.processing_stopped_signal.emit()

        def wait_for(predicate):
            deadline = time.monotonic() + 8
            while not predicate() and time.monotonic() < deadline:
                QtTest.QTest.qWait(10)
            assert predicate()

        for selected, similar in ((False, False), (True, False), (False, True), (True, True)):
            for outcome in ("success", "stop", "cancel", "load_failure"):
                window = QtWidgets.QMainWindow()
                window.project_root_path = root / f"{selected}-{similar}-{outcome}"
                jobs = window.project_root_path / "jobs"
                jobs.mkdir(parents=True)
                window.video_processor = Video(window)
                window.job_processor = None
                window.job_progress_dialog = None
                window.job_processing_button = None
                window.job_similarity_dialog = None
                window.job_similarity_button = None
                window.batch_progress_dialog = object()
                batch_dialog = window.batch_progress_dialog
                window.is_batch_processing = False
                window.jobsManagerSearchBox = QtWidgets.QLineEdit(window)
                window.jobsManagerSearchResetButton = QtWidgets.QPushButton(window)
                window.jobQueueList = QtWidgets.QListWidget(window)
                window.jobListLabelTemplateComboBox = QtWidgets.QComboBox(window)
                window.jobListLabelTemplateComboBox.addItem("{job_name}")
                for attr, label in (
                    ("buttonProcessAll", "Process All"),
                    ("buttonProcessSelected", "Process Selected"),
                    ("buttonProcessSelectedSimilar", "Process Similar (0)"),
                    ("buttonProcessAllSimilar", "Process Similar"),
                    ("buttonStopProcessing", "Stop Processing"),
                    ("addJobButton", "Save Job"), ("loadJobButton", "Load Job"),
                    ("deleteJobButton", "Delete Job"), ("refreshJobListButton", "Refresh"),
                    ("checkNewJobListButton", "Check for New"),
                    ("smartJobListButton", "S.M.A.R.T"),
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

                original_show_result = JobProgressDialog.show_result
                def capture_report(box, processor, command):
                    assert restored == [True]
                    original_show_result(box, processor, command)
                    assert box.isVisible()
                    assert box.is_finished
                    assert not box.runtime_timer.isActive()
                    assert box.cancel_button.text() == "Close"
                    assert box.cancel_button.isEnabled()
                    assert not box.stop_button.isEnabled()
                    assert not box.skip_button.isEnabled()
                    assert "Workspace restoration finished" in box.status_label.text()
                    summary = command + "\\n" + "\\n".join(
                        f"{field} {box.report_labels[field][1].text()}"
                        for field in ("Completed:", "Failed:", "Skipped:")
                    ) + box.runtime_label.text()
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
                    window.video_processor.max_frame_number = 49 if name == "A" else 0
                    window.video_processor.media_pipeline.absolute_frames_processed = 0
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
                     patch.object(JobProgressDialog, "show_result", capture_report), \
                     patch.object(actions.QMessageBox, "critical", side_effect=lambda *args: reports.append(args[1])):
                    active = window.buttonProcessSelected if selected or similar else window.buttonProcessAll
                    other = window.buttonProcessAll if selected or similar else window.buttonProcessSelected
                    if similar:
                        from app.ui.widgets import job_similarity_dialog
                        class ReviewDialog(QtWidgets.QDialog):
                            def __init__(self, parent, jobs):
                                super().__init__(parent)
                                self.jobs_to_process = jobs
                            def run(self):
                                assert window.job_similarity_dialog is self
                                assert window.job_processing_button is None
                                return QtWidgets.QDialog.Accepted
                        origin = window.buttonProcessSelectedSimilar if selected else window.buttonProcessAllSimilar
                        with patch.object(job_similarity_dialog, "JobSimilarityDialog", ReviewDialog):
                            origin.click()
                        assert window.job_similarity_dialog is None
                        assert window.job_similarity_button is None
                        assert not origin.isChecked() and not origin.isCheckable()
                    else:
                        active.click()
                    worker = window.job_processor
                    dialog = window.job_progress_dialog
                    assert worker.jobs == (["B"] if selected else ["A", "B"])
                    assert active.isEnabled() and not other.isEnabled()
                    assert window.job_processing_button is active
                    assert not window.buttonProcessAllSimilar.isEnabled()
                    assert not window.buttonProcessSelectedSimilar.isEnabled()
                    assert not window.loadJobButton.isEnabled()
                    assert not window.deleteJobButton.isEnabled()
                    assert window.buttonStopProcessing.isEnabled()
                    assert not window.smartJobListButton.isEnabled()
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
                        window.buttonProcessSelectedSimilar.click()
                        window.buttonProcessAllSimilar.click()
                        actions.prepare_similar_jobs(window, selected_only=True)
                        assert not dialog.isVisible()
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
                    assert summaries[0].startswith("Process Selected" if selected or similar else "Process All")
                    total = 1 if selected else 2
                    assert f"Completed: {total if outcome == 'success' else 0}" in summaries[0]
                    assert "Failed: 0" in summaries[0]
                    assert "Skipped: 0" in summaries[0]
                    assert restored == [True]
                    assert not active.isChecked() and not active.isCheckable()
                    assert window.buttonProcessAll.text() == "Process All"
                    assert window.buttonProcessSelected.text() == f"Process ({len(window.jobQueueList.selectedItems())})"
                    assert not window.buttonStopProcessing.isEnabled()
                    assert window.smartJobListButton.isEnabled()
                    assert window.buttonProcessSelectedSimilar.text() == f"Process Similar ({len(window.jobQueueList.selectedItems())})"
                    assert window.buttonProcessAllSimilar.text() == "Process Similar"
                    assert window.job_processing_button is None
                    assert window.batch_progress_dialog is batch_dialog
                    assert window.is_batch_processing is False
                    cancelled_signals = QtTest.QSignalSpy(dialog.cancelRequested)
                    dialog.details_button.click()
                    assert dialog.detail_text.isVisible()
                    dialog.cancel_button.click()
                    assert cancelled_signals.count() == 0
                    assert not dialog.isVisible()
                window.close()
                window.deleteLater()
                app.processEvents()
        # Preflight errors are skipped, not double-counted as failed jobs.
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
                summary = "\\n".join(
                    f"{field} {box.report_labels[field][1].text()}"
                    for field in ("Completed:", "Failed:", "Skipped:")
                )
                details = box.findChild(QtWidgets.QPlainTextEdit).toPlainText()
                assert "Completed: 1" in summary
                assert f"Failed: {0 if cancelled else 1}" in summary
                assert "Skipped: 1" in summary
                assert "Skipped: Missing media" in details
                assert "Completed job files:" in details
                return QtWidgets.QDialog.Accepted
            dialog.show_result(processor, "Process All")
            check_counts(dialog)
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


def test_job_progress_live_counts(tmp_path):
    script = textwrap.dedent('''
        import sys
        from PySide6 import QtCore, QtWidgets
        from app.ui.widgets import job_progress_dialog
        from app.ui.widgets.job_list_widgets import JobDataRole

        app = QtWidgets.QApplication([])
        job_progress_dialog.settings_group = lambda namespace, parent: QtCore.QSettings(
            sys.argv[1], QtCore.QSettings.IniFormat, parent
        )
        items = {}
        for name in ("Done", "Skipped", "Failed", "Pending", "Invalid"):
            item = QtWidgets.QListWidgetItem(name)
            item.setData(JobDataRole.FrameCountRole, 50)
            item.setData(JobDataRole.FrameRateRole, 25.0)
            item.setData(JobDataRole.EmbeddingNamesRole, [])
            items[name] = item
        dialog = job_progress_dialog.JobProgressDialog(None, items)
        def count(field):
            return int(dialog.report_labels[field + ":"][1].text())

        assert all(field not in dialog.report_labels for field in ("Queued:", "Stopped:", "Cancelled:", "Not started:"))
        dialog.job_failed("Invalid", "Missing job file")
        assert count("Failed") == 0
        dialog.queue_ready(4, 1)
        assert count("Skipped") == 1
        dialog.job_started("Done", 1)
        dialog.job_completed("Done")
        assert count("Completed") == 1
        dialog.job_started("Skipped", 2)
        dialog.job_skipped("Skipped")
        assert count("Skipped") == 2
        dialog.job_started("Failed", 3)
        dialog.job_failed("Failed", "Recording failed")
        assert count("Failed") == 1
        assert count("Completed") == 1
        assert not dialog.is_finished
        dialog.finish()
    ''')
    result = subprocess.run(
        [sys.executable, "-u", "-c", script, str(tmp_path / "counts.ini")],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_job_progress_eta(tmp_path):
    script = textwrap.dedent('''
        import sys
        from unittest.mock import MagicMock
        from PySide6 import QtCore, QtWidgets
        from app.ui.widgets import job_progress_dialog
        from app.ui.widgets.job_list_widgets import JobDataRole

        app = QtWidgets.QApplication([])
        def isolated_settings(namespace, parent):
            return QtCore.QSettings(sys.argv[1], QtCore.QSettings.IniFormat, parent)
        job_progress_dialog.settings_group = isolated_settings
        item = QtWidgets.QListWidgetItem("A")
        item.setData(JobDataRole.FrameCountRole, 36620)
        item.setData(JobDataRole.FrameRateRole, 25.0)
        item.setData(JobDataRole.EmbeddingNamesRole, [])
        window = QtWidgets.QMainWindow()
        window.video_processor = MagicMock(
            is_processing_segments=False, max_frame_number=36619, next_frame_to_display=0,
            media_pipeline=MagicMock(absolute_frames_processed=20),
        )
        dialog = job_progress_dialog.JobProgressDialog(window, {"A": item})
        dialog.job_started("A", 1)
        dialog.processing_started()
        assert dialog.eta_label.text() == "ETA: --:--:--"
        clock = MagicMock(isValid=MagicMock(return_value=True),
                         nsecsElapsed=MagicMock(return_value=2_000_000_000))
        dialog.processing_rate_clock = clock
        for _ in range(20):
            dialog.frame_processed()
        dialog.update_runtime()
        assert dialog.report_labels["f/s:"][1].text() == "10.00"
        assert dialog.eta_label.text() == "ETA: 01:01:00"
        dialog.update_runtime()
        assert dialog.eta_label.text() == "ETA: --:--:--"
        item.setData(JobDataRole.FrameCountRole, 1)
        window.video_processor.max_frame_number = 0
        window.video_processor.media_pipeline.absolute_frames_processed = 1
        dialog.job_started("A", 1)
        dialog.processing_started()
        dialog.frame_processed()
        dialog.update_runtime()
        assert dialog.report_labels["Item progress:"][1].text() == "100.0%"
        assert dialog.eta_label.text() == "ETA: 00:00:00"
        dialog.update_runtime()
        assert dialog.eta_label.text() == "ETA: 00:00:00"
        dialog.processing_stopped()
        assert dialog.eta_label.text() == "ETA: 00:00:00"
        item.setData(JobDataRole.FrameCountRole, 50)
        dialog.job_started("A", 1)
        assert dialog.report_labels["Item progress:"][1].text() == "0.0%"
        assert dialog.eta_label.text() == "ETA: --:--:--"
        # Output range, rather than source metadata, controls the estimate.
        window.video_processor.max_frame_number = 29
        window.video_processor.next_frame_to_display = 10
        window.video_processor.media_pipeline.absolute_frames_processed = 10
        dialog.processing_started()
        dialog.frame_processed()
        dialog.update_runtime()
        assert dialog.report_labels["Item progress:"][1].text() == "50.0%"
        assert dialog.eta_label.text() == "ETA: 00:00:20"
        # Both ends of each recorded segment are included.
        window.video_processor.is_processing_segments = True
        window.video_processor.segments_to_process = [(10, 19), (30, 39)]
        dialog.processing_started()
        dialog.frame_processed()
        dialog.update_runtime()
        assert dialog.report_labels["Item progress:"][1].text() == "50.0%"
        assert dialog.eta_label.text() == "ETA: 00:00:20"
        dialog.processing_stopped()
        assert dialog.eta_label.text() == "ETA: --:--:--"
        dialog.job_completed("A")
        assert dialog.report_labels["Item progress:"][1].text() == "100.0%"
        assert dialog.eta_label.text() == "ETA: 00:00:00"
        dialog.show()
        app.processEvents()
        progress = dialog.report_labels["Item progress:"][1]
        assert progress.geometry().right() < dialog.eta_label.x()
        assert progress.geometry().center().y() == dialog.eta_label.geometry().center().y()
        assert dialog.eta_label.geometry().right() < dialog.width()
        for frames, fps in ((None, 25.0), (50, None), (None, None)):
            item.setData(JobDataRole.FrameCountRole, frames)
            item.setData(JobDataRole.FrameRateRole, fps)
            dialog.job_started("A", 1)
            assert dialog.report_labels["Frames:"][0].isHidden() == (frames is None)
            assert dialog.report_labels["Frame rate:"][0].isHidden() == (fps is None)
            assert dialog.report_labels["Length:"][0].isHidden()
            dialog.processing_started()
            dialog.frame_processed()
            dialog.update_runtime()
            assert dialog.report_labels["Item progress:"][1].text() == "50.0%"
            dialog.processing_stopped()
        dialog.finish()
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


def test_job_notification_suppression(tmp_path):
    script = textwrap.dedent('''
        import ast
        import sys
        from functools import wraps
        from types import SimpleNamespace
        from pathlib import Path
        from unittest.mock import patch
        from PySide6 import QtCore, QtWidgets
        from app.ui.widgets import job_progress_dialog

        app = QtWidgets.QApplication([])
        def isolated_settings(namespace, parent):
            return QtCore.QSettings(sys.argv[1], QtCore.QSettings.IniFormat, parent)
        job_progress_dialog.settings_group = isolated_settings
        source = Path("app/ui/widgets/actions/common_actions.py")
        function = next(node for node in ast.parse(source.read_text(encoding="utf-8")).body
                        if isinstance(node, ast.FunctionDef) and node.name == "suppress_batch_notifications")
        namespace = dict(QtWidgets=QtWidgets, wraps=wraps)
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
        displayed = []
        display = namespace["suppress_batch_notifications"](lambda *args: displayed.append(True))
        parent = QtWidgets.QWidget()
        parent.is_batch_processing = False
        dialog = job_progress_dialog.JobProgressDialog(parent, {})
        display(parent)
        assert displayed == [True]
        dialog.suppress_notifications_checkbox.setChecked(True)
        dialog.minimize()
        display(parent)
        assert displayed == [True]
        with patch.object(QtWidgets.QDialog, "exec") as report:
            dialog.finish()
            dialog.show_result(SimpleNamespace(
                jobs=[], skipped_jobs=[], batch_cancelled=False, batch_stopped=False,
                batch_succeeded=True,
            ), "Process All")
            assert dialog.isVisible()
            assert dialog.report_labels["Completed:"][1].text() == "0"
            assert dialog.cancel_button.text() == "Close"
            report.assert_not_called()
        dialog.suppress_notifications_checkbox.setChecked(False)
        display(parent)
        assert displayed == [True, True]
        dialog.suppress_notifications_checkbox.setChecked(True)
        dialog.finish()
        display(parent)
        assert displayed == [True, True, True]
    ''')
    result = subprocess.run(
        [sys.executable, "-u", "-c", script, str(tmp_path / "notifications.ini")],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
