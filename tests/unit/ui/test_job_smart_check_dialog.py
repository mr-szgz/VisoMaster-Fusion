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
        from pathlib import Path
        import sys
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
        for name in ("jobQueueList", "buttonProcessAll", "buttonProcessSelected",
                     "buttonStopProcessing", "loadJobButton", "deleteJobButton",
                     "smartJobListButton", "checkNewJobListButton", "refreshJobListButton",
                     "addJobButton", "jobListLabelTemplateComboBox"):
            setattr(window, name, getattr(ui, name))
        window.project_root_path = root
        window.job_progress_dialog = None
        window.job_processing_button = None
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
        dialog.reject()
        assert dialog.isVisible()
        wait_for_scan(dialog)
        assert dialog.checked_jobs == 6
        assert dialog.passed_jobs == 2
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

        trashed = []
        def trash(filename):
            path = Path(filename)
            trashed.append(path.stem)
            path.unlink()
        with patch.object(smart, "send2trash", side_effect=trash):
            dialog.remove_button.click()
        assert set(trashed) == set(dialog.failed_jobs)
        assert {path.stem for path in jobs.glob("*.json")} == {"pass", "same-assets"}
        assert {window.jobQueueList.item(i).data(JobDataRole.JobNameRole)
                for i in range(window.jobQueueList.count())} == {"pass", "same-assets"}
        assert media.exists() and face.exists()
        assert not dialog.remove_button.isEnabled()
        assert "Removed 4" in dialog.status_label.text()
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
