"""Exercise live edits and the batch-load overlay with real Qt, without inference."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_live_parameter_edits_survive_job_load_without_replacing_other_settings(tmp_path):
    script = textwrap.dedent('''
        import copy
        import sys
        import threading
        from contextlib import ExitStack
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch
        from PySide6 import QtCore, QtWidgets, QtTest
        from app.ui.widgets import job_progress_dialog
        from app.ui.widgets.actions import common_actions, job_manager_actions, layout_actions
        from app.ui.widgets.swapper_layout_data import SWAPPER_LAYOUT_DATA
        from app.helpers.miscellaneous import ParametersDict

        app = QtWidgets.QApplication([])
        job_progress_dialog.settings_group = lambda namespace, parent: QtCore.QSettings(
            sys.argv[1], QtCore.QSettings.IniFormat, parent
        )
        window = QtWidgets.QMainWindow()
        window.videoSeekSlider = QtWidgets.QSlider(window)
        window.video_processor = SimpleNamespace(
            processing=True, state_lock=threading.Lock(), feeder_parameters=None
        )
        window._batch_update_in_progress = False
        window.target_faces = {"old-face": MagicMock()}
        window.selected_target_face_id = "old-face"
        window.parameters = {"old-face": {"StrengthAmountSlider": 100}}
        window.current_widget_parameters = window.parameters["old-face"].copy()
        window.markers = {}
        dialog = job_progress_dialog.JobProgressDialog(window, {})
        window.job_progress_dialog = dialog
        window.parameter_widgets = {}
        window.parameter_section_states = {}
        window.register_parameter_section = MagicMock()
        window.default_parameters = {}
        window.control = {}
        panel = QtWidgets.QWidget(window)
        layout_actions.add_widgets_to_tab_layout(
            window,
            {"Swap strength and likeness": {
                name: SWAPPER_LAYOUT_DATA["Swap strength and likeness"][name]
                for name in ("StrengthEnableToggle", "StrengthAmountSlider")
            }},
            QtWidgets.QVBoxLayout(panel),
        )
        slider = window.parameter_widgets["StrengthAmountSlider"]
        edit = lambda name, value: common_actions.update_parameter(
            window, name, value, enable_refresh_frame=False
        )

        assert not dialog.lock_parameters_checkbox.isChecked()
        edit("StrengthAmountSlider", 125)
        assert dialog.parameter_overrides == {}
        dialog.lock_parameters_checkbox.setChecked(True)
        edit("StrengthAmountSlider", 125)  # No actual change.
        assert dialog.parameter_overrides == {}
        slider.line_edit.setText("150")
        slider.setSliderPosition(200)
        slider.debounce_timer.start(1)
        QtTest.QTest.qWait(30)
        assert slider.value() == 200
        assert dialog.parameter_overrides == {"StrengthAmountSlider": 200}
        slider.line_edit.setText("175")  # Latest edit wins through real widget signals.
        edit("SwapModelSelection", "GhostFace-v1")
        window._batch_update_in_progress = True
        edit("StrengthAmountSlider", 200)  # Programmatic restore must not be captured.
        window._batch_update_in_progress = False
        window.video_processor.processing = False
        edit("StrengthAmountSlider", 225)  # No active processing.
        assert dialog.parameter_overrides == {"StrengthAmountSlider": 175}

        job = {
            "selected_media_id": "media",
            "selected_target_face_id": "new-face",
            "restore_selected_face": True,
            "target_faces_data": {
                face: {"parameters": {
                    "StrengthAmountSlider": 50, "SwapModelSelection": "Inswapper128",
                    "StrengthEnableToggle": False,
                }} for face in ("new-face", "other-face")
            },
            "control": {"KeepControlsToggle": False, "OutputMediaFolder": "job-output"},
            "markers": {"10": {"parameters": {
                face: {"StrengthAmountSlider": 75, "SwapModelSelection": "SimSwap512"}
                for face in ("new-face", "other-face")
            }, "control": {"OutputMediaFolder": "marker-output"}}},
        }
        original = copy.deepcopy(job)
        window.control = job["control"].copy()
        window.target_videos = {"media": MagicMock()}
        window.job_processor = SimpleNamespace(job_settings_loaded_event=threading.Event())
        stages = []

        def load_faces(mw, data):
            stages.append("faces")
            assert mw._batch_update_in_progress
            mw.parameters = {key: face["parameters"].copy()
                             for key, face in data["target_faces_data"].items()}
            mw.target_faces = {key: MagicMock() for key in mw.parameters}

        def load_controls(mw, data, is_batch_load):
            stages.append("controls")
            assert is_batch_load
            assert data["control"] == original["control"]
            assert mw.parameters["new-face"]["StrengthAmountSlider"] == 50
            # Simulate widget synchronization during the normal loader.
            mw.video_processor.processing = True
            edit("StrengthEnableToggle", True)
            common_actions.set_widgets_values_using_face_id_parameters(mw)
            mw.video_processor.processing = False

        def load_markers(mw, data):
            stages.append("markers")
            mw.markers = copy.deepcopy(data["markers"])

        with ExitStack() as stack:
            stack.enter_context(patch.object(job_manager_actions, "_load_job_target_faces_and_params", load_faces))
            stack.enter_context(patch.object(job_manager_actions, "_load_job_controls_and_state", load_controls))
            stack.enter_context(patch.object(job_manager_actions, "_load_job_markers", load_markers))
            errors = stack.enter_context(patch.object(job_manager_actions.QMessageBox, "critical"))
            job_manager_actions.load_job_settings(window, job)
            errors.assert_not_called()

        assert stages == ["faces", "controls", "markers"]
        assert window.job_processor.job_settings_loaded_event.is_set()
        assert not window._batch_update_in_progress
        assert dialog.parameter_overrides == {"StrengthAmountSlider": 175}
        assert slider.value() == 175
        assert window.current_widget_parameters["StrengthAmountSlider"] == 175
        for params in window.parameters.values():
            assert params["StrengthAmountSlider"] == 175
            assert params["SwapModelSelection"] == "Inswapper128"
        for params in window.markers["10"]["parameters"].values():
            assert params["StrengthAmountSlider"] == 175
            assert params["SwapModelSelection"] == "SimSwap512"
        assert window.markers["10"]["control"] == original["markers"]["10"]["control"]
        assert job == original

        # Exercise the real face and marker loaders with optional fields omitted.
        window.default_parameters = ParametersDict(window.default_parameters, {})
        window.apply_parameter_section_states = MagicMock()
        window.videoSeekSlider.add_marker_and_paint = MagicMock()
        window.merged_embeddings = {}
        window.input_faces = {}
        def add_face(mw, image, embeddings, pixmap, face_id):
            mw.target_faces[face_id] = MagicMock()

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                job_manager_actions.list_view_actions,
                "add_media_thumbnail_to_target_faces_list", add_face,
            ))
            stack.enter_context(patch.object(
                job_manager_actions, "_load_job_controls_and_state",
                lambda mw, data, is_batch_load: common_actions.set_widgets_values_using_face_id_parameters(mw),
            ))
            for name in ("set_issue_frames_for_face", "set_issue_frames_by_face",
                         "set_dropped_frames", "update_drop_frame_button_label"):
                stack.enter_context(patch.object(job_manager_actions.video_control_actions, name))
            errors = stack.enter_context(patch.object(job_manager_actions.QMessageBox, "critical"))
            for variant in ("missing-face-parameters", "control-only-marker", "null-markers", "no-faces"):
                sparse = copy.deepcopy(job)
                for face in sparse["target_faces_data"].values():
                    face["cropped_face"] = [[[0, 0, 0], [0, 0, 0]], [[0, 0, 0], [0, 0, 0]]]
                    face["embedding_store"] = {}
                if variant == "missing-face-parameters":
                    for face in sparse["target_faces_data"].values():
                        del face["parameters"]
                elif variant == "control-only-marker":
                    del sparse["markers"]["10"]["parameters"]
                elif variant == "null-markers":
                    sparse["markers"] = None
                else:
                    del sparse["target_faces_data"]
                    sparse["selected_target_face_id"] = None
                    sparse["restore_selected_face"] = False
                    del sparse["markers"]
                before = copy.deepcopy(sparse)
                window.parameters = {}
                window.target_faces = {}
                window.markers = {}
                window.current_widget_parameters = window.default_parameters.copy()
                window.job_processor.job_settings_loaded_event.clear()
                job_manager_actions.load_job_settings(window, sparse)
                errors.assert_not_called()
                assert window.job_processor.job_settings_loaded_event.is_set()
                assert sparse == before
                assert slider.value() == 175
                assert window.current_widget_parameters["StrengthAmountSlider"] == 175
                assert all(params["StrengthAmountSlider"] == 175 for params in window.parameters.values())
                assert all(params["StrengthAmountSlider"] == 175
                           for marker in window.markers.values() for params in marker["parameters"].values())

        # Programmatic restoration and queued widget events must not add overrides.
        QtTest.QTest.qWait(350)
        assert dialog.parameter_overrides == {"StrengthAmountSlider": 175}
        # The runtime loader supplies normalized dictionaries even for omitted raw fields.
        window.parameters = {"defaults-only-face": {"StrengthAmountSlider": 100}}
        window.markers = {10: {"parameters": {}, "control": {}}}
        window._batch_update_in_progress = True
        dialog.apply_parameter_overrides()
        window._batch_update_in_progress = False
        assert window.parameters["defaults-only-face"]["StrengthAmountSlider"] == 175
        assert window.markers[10]["parameters"] == {}
        dialog.lock_parameters_checkbox.setChecked(False)
        assert dialog.parameter_overrides == {}
        assert window.parameters["defaults-only-face"]["StrengthAmountSlider"] == 175
        window.parameters["defaults-only-face"]["StrengthAmountSlider"] = 50
        dialog.apply_parameter_overrides()
        assert window.parameters["defaults-only-face"]["StrengthAmountSlider"] == 50
        dialog.lock_parameters_checkbox.setChecked(True)
        assert dialog.parameter_overrides == {}
        fresh = job_progress_dialog.JobProgressDialog(window, {})
        assert not fresh.lock_parameters_checkbox.isChecked()
        assert fresh.parameter_overrides == {}
        dialog.record_parameter_edit("StrengthAmountSlider", 200)
        dialog.finish()
        assert dialog.parameter_overrides == {}
        assert not dialog.lock_parameters_checkbox.isEnabled()
    ''')
    result = subprocess.run(
        [sys.executable, "-u", "-c", script, str(tmp_path / "lock.ini")],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
