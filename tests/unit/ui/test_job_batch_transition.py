"""Real Qt job transitions without GPU inference or workspace asset loading."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import pytest


def test_job_transition_and_final_report(tmp_path):
    script = textwrap.dedent('''
        from contextlib import ExitStack
        from pathlib import Path
        import sys
        import time
        from unittest.mock import MagicMock, patch
        from PySide6 import QtCore, QtWidgets, QtTest
        from app.ui.widgets.actions import job_manager_actions as actions
        from app.ui.widgets import job_progress_dialog
        from app.ui.widgets.job_list_widgets import JobDataRole as Role

        app = QtWidgets.QApplication([])
        root = Path(sys.argv[1])
        class Video(QtCore.QObject):
            processing_started_signal = QtCore.Signal()
            processing_stopped_signal = QtCore.Signal()
            processing_heartbeat_signal = QtCore.Signal()
            frame_processed_signal = QtCore.Signal()

        for fail_second in (False, True):
            window = QtWidgets.QMainWindow()
            window.project_root_path = root / str(fail_second)
            jobs = window.project_root_path / "jobs"
            jobs.mkdir(parents=True)
            window.video_processor = Video(window)
            window.jobQueueList = QtWidgets.QListWidget(window)
            window.jobQueueList.setSortingEnabled(True)
            window.job_marker_pairs = []
            window.job_progress_dialog = None
            window.job_processing_button = None
            for name in ("buttonProcessAll", "buttonProcessSelected", "buttonStopProcessing", "loadJobButton", "deleteJobButton", "smartJobListButton"):
                setattr(window, name, QtWidgets.QPushButton(name, window))
            items = {}
            for name in ("A", "B", "C"):
                (jobs / f"{name}.json").write_text("{}")
                item = QtWidgets.QListWidgetItem(name)
                for role, value in ((Role.JobNameRole, name), (Role.FrameCountRole, 1),
                                    (Role.FrameRateRole, 0.0), (Role.EmbeddingNamesRole, [])):
                    item.setData(role, value)
                window.jobQueueList.addItem(item)
                items[name] = item
            window.jobQueueList.setCurrentItem(items["C"])
            events = []
            reports = []
            def analyze(worker):
                worker.job_data_list = [{"job_name_internal": name} for name in worker.jobs]
                return {}
            def assets(mw, data):
                events.append("assets")
                mw.job_processor.master_assets_loaded_event.set()
            def load(mw, data):
                name = data["job_name_internal"]
                events.append("load " + name)
                if name == "B":
                    assert events == ["assets", "load A", "clear", "load B"]
                    assert mw.jobQueueList.count() == 2
                    assert mw.jobQueueList.item(0) is items["B"]
                    assert mw.jobQueueList.currentItem() is items["C"]
                mw.job_processor.job_settings_loaded_event.set()
            def process(worker, name):
                if fail_second and name == "B":
                    worker.job_failed_signal.emit(name, "test processing failure")
                    return False
                return True
            def clear_faces(mw):
                assert mw._batch_update_in_progress is True
                events.append("clear")
            def restore(mw, snapshot):
                assert not mw.job_processor.isRunning()
                events.append("restore")
            def report(dialog):
                assert events[-1] == "restore"
                reports.append((dialog.windowTitle(), dialog.findChild(QtWidgets.QPlainTextEdit).toPlainText()))
                return QtWidgets.QDialog.Accepted
            def settings(namespace, parent):
                result = QtCore.QSettings(str(root / "settings.ini"), QtCore.QSettings.IniFormat, parent)
                result.beginGroup(namespace)
                return result
            with ExitStack() as stack:
                for target, name, value in (
                    (actions, "_serialize_job_data", MagicMock(return_value={"snapshot": True})),
                    (actions, "_restore_workspace_from_snapshot", restore),
                    (actions.JobProcessor, "_analyze_job_batch", analyze),
                    (actions.JobProcessor, "_trigger_and_wait_for_processing", process),
                    (actions, "load_master_assets", assets),
                    (actions, "load_job_settings", load),
                    (actions.card_actions, "clear_target_faces", clear_faces),
                    (actions.video_control_actions, "remove_all_markers", MagicMock()),
                    (job_progress_dialog, "settings_group", settings),
                    (QtWidgets.QDialog, "exec", report),
                ):
                    stack.enter_context(patch.object(target, name, value))
                full_refresh = stack.enter_context(patch.object(actions, "refresh_job_list"))
                critical = stack.enter_context(patch.object(actions.QMessageBox, "critical"))
                actions.start_job_processor(window, ["A", "B"])
                worker = window.job_processor
                deadline = time.monotonic() + 10
                while window.job_processor is not None and time.monotonic() < deadline:
                    QtTest.QTest.qWait(10)
                assert window.job_processor is None
                assert worker.wait(1000)
                assert events == (["assets", "load A", "clear", "load B", "restore"] if fail_second
                                  else ["assets", "load A", "clear", "load B", "clear", "restore"])
                assert len(reports) == 1
                assert reports[0][0] == ("Job Processing Failed" if fail_second else "Job Processing Complete")
                assert ("B: test processing failure" in reports[0][1]) == fail_second
                assert window.jobQueueList.count() == (2 if fail_second else 1)
                assert window.jobQueueList.currentItem() is items["C"]
                assert (jobs / "completed" / "A.json").is_file()
                assert (jobs / "completed" / "B.json").is_file() == (not fail_second)
                full_refresh.assert_not_called()
                critical.assert_not_called()
            window.close()
            window.deleteLater()
            app.processEvents()
    ''')
    result = subprocess.run(
        [sys.executable, "-u", "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr


def test_interruption_waits_for_ui_handoffs_before_restoring(tmp_path):
    script = textwrap.dedent('''
        from contextlib import ExitStack
        from pathlib import Path
        import sys
        import time
        from types import SimpleNamespace
        from unittest.mock import patch
        from PySide6 import QtCore, QtWidgets, QtTest
        from app.ui.widgets.actions import job_manager_actions as actions
        from app.ui.widgets import job_progress_dialog
        from app.ui.widgets.job_list_widgets import JobDataRole as Role

        app = QtWidgets.QApplication([])
        root = Path(sys.argv[1])

        class Video(QtCore.QObject):
            processing_started_signal = QtCore.Signal()
            processing_stopped_signal = QtCore.Signal()
            processing_heartbeat_signal = QtCore.Signal()
            frame_processed_signal = QtCore.Signal()
            recording = False
            is_processing_segments = False
            last_processing_error = None
            max_frame_number = 0
            next_frame_to_display = 0
            media_pipeline = SimpleNamespace(absolute_frames_processed=0)

            def stop_processing(self):
                self.recording = False
                button = self.parent().buttonMediaRecord
                button.blockSignals(True)
                button.setChecked(False)
                button.blockSignals(False)
                self.processing_stopped_signal.emit()

            def _finalize_default_style_recording(self):
                self.stop_processing()

        for phase in ("assets", "settings", "clear", "record", "settings_after_first", "record_after_first"):
            for command in ("cancel", "stop", "timeout"):
                handoff = phase.removesuffix("_after_first")
                window = QtWidgets.QMainWindow()
                window.project_root_path = root / f"{phase}-{command}"
                jobs = window.project_root_path / "jobs"
                jobs.mkdir(parents=True)
                window.video_processor = Video(window)
                window.jobQueueList = QtWidgets.QListWidget(window)
                window.job_marker_pairs = []
                window.job_progress_dialog = None
                window.job_processing_button = None
                for name in ("buttonProcessAll", "buttonProcessSelected", "buttonStopProcessing",
                             "loadJobButton", "deleteJobButton", "smartJobListButton", "buttonMediaRecord"):
                    setattr(window, name, QtWidgets.QPushButton(name, window))
                window.buttonMediaRecord.setCheckable(True)
                for name in ("A", "B"):
                    (jobs / f"{name}.json").write_text("{}")
                    item = QtWidgets.QListWidgetItem(name)
                    for role, value in ((Role.JobNameRole, name), (Role.FrameCountRole, 1),
                                        (Role.FrameRateRole, 0.0), (Role.EmbeddingNamesRole, [])):
                        item.setData(role, value)
                    window.jobQueueList.addItem(item)
                events = []
                window.scope = "original"

                def interrupt_inside_handoff(name):
                    assert QtCore.QThread.currentThread() == app.thread()
                    events.append("enter " + name)
                    window.scope = "job"
                    if handoff == name and (
                        not phase.endswith("_after_first") or window.job_progress_dialog.current_index == 2
                    ):
                        if command != "timeout":
                            button = (window.job_progress_dialog.cancel_button if command == "cancel"
                                      else window.job_progress_dialog.stop_button)
                            QtCore.QTimer.singleShot(0, button.click)
                        QtTest.QTest.qWait(120)
                        assert window.job_processor.ui_operation_depth > 0
                        if command == "timeout":
                            assert window.job_processor.wait(1000)
                            app.processEvents()
                            assert errors and "Timeout" in errors[0][1]
                        assert window.scope == "job"
                        assert "restore" not in events
                    events.append("exit " + name)

                def analyze(worker):
                    worker.job_data_list = [{"job_name_internal": name} for name in worker.jobs]
                    return {}

                def assets(mw, data):
                    interrupt_inside_handoff("assets")
                    mw.job_processor.master_assets_loaded_event.set()

                def settings(mw, data):
                    interrupt_inside_handoff("settings")
                    mw.job_processor.job_settings_loaded_event.set()

                def clear(mw):
                    interrupt_inside_handoff("clear")
                    mw.job_processor.job_settings_cleared_event.set()

                def record(checked):
                    if not checked:
                        return
                    window.video_processor.recording = True
                    if not (command == "timeout" and handoff == "record" and (
                        not phase.endswith("_after_first") or window.job_progress_dialog.current_index == 2
                    )):
                        window.video_processor.processing_started_signal.emit()
                    interrupt_inside_handoff("record")
                    if handoff != "record" or (
                        phase.endswith("_after_first") and window.job_progress_dialog.current_index == 1
                    ):
                        window.video_processor.stop_processing()

                def restore(mw, snapshot):
                    assert events[-1] == "exit " + handoff
                    assert snapshot == {"scope": "original"}
                    events.append("restore")
                    mw.scope = snapshot["scope"]

                def report(dialog, worker, command):
                    assert window.scope == "original"
                    events.append("report")

                def isolated_settings(namespace, parent):
                    result = QtCore.QSettings(str(root / "settings.ini"), QtCore.QSettings.IniFormat, parent)
                    result.beginGroup(namespace)
                    return result

                window.buttonMediaRecord.toggled.connect(record)
                with ExitStack() as stack:
                    for target, name, value in (
                        (actions, "_serialize_job_data", lambda mw: {"scope": mw.scope}),
                        (actions, "_restore_workspace_from_snapshot", restore),
                        (actions.JobProcessor, "_analyze_job_batch", analyze),
                        (actions, "load_master_assets", assets),
                        (actions, "load_job_settings", settings),
                        (actions, "clear_job_settings", clear),
                        (job_progress_dialog.JobProgressDialog, "show_result", report),
                        (job_progress_dialog, "settings_group", isolated_settings),
                    ):
                        stack.enter_context(patch.object(target, name, value))
                    if command == "timeout":
                        for name in ("MASTER_ASSETS_LOAD_TIMEOUT", "JOB_SETTINGS_LOAD_TIMEOUT",
                                     "JOB_SETTINGS_CLEAR_TIMEOUT", "JOB_START_TIMEOUT"):
                            stack.enter_context(patch.object(actions.JobProcessor, name, 0.03))
                    actions.start_job_processor(window, ["A", "B"])
                    worker = window.job_processor
                    errors = []
                    worker.job_failed_signal.connect(lambda name, error: errors.append((name, error)))
                    deadline = time.monotonic() + 5
                    while window.job_processor is not None and time.monotonic() < deadline:
                        QtTest.QTest.qWait(10)
                    assert window.job_processor is None, (phase, command, events)
                    assert worker.wait(1000)
                    assert events[-2:] == ["restore", "report"]
                    assert window.scope == "original"
                    assert window.workspace_snapshot_before_batch is None
                    assert worker.batch_cancelled == (command == "cancel")
                    assert worker.batch_stopped == (command == "stop")
                    assert (jobs / "B.json").is_file()
                window.close()
                window.deleteLater()
                app.processEvents()

        # Cancel/Stop after a record-start command is queued, before GUI delivery.
        import threading
        class RecordingWorker(actions.JobProcessor):
            def run(self):
                self.entered.set()
                self.result = self._trigger_and_wait_for_processing("A")

        for command in ("cancel", "stop"):
            window = QtWidgets.QMainWindow()
            window.project_root_path = root / ("queued-record-" + command)
            window.video_processor = Video(window)
            window.buttonMediaRecord = QtWidgets.QPushButton(window)
            window.buttonMediaRecord.setCheckable(True)
            toggles = []
            window.buttonMediaRecord.toggled.connect(toggles.append)
            worker = RecordingWorker(window, jobs_to_process=[])
            worker.entered = threading.Event()
            worker.start()
            assert worker.entered.wait(2)
            if command == "cancel":
                worker.request_cancel()
            else:
                worker.request_stop()
            deadline = time.monotonic() + 2
            while worker.isRunning() and time.monotonic() < deadline:
                QtTest.QTest.qWait(10)
            assert worker.wait(1000)
            assert worker.result is False
            assert toggles == []
            assert not hasattr(window, "job_manager_initiated_record")
            window.close()
    ''')
    result = subprocess.run(
        [sys.executable, "-u", "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr


@pytest.mark.parametrize("segmented", [False, True])
def test_active_queue_controls_and_empty_output(tmp_path, segmented):
    script = textwrap.dedent('''
        from contextlib import ExitStack
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch
        import sys
        import time
        from PySide6 import QtCore, QtWidgets, QtTest
        from app.ui.widgets.actions import job_manager_actions as actions
        from app.ui.widgets import job_progress_dialog
        from app.ui.widgets.job_list_widgets import JobDataRole as Role
        from app.processors.video_processor import VideoProcessor
        import app.processors.video_processor as video_module

        app = QtWidgets.QApplication([])
        root = Path(sys.argv[1])
        segmented = sys.argv[2] == "True"
        empty_error = "No valid recorded segments were found, so no video file was saved."

        class Video(QtCore.QObject):
            processing_started_signal = QtCore.Signal()
            processing_stopped_signal = QtCore.Signal()
            processing_heartbeat_signal = QtCore.Signal()
            frame_processed_signal = QtCore.Signal()
            is_processing_segments = False
            recording = False
            processing = False
            last_processing_error = None
            max_frame_number = 1
            next_frame_to_display = 0
            media_pipeline = SimpleNamespace(absolute_frames_processed=0)
            file_type = "video"
            media_path = "input.mp4"
            def start_multi_segment_recording(self, segments, triggered_by_job_manager=False):
                VideoProcessor.start_multi_segment_recording(self, segments, triggered_by_job_manager)

            def process_video(self):
                self.last_processing_error = None
                self.processing = True
                self.parent().job_manager_initiated_record = False
                begin_processing()

            def process_next_segment(self):
                assert self.last_processing_error is None
                assert not self._fatal_processing_error_latched
                begin_processing()

            def stop_processing(self):
                events.append("stop processing")
                self.recording = self.processing = False
                self.is_processing_segments = False
                button = self.parent().buttonMediaRecord
                button.blockSignals(True)
                button.setChecked(False)
                button.blockSignals(False)
                self.processing_stopped_signal.emit()

            def _finalize_default_style_recording(self):
                events.append("save")
                if mode == "stop_preroll_slow":
                    QtTest.QTest.qWait(450)
                self.stop_processing()

            def finalize_segment_concatenation(self):
                events.append("save")
                if mode == "stop_preroll_slow":
                    QtTest.QTest.qWait(450)
                self.stop_processing()

        for mode in ("stop", "cancel", "skip_discard", "skip_save", "stop_after",
                     "skip_stop_after", "empty", "stop_empty", "stop_preroll", "stop_preroll_slow", "cancel_preroll", "timeout"):
            window = QtWidgets.QMainWindow()
            window.project_root_path = root / mode
            jobs = window.project_root_path / "jobs"
            jobs.mkdir(parents=True)
            window.video_processor = Video(window)
            window.video_processor.main_window = window
            window.video_processor.media_capture = MagicMock()
            window.video_processor.last_processing_error = empty_error
            window.video_processor._fatal_processing_error_latched = True
            window.jobQueueList = QtWidgets.QListWidget(window)
            window.job_marker_pairs = []
            window.job_progress_dialog = None
            window.job_processing_button = None
            window.is_batch_processing = False
            window.control = {"OutputMediaFolder": str(root), "KeepControlsToggle": True,
                              "ConfirmBeforeStoppingRecordingToggle": True}
            window.videoSeekSlider = QtWidgets.QSlider(window)
            window.buttonMediaPlay = QtWidgets.QPushButton(window)
            for name in ("buttonProcessAll", "buttonProcessSelected", "buttonStopProcessing",
                         "loadJobButton", "deleteJobButton", "smartJobListButton", "buttonMediaRecord"):
                setattr(window, name, QtWidgets.QPushButton(name, window))
            window.buttonMediaRecord.setCheckable(True)
            for name in ("A", "B"):
                (jobs / f"{name}.json").write_text("{}")
                item = QtWidgets.QListWidgetItem(name)
                for role, value in ((Role.JobNameRole, name), (Role.FrameCountRole, 1),
                                    (Role.FrameRateRole, 0.0), (Role.EmbeddingNamesRole, [])):
                    item.setData(role, value)
                window.jobQueueList.addItem(item)
            events = []
            errors = []
            prompts = MagicMock(return_value=QtWidgets.QMessageBox.No)

            def analyze(worker):
                worker.job_data_list = [{"job_name_internal": name} for name in worker.jobs]
                return {}

            def settings(mw, data):
                events.append("load " + data["job_name_internal"])
                mw.job_marker_pairs = [(0, 1), (3, 4)] if segmented else []
                mw.job_processor.job_settings_loaded_event.set()

            def action():
                dialog = window.job_progress_dialog
                video = window.video_processor
                if mode in ("empty", "stop_empty"):
                    video.last_processing_error = empty_error
                if mode in ("stop", "stop_empty", "stop_preroll", "stop_preroll_slow"):
                    dialog.stop_button.click()
                elif mode in ("cancel", "cancel_preroll"):
                    dialog.cancel_button.click()
                elif mode.startswith("skip"):
                    dialog.stop_after_completion_checkbox.setChecked(mode == "skip_stop_after")
                    dialog.save_partial_on_skip_checkbox.setChecked(mode == "skip_save")
                    dialog.skip_button.click()
                elif mode == "empty":
                    video.stop_processing()
                else:
                    dialog.stop_after_completion_checkbox.setChecked(True)
                    if segmented:
                        video.finalize_segment_concatenation()
                    else:
                        video._finalize_default_style_recording()

            def begin_processing():
                video = window.video_processor
                if mode not in ("stop_preroll", "stop_preroll_slow", "cancel_preroll", "timeout"):
                    video.processing_started_signal.emit()
                if mode != "timeout":
                    finish = video.finalize_segment_concatenation if segmented else video._finalize_default_style_recording
                    QtCore.QTimer.singleShot(30, action if window.job_processor.current_job_name == "A" else finish)

            def isolated_settings(namespace, parent):
                return QtCore.QSettings(str(root / "settings.ini"), QtCore.QSettings.IniFormat, parent)

            window.buttonMediaRecord.toggled.connect(
                lambda checked: actions.video_control_actions.record_video(window, checked)
            )
            with ExitStack() as stack:
                for target, name, value in (
                    (actions, "_serialize_job_data", lambda mw: {"original": True}),
                    (actions, "_restore_workspace_from_snapshot", lambda *args: events.append("restore")),
                    (actions.JobProcessor, "_analyze_job_batch", analyze),
                    (actions, "load_master_assets", lambda mw, data: mw.job_processor.master_assets_loaded_event.set()),
                    (actions, "load_job_settings", settings),
                    (actions, "clear_job_settings", lambda mw: mw.job_processor.job_settings_cleared_event.set()),
                    (job_progress_dialog.JobProgressDialog, "show_result", lambda *args: events.append("report")),
                    (job_progress_dialog, "settings_group", isolated_settings),
                    (actions.video_control_actions.misc_helpers, "is_ffmpeg_in_path", lambda: True),
                    (actions.video_control_actions, "_disable_compare_preview_modes_for_recording", lambda mw: None),
                    (actions.video_control_actions, "set_record_button_icon_to_stop", lambda mw: None),
                    (actions.video_control_actions, "resolve_output_folder", lambda *args: str(root)),
                    (video_module.os, "getcwd", lambda: str(root)),
                    (QtWidgets.QMessageBox, "exec", prompts),
                    (actions.JobProcessor, "JOB_START_TIMEOUT", 0.3),
                ):
                    stack.enter_context(patch.object(target, name, value))
                actions.start_job_processor(window, ["A", "B"])
                worker = window.job_processor
                worker.job_failed_signal.connect(lambda name, error: errors.append((name, error)))
                deadline = time.monotonic() + 6
                while window.job_processor is not None and time.monotonic() < deadline:
                    QtTest.QTest.qWait(10)
                assert window.job_processor is None, (mode, events)
                assert worker.wait(1000)
                assert events[-2:] == ["restore", "report"]
                assert events.count("restore") == 1
                completed = {path.stem for path in (jobs / "completed").glob("*.json")}
                assert completed == ({"B"} if mode in ("skip_discard", "skip_save")
                                     else {"A"} if mode == "stop_after" else set()), (mode, completed)
                assert ("load B" in events) == (mode in ("skip_discard", "skip_save"))
                assert bool(worker.skipped_jobs) == mode.startswith("skip")
                assert worker.batch_cancelled == (mode in ("cancel", "cancel_preroll"))
                assert worker.batch_stopped == (mode in ("stop", "stop_empty", "stop_after", "skip_stop_after", "stop_preroll", "stop_preroll_slow"))
                assert bool(errors) == (mode in ("empty", "timeout")), (mode, errors)
                if mode == "empty":
                    assert errors == [("A", empty_error)]
                if mode == "timeout":
                    assert errors == [("A", "Timeout waiting for processing to start signal.")]
                expected_saves = 2 if mode == "skip_save" else 1 if mode in (
                    "stop", "stop_empty", "skip_discard", "stop_after", "stop_preroll", "stop_preroll_slow"
                ) else 0
                assert events.count("save") == expected_saves, (mode, events)
                prompts.assert_not_called()
            window.close()
            window.deleteLater()
            app.processEvents()
    ''')
    result = subprocess.run(
        [sys.executable, "-u", "-c", script, str(tmp_path), str(segmented)],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
