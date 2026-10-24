"""Queue decisions after job failures, without invoking GPU inference."""

import ast
import os
from pathlib import Path
import shutil
import threading
import json
from types import SimpleNamespace, MethodType
from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize("stop_on_error", [False, True])
@pytest.mark.parametrize("failure", ["render", "watchdog", "settings", "move"])
@pytest.mark.parametrize("interrupt", [None, "stop", "cancel", "after_current", "limit", "skip"])
def test_error_policy_preserves_queue_controls(tmp_path, stop_on_error, failure, interrupt):
    source = Path("app/ui/widgets/actions/job_manager_actions.py")
    cls = next(node for node in ast.parse(source.read_text(encoding="utf-8")).body
               if isinstance(node, ast.ClassDef) and node.name == "JobProcessor")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "run")
    namespace = {"os": os, "shutil": MagicMock()}
    namespace["shutil"].move.side_effect = shutil.move
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)
    worker = MagicMock()
    worker.jobs = ["A", "B", "C"]
    worker.jobs_dir = tmp_path
    worker.completed_dir = tmp_path / "completed"
    worker.completed_dir.mkdir()
    for name in worker.jobs:
        (tmp_path / f"{name}.json").write_text("{}")
    worker.job_data_list = [{"job_name_internal": name} for name in worker.jobs]
    worker.skipped_jobs = []
    worker.batch_stopped = False
    worker.processing_timed_out = False
    for name in ("stop_requested_event", "cancel_requested_event", "skip_requested_event",
                 "stop_after_current_event", "stop_on_job_errors_event", "render_limit_reached_event"):
        setattr(worker, name, threading.Event())
    if stop_on_error:
        worker.stop_on_job_errors_event.set()
    if interrupt == "after_current":
        worker.stop_after_current_event.set()
    worker.processing_limit = (interrupt == "limit", 1)
    worker.master_assets_loaded_event.wait.return_value = True
    worker.job_settings_loaded_event.wait.side_effect = [failure != "settings", True, True]
    worker.job_settings_cleared_event.wait.return_value = True
    processed = []
    cleared = []

    def load(data):
        if data["job_name_internal"] == "A":
            if interrupt in ("stop", "cancel"):
                getattr(worker, f"{interrupt}_requested_event").set()
            elif interrupt == "skip":
                worker.skip_requested_event.set()

    def process(name):
        processed.append(name)
        if name == "A" and failure in ("render", "watchdog"):
            worker.processing_timed_out = failure == "watchdog"
            worker.job_failed_signal.emit(name, "render failed")
            return False
        return True

    def move(src, dest):
        if Path(src).stem == "A" and failure == "move":
            raise OSError("move failed")
        shutil.move(src, dest)

    namespace["shutil"].move.side_effect = move
    worker.load_job_settings_signal.emit.side_effect = load
    worker._trigger_and_wait_for_processing.side_effect = process
    worker.clear_job_settings_signal.emit.side_effect = lambda: cleared.append(worker.current_job_name)
    namespace["run"](worker)

    stopped = stop_on_error or interrupt in ("stop", "cancel", "after_current")
    if interrupt == "skip":
        stopped = False  # An explicit skip takes precedence over stop-on-error.
    expected_completed = [] if stopped else (["B"] if interrupt == "limit" else ["B", "C"])
    assert [call.args[0] for call in worker.job_completed_signal.emit.call_args_list] == expected_completed
    assert (tmp_path / "A.json").exists()
    assert not (worker.completed_dir / "A.json").exists()
    for name in expected_completed:
        assert not (tmp_path / f"{name}.json").exists()
        assert (worker.completed_dir / f"{name}.json").exists()
    if not stopped:
        assert cleared[0] == "A"
        assert worker.job_skipped_signal.emit.call_args_list[0].args == ("A",)
    if interrupt not in ("stop", "cancel", "after_current", "limit"):
        assert worker.batch_succeeded == (interrupt == "skip" and failure == "move")
    if interrupt in ("limit", "after_current") and not stop_on_error:
        assert worker.batch_stopped is True


@pytest.mark.parametrize("save", [False, True])
@pytest.mark.parametrize("update", [False, True])
@pytest.mark.parametrize("segments", [False, True])
@pytest.mark.parametrize("frames", [0, 20])
def test_render_error_uses_manual_skip_options(tmp_path, save, update, segments, frames):
    source = Path("app/ui/widgets/actions/job_manager_actions.py")
    cls = next(node for node in ast.parse(source.read_text(encoding="utf-8")).body
               if isinstance(node, ast.ClassDef) and node.name == "JobProcessor")
    names = {"stop_job_recording", "request_skip", "request_skip_and_update", "_trigger_and_wait_for_processing"}
    methods = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    for method in methods:
        method.decorator_list = []
    namespace = {"json": json, "QMetaObject": MagicMock(), "Qt": MagicMock(), "time": MagicMock()}
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), namespace)
    video = MagicMock()
    video.is_processing_segments = segments
    video.recording = not segments
    video.processing = True
    video._used_ffmpeg_cap = True
    video.last_displayed_frame = 19 if frames else None
    video.media_pipeline.absolute_frames_processed = frames
    video.output_to_source_frame.return_value = 38
    dialog = MagicMock()
    dialog.total_frames = 100
    dialog.save_partial_on_skip_checkbox.isChecked.return_value = save
    dialog.update_partial_jobs_checkbox.isChecked.return_value = update
    window = SimpleNamespace(video_processor=video, job_progress_dialog=dialog)
    worker = SimpleNamespace(main_window=window, current_job_name="A", jobs_dir=tmp_path,
                             error_skip_requested=False)
    window.job_processor = worker
    for name in ("cancel_requested_event", "stop_requested_event", "skip_requested_event", "stop_on_job_errors_event"):
        setattr(worker, name, threading.Event())
    for name in names:
        setattr(worker, name, MethodType(namespace[name], worker))
    worker.run_ui_operation = lambda operation, *args: operation(*args)
    job_path = tmp_path / "A.json"
    job_path.write_text(json.dumps({"job_marker_pairs": [[0, 99], [120, 199]]}))
    observed = []

    def stopped():
        observed.append(json.loads(job_path.read_text())["job_marker_pairs"])

    video.stop_processing.side_effect = stopped
    video.finalize_segment_concatenation.side_effect = stopped
    video._finalize_default_style_recording.side_effect = stopped
    # Invoke the real fatal-error routing before it can discard partial output.
    vp_source = Path("app/processors/video_processor.py")
    vp_class = next(node for node in ast.parse(vp_source.read_text(encoding="utf-8")).body
                    if isinstance(node, ast.ClassDef) and node.name == "VideoProcessor")
    handler = next(node for node in vp_class.body if isinstance(node, ast.FunctionDef)
                   and node.name == "_handle_fatal_processing_error")
    handler.decorator_list = []
    exec(compile(ast.Module(body=[handler], type_ignores=[]), str(vp_source), "exec"), namespace)
    video.main_window = window
    video._fatal_processing_error_latched = False
    namespace["_handle_fatal_processing_error"](video, "inference failed")

    expected_start = (19 if segments else 38) if update and frames else 0
    assert observed == [[[expected_start, 99], [120, 199]]]
    assert worker.error_skip_requested
    assert worker.skip_requested_event.is_set()
    assert video.last_processing_error == "inference failed"
    if save:
        video.stop_processing.assert_not_called()
        if segments:
            video.finalize_segment_concatenation.assert_called_once_with()
            video._finalize_default_style_recording.assert_not_called()
        else:
            video._finalize_default_style_recording.assert_called_once_with()
            video.finalize_segment_concatenation.assert_not_called()
    else:
        video.stop_processing.assert_called_once_with()
        video.finalize_segment_concatenation.assert_not_called()
        video._finalize_default_style_recording.assert_not_called()
    namespace["_handle_fatal_processing_error"](video, "duplicate error")
    assert len(observed) == 1
    worker.processing_started_event = MagicMock()
    worker.processing_stopped_event = threading.Event()
    worker.processing_started_event.wait.side_effect = lambda **kwargs: (worker.processing_stopped_event.set(), True)[1]
    worker.JOB_START_TIMEOUT = 30
    worker.job_failed_signal = MagicMock()
    assert worker._trigger_and_wait_for_processing("A") is False
    worker.job_failed_signal.emit.assert_called_once_with("A", "inference failed")
