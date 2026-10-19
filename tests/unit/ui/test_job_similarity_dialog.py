"""Real Qt preparation and file rechecks, without loading assets or rendering."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize("theme,scale", [("light", "1"), ("dark", "1.5")])
def test_similarity_review_and_processing_selection(tmp_path, theme, scale):
    script = textwrap.dedent("""
        import copy
        import json
        from pathlib import Path
        import sys
        import time
        from unittest.mock import patch
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
        import qdarktheme
        from app.ui.core.main_window import Ui_MainWindow
        from app.ui.widgets.actions import job_manager_actions as actions
        from app.ui.widgets.job_similarity_dialog import JobSimilarityDialog
        from app.ui.widgets.job_list_widgets import JobDataRole

        app = QtWidgets.QApplication([])
        app.setFont(QtGui.QFont("Segoe UI", 10))
        app.setStyleSheet(qdarktheme.load_stylesheet(theme=sys.argv[2]))
        root = Path(sys.argv[1])
        jobs_dir = root / "jobs"
        jobs_dir.mkdir()
        window = QtWidgets.QMainWindow()
        ui = Ui_MainWindow()
        ui.setupUi(window)
        assert isinstance(ui.jobControlLayout, QtWidgets.QGridLayout)
        assert isinstance(ui.jobControlLayout_2, QtWidgets.QFormLayout)
        assert isinstance(ui.processControlLayout, QtWidgets.QGridLayout)
        assert ui.jobControlLayout.itemAtPosition(1, 2).widget() is ui.smartJobListButton
        assert ui.processControlLayout.itemAtPosition(1, 1).widget() is ui.buttonProcessSelectedSimilar
        assert not hasattr(ui, "buttonStopBatch")
        assert ui.buttonProcessSelected.text() == "Process (0)"
        for name in ("jobQueueList", "buttonProcessAll", "buttonProcessSelected",
                     "buttonProcessSelectedSimilar", "buttonProcessAllSimilar", "buttonStopProcessing", "loadJobButton",
                     "deleteJobButton", "smartJobListButton", "checkNewJobListButton",
                     "refreshJobListButton", "addJobButton", "jobListLabelTemplateComboBox"):
            setattr(window, name, getattr(ui, name))
        window.project_root_path = root
        window.job_progress_dialog = None
        window.job_processing_button = None
        window.control = {"ProvidersPrioritySelection": "TensorRT-Engine", "KeepModelsAliveToggle": True}
        parameters = {"SwapModelSelection": "Inswapper128", "StrengthAmountSlider": 90}
        window.jobQueueList.clear()
        window.jobQueueList.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        actions.connect_job_manager_signals(window)
        actions.update_job_manager_buttons(window)
        assert not window.buttonProcessSelectedSimilar.isEnabled()
        payload = {
            "control": window.control.copy(),
            "target_faces_data": {"face-A": {"parameters": parameters.copy(),
                "embedding_store": {"ignored": [1, 2]}, "assigned_merged_embeddings": ["embed-A"]}},
            "markers": {}, "job_marker_pairs": [], "dropped_frames": [],
            "swap_faces_enabled": True, "edit_faces_enabled": True,
            "target_medias_data": [{"media_id": "media-A", "media_path": "does-not-exist.mp4"}],
            "embeddings_data": {"embed-A": {"embedding_store": {"ignored": [1, 2]}}},
        }
        payloads = {name: copy.deepcopy(payload) for name in ("A", "B", "C", "D", "E")}
        payloads["B"]["target_faces_data"]["face-B"] = payloads["B"]["target_faces_data"].pop("face-A")
        payloads["B"]["target_faces_data"]["face-B"]["embedding_store"] = {"other": [9]}
        payloads["B"]["target_medias_data"] = [{"media_id": "media-B", "media_path": "other.mp4"}]
        payloads["B"]["embeddings_data"] = {}
        for name in ("C", "D"):
            payloads[name]["target_faces_data"]["face-A"]["parameters"]["StrengthAmountSlider"] = 80
        payloads["E"]["markers"] = {"10": {"parameters": {}}}
        for name, data in payloads.items():
            (jobs_dir / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
            item = QtWidgets.QListWidgetItem(name)
            item.setData(JobDataRole.JobNameRole, name)
            window.jobQueueList.addItem(item)
            item.setSelected(name != "E")
        assert window.buttonProcessSelectedSimilar.isEnabled()
        assert window.buttonProcessSelected.text() == "Process (4)"
        assert window.buttonProcessSelectedSimilar.text() == "Process Similar (4)"
        assert window.buttonProcessAllSimilar.isEnabled()
        with patch.object(actions, "prepare_similar_jobs") as prepare:
            window.buttonProcessSelectedSimilar.click()
            prepare.assert_called_once_with(window, selected_only=True)
            prepare.reset_mock()
            window.buttonProcessAllSimilar.click()
            prepare.assert_called_once_with(window, selected_only=False)
        with patch("app.ui.widgets.job_similarity_dialog.JobSimilarityDialog") as dialog_type, \
             patch.object(actions, "start_job_processor") as start:
            dialog_type.return_value.exec.return_value = QtWidgets.QDialog.Accepted
            dialog_type.return_value.jobs_to_process = ["C"]
            actions.prepare_similar_jobs(window, selected_only=True)
            dialog_type.assert_called_once_with(window, ["A", "B", "C", "D"])
            start.assert_called_once_with(window, ["C"], processing_button=window.buttonProcessSelectedSimilar)
            dialog_type.reset_mock()
            start.reset_mock()
            actions.prepare_similar_jobs(window, selected_only=False)
            dialog_type.assert_called_once_with(window, ["A", "B", "C", "D", "E"])
            start.assert_called_once_with(window, ["C"], processing_button=window.buttonProcessAllSimilar)
            start.reset_mock()
            dialog_type.return_value.exec.return_value = QtWidgets.QDialog.Rejected
            actions.prepare_similar_jobs(window, selected_only=True)
            start.assert_not_called()

        def wait_for_check(dialog):
            deadline = time.monotonic() + 10
            while (dialog.checking or not dialog.configurations) and time.monotonic() < deadline:
                app.processEvents()
                QtTest.QTest.qWait(5)
            assert not dialog.checking
            assert not dialog.worker.isRunning()

        original_control = window.control.copy()
        def forbidden(*args, **kwargs):
            raise AssertionError("Preparation must not load or process jobs")
        with patch.object(actions, "start_job_processor", side_effect=forbidden), \
             patch.object(actions, "load_master_assets", side_effect=forbidden), \
             patch.object(actions, "load_job_settings", side_effect=forbidden):
            dialog = JobSimilarityDialog(window, ["A", "B", "C", "D", "E"])
            dialog.show()
            wait_for_check(dialog)
            assert dialog.selected_jobs() == ["A", "B"]
            assert dialog.start_button.isEnabled()
            assert dialog.start_button.text() == "Send"
            assert dialog.items["B"].text(1) == "Same settings"
            assert dialog.results.columnCount() == 3
            assert not dialog.differences["A"] and not dialog.differences["B"]
            assert dialog.details.toPlainText() == "No differences."
            assert "StrengthAmountSlider" in dialog.differences["C"][0]
            assert "markers" in dialog.differences["E"][0]
            dialog.results.setCurrentItem(dialog.items["C"])
            assert "reference = 90; job = 80" in dialog.details.toPlainText()
            dialog.grab().save(str(root / "preparation.png"))

            # The file changes after preview: Send must reread, not approve the cached match.
            payloads["B"]["control"]["KeepModelsAliveToggle"] = False
            (jobs_dir / "B.json").write_text(json.dumps(payloads["B"]), encoding="utf-8")
            dialog.start_button.click()
            wait_for_check(dialog)
            assert not dialog.jobs_to_process
            assert not dialog.start_button.isEnabled()
            assert "KeepModelsAliveToggle" in dialog.differences["B"][0]

            # A different compatible subset can become the reference group.
            for name in ("A", "B"):
                dialog.items[name].setCheckState(0, QtCore.Qt.Unchecked)
            for name in ("C", "D"):
                dialog.items[name].setCheckState(0, QtCore.Qt.Checked)
            assert dialog.reference_label.text() == "Reference: C"
            assert dialog.start_button.isEnabled()
            dialog.start_button.click()
            wait_for_check(dialog)
            assert dialog.jobs_to_process == ["C", "D"]
            assert dialog.result() == QtWidgets.QDialog.Accepted
            assert not dialog.isVisible()
            single = JobSimilarityDialog(window, ["C"])
            single.show()
            wait_for_check(single)
            assert single.start_button.isEnabled()
            single.start_button.click()
            wait_for_check(single)
            assert single.jobs_to_process == ["C"]
            assert single.result() == QtWidgets.QDialog.Accepted
            app.processEvents()
            cancelled = JobSimilarityDialog(window, ["A", "B"])
            cancelled.show()
            cancelled.check_jobs()
            cancelled.reject()
            assert not cancelled.worker.isRunning()
            assert not cancelled.isVisible()
        assert window.control == original_control
        assert set(path.stem for path in jobs_dir.glob("*.json")) == set(payloads)
        assert not (jobs_dir / "completed").exists()
        print("PASS similarity review")
    """)
    result = subprocess.run(
        [sys.executable, "-u", "-c", script, str(tmp_path), theme],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_SCALE_FACTOR": scale},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "PASS similarity review" in result.stdout
