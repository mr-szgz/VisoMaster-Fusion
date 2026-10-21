"""Exercise the shared pre-flight scan and failed-job cleanup with real Qt."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize("theme,scale", [("light", "1"), ("dark", "1.5")])
def test_smart_scan_report_and_cleanup(tmp_path, theme, scale):
    script = textwrap.dedent("""
        import copy
        import json
        from itertools import product
        from pathlib import Path
        import sys
        import threading
        import time
        from unittest.mock import patch
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
        import qdarktheme
        from app.ui.widgets.actions import job_manager_actions as actions
        from app.ui.widgets import job_smart_check_dialog as smart
        from app.ui.widgets.job_list_widgets import JobDataRole
        from app.ui.core.main_window import Ui_MainWindow

        app = QtWidgets.QApplication([])
        app.setFont(QtGui.QFont("Segoe UI", 10))
        app.setStyleSheet(qdarktheme.load_stylesheet(theme=sys.argv[2]))
        root = Path(sys.argv[1])
        window = QtWidgets.QMainWindow()
        ui = Ui_MainWindow()
        ui.setupUi(window)
        ui.jobQueueList.clear()
        assert ui.checkNewJobListButton.text() == "Check for Jobs"
        assert ui.smartJobListButton.text() == "S.M.A.R.T"
        for name in ("jobQueueList", "buttonProcessAll", "buttonProcessSelected", "buttonProcessSelectedSimilar", "buttonProcessAllSimilar",
                     "buttonStopProcessing", "loadJobButton", "deleteJobButton",
                     "smartJobListButton", "checkNewJobListButton", "refreshJobListButton",
                     "addJobButton", "jobListLabelTemplateComboBox", "jobsManagerSearchBox",
                     "jobsManagerSearchResetButton"):
            setattr(window, name, getattr(ui, name))
        window.project_root_path = root
        window.job_progress_dialog = None
        window.job_processing_button = None
        window.job_similarity_dialog = None
        window.job_similarity_button = None
        actions.connect_job_manager_signals(window)
        with patch.object(actions, "check_jobs_smart") as check_jobs:
            window.smartJobListButton.click()
            check_jobs.assert_called_once_with(window)
        jobs = root / "jobs"
        jobs.mkdir()
        media = root / "video.mp4"
        face = root / "face.png"
        media.touch()
        face.touch()
        valid = {
            "selected_media_id": "media",
            "target_medias_data": [{"media_id": "media", "media_path": str(media)}],
            "target_faces_data": {"face": {
                "assigned_input_faces": ["input"], "assigned_merged_embeddings": ["embed"]}},
            "input_faces_data": {"input": {"media_path": str(face)}},
            "embeddings_data": {"embed": {"embedding_name": "Saved", "embedding_store": {}}},
        }
        payloads = {"pass": valid, "same-assets": copy.deepcopy(valid)}
        for name, field in (("missing-media", "media"), ("missing-face", "face"),
                            ("missing-embedding", "embedding")):
            payload = copy.deepcopy(valid)
            if field == "media":
                payload["target_medias_data"][0]["media_path"] = str(root / "missing.mp4")
            elif field == "face":
                payload["input_faces_data"]["input"]["media_path"] = str(root / "missing.png")
            else:
                payload["embeddings_data"] = {}
            payloads[name] = payload
        for name, payload in payloads.items():
            (jobs / f"{name}.json").write_text(json.dumps(payload))
        (jobs / "broken-json.json").write_text("{")
        names = list(payloads) + ["broken-json"]
        for name in names:
            item = QtWidgets.QListWidgetItem(name)
            item.setData(JobDataRole.JobNameRole, name)
            window.jobQueueList.addItem(item)

        def wait_for_scan(dialog):
            deadline = time.monotonic() + 15
            while not dialog.scan_complete and time.monotonic() < deadline:
                app.processEvents()
                QtTest.QTest.qWait(5)
            assert dialog.scan_complete
            assert not dialog.worker.isRunning()

        dialog = smart.JobSmartCheckDialog(window, names)
        dialog.show()
        assert not dialog.remove_button.isEnabled()
        assert not dialog.close_button.isEnabled()
        assert set(dialog.state_filters) == {"Passed", "Failed", "Removed"}
        assert all(checkbox.isChecked() for checkbox in dialog.state_filters.values())
        assert all(checkbox.text() == f"{state} (0)" for state, checkbox in dialog.state_filters.items())
        dialog.state_filters["Failed"].setChecked(False)
        wait_for_scan(dialog)
        assert all(
            dialog.results.topLevelItem(i).isHidden()
            == (dialog.results.topLevelItem(i).text(1) == "Failed")
            for i in range(dialog.results.topLevelItemCount())
        )
        dialog.state_filters["Failed"].setChecked(True)
        assert dialog.checked_jobs == 6
        assert dialog.passed_jobs == 2
        assert dialog.state_filters["Passed"].text() == "Passed (2)"
        assert dialog.state_filters["Failed"].text() == "Failed (4)"
        assert dialog.state_filters["Removed"].text() == "Removed (0)"
        assert set(dialog.failed_jobs) == set(names) - {"pass", "same-assets"}
        assert dialog.progress_bar.value() == 6
        assert "Media: 1" in dialog.assets_label.text()
        assert "Input faces: 1" in dialog.assets_label.text()
        assert "Embeddings: 1" in dialog.assets_label.text()
        assert "Target media file not found" in dialog.failed_jobs["missing-media"]
        assert "Input face file not found" in dialog.failed_jobs["missing-face"]
        assert "Required embedding ID" in dialog.failed_jobs["missing-embedding"]
        assert "read or parsed" in dialog.failed_jobs["broken-json"]
        assert dialog.remove_button.isEnabled()
        assert dialog.close_button.isEnabled()
        assert dialog.results.topLevelItemCount() == 6
        dialog.grab().save(str(root / "report.png"))

        def check_filters(report):
            metrics = report.metrics_label.text()
            for checked in product((False, True), repeat=3):
                for checkbox, value in zip(report.state_filters.values(), checked):
                    checkbox.setChecked(value)
                for index in range(report.results.topLevelItemCount()):
                    item = report.results.topLevelItem(index)
                    assert item.isHidden() == (not report.state_filters[item.text(1)].isChecked())
                assert report.metrics_label.text() == metrics
                for state, checkbox in report.state_filters.items():
                    count = sum(report.results.topLevelItem(i).text(1) == state
                                for i in range(report.results.topLevelItemCount()))
                    assert checkbox.text() == f"{state} ({count})"

        check_filters(dialog)

        for action in ("stop", "cancel", "escape", "close"):
            entered = threading.Event()
            release = threading.Event()
            validate = actions._validate_job_files_exist
            def blocked_validation(data):
                if data["target_medias_data"][0]["media_path"] == str(media):
                    entered.set()
                    assert release.wait(10)
                return validate(data)

            with patch.object(actions, "_validate_job_files_exist", blocked_validation):
                partial = smart.JobSmartCheckDialog(
                    window, ["missing-media", "pass", "same-assets"]
                )
                partial.show()
                deadline = time.monotonic() + 10
                while (not entered.is_set() or partial.checked_jobs != 1) and time.monotonic() < deadline:
                    app.processEvents()
                    QtTest.QTest.qWait(5)
                assert entered.is_set()
                assert partial.checked_jobs == 1
                assert partial.state_filters["Failed"].text() == "Failed (1)"
                assert partial.state_filters["Passed"].text() == "Passed (0)"
                assert partial.stop_button.isEnabled()
                assert partial.cancel_button.isEnabled()
                if action == "stop":
                    partial.stop_button.click()
                    assert partial.isVisible()
                    assert not partial.stop_button.isEnabled()
                elif action == "cancel":
                    partial.cancel_button.click()
                elif action == "escape":
                    QtTest.QTest.keyClick(partial, QtCore.Qt.Key_Escape)
                else:
                    partial.close()
                release.set()
                wait_for_scan(partial)

            assert partial.checked_jobs == 1
            if action == "stop":
                assert partial.isVisible()
                assert set(partial.failed_jobs) == {"missing-media"}
                assert partial.results.topLevelItemCount() == 1
                assert partial.remove_button.isEnabled()
                assert "stopped" in partial.status_label.text()
                check_filters(partial)
                partial.state_filters["Failed"].setChecked(False)
                with patch.object(smart, "send2trash") as stopped_trash:
                    partial.remove_button.click()
                    stopped_trash.assert_called_once_with(str(jobs / "missing-media.json"))
                assert partial.results.topLevelItem(0).text(1) == "Removed"
                assert not partial.results.topLevelItem(0).isHidden()
                check_filters(partial)
                partial.close_button.click()
            else:
                assert not partial.isVisible()
                assert partial.result() == QtWidgets.QDialog.Rejected
                assert partial.failed_jobs == {}
                assert partial.results.topLevelItemCount() == 0
                assert all(checkbox.text() == f"{state} (0)" for state, checkbox in partial.state_filters.items())
            assert (jobs / "missing-media.json").exists()

        immediate = smart.JobSmartCheckDialog(window, names)
        immediate.show()
        immediate.cancel_button.click()
        wait_for_scan(immediate)
        assert not immediate.isVisible()
        assert immediate.results.topLevelItemCount() == 0
        assert immediate.failed_jobs == {}

        trashed = []
        def trash(filename):
            path = Path(filename)
            trashed.append(path.stem)
            path.unlink()
        with patch.object(smart, "send2trash", side_effect=trash):
            dialog.state_filters["Removed"].setChecked(False)
            dialog.remove_button.click()
        assert all(
            dialog.results.topLevelItem(i).isHidden()
            == (dialog.results.topLevelItem(i).text(1) == "Removed")
            for i in range(dialog.results.topLevelItemCount())
        )
        check_filters(dialog)
        assert set(trashed) == set(dialog.failed_jobs)
        assert {path.stem for path in jobs.glob("*.json")} == {"pass", "same-assets"}
        assert {window.jobQueueList.item(i).data(JobDataRole.JobNameRole)
                for i in range(window.jobQueueList.count())} == {"pass", "same-assets"}
        assert media.exists() and face.exists()
        assert not dialog.remove_button.isEnabled()
        assert "Removed 4" in dialog.status_label.text()
        assert dialog.state_filters["Passed"].text() == "Passed (2)"
        assert dialog.state_filters["Failed"].text() == "Failed (0)"
        assert dialog.state_filters["Removed"].text() == "Removed (4)"
        assert dialog.checked_jobs == 6 and len(dialog.failed_jobs) == 4
        dialog.close_button.click()
        assert not dialog.isVisible()

        for job_names in (["pass", "same-assets"], []):
            report = smart.JobSmartCheckDialog(window, job_names)
            report.show()
            wait_for_scan(report)
            assert not report.remove_button.isEnabled()
            assert report.passed_jobs == len(job_names)
            assert report.close_button.isEnabled()
            check_filters(report)
            report.close()
        assert not (jobs / "completed").exists()
        print("PASS SMART scan and cleanup")
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
    assert "PASS SMART scan and cleanup" in result.stdout
