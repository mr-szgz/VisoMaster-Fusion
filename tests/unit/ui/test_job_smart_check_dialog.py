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
        import cv2
        import json
        import numpy as np
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
        payloads["same-assets"]["embeddings_data"]["unused"] = {
            "embedding_name": "Unused", "embedding_store": {}}
        payloads["same-assets"]["target_medias_data"][0].update(fps=25.0, frame_count=10)
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
        assert [dialog.results.headerItem().text(i) for i in range(7)] == [
            "Job", "Status", "Embedding name", "Embeddings", "FPS", "Frames", "Bytes"]
        rows = {dialog.results.topLevelItem(i).text(0): dialog.results.topLevelItem(i)
                for i in range(dialog.results.topLevelItemCount())}
        assert [rows["pass"].text(i) for i in range(2, 6)] == ["Saved", "1", "", ""]
        for name, row in rows.items():
            assert int(row.text(6)) == (jobs / f"{name}.json").stat().st_size
        assert int(dialog.total_bytes_label.text()) == sum(
            (jobs / f"{name}.json").stat().st_size for name in names)
        assert not dialog.remove_embeddings_button.isEnabled()
        assert not dialog.update_metadata_button.isEnabled()

        assert dialog.property_filters["Embeddings > 1"].text() == "Embeddings > 1 (1)"
        assert dialog.property_filters["Missing FPS"].text() == "Missing FPS (5)"
        assert dialog.property_filters["Missing Frames"].text() == "Missing Frames (5)"
        for states in product((False, True), repeat=3):
            for checkbox, checked in zip(dialog.state_filters.values(), states):
                checkbox.setChecked(checked)
            for properties in product((False, True), repeat=3):
                for checkbox, checked in zip(dialog.property_filters.values(), properties):
                    checkbox.setChecked(checked)
                for row in rows.values():
                    matches = (row.text(3) != "" and int(row.text(3)) > 1,
                               row.text(4) == "", row.text(5) == "")
                    visible = dialog.state_filters[row.text(1)].isChecked() and (
                        not any(properties) or any(checked and match for checked, match in zip(properties, matches)))
                    assert row.isHidden() == (not visible)
                dialog.select_all_button.click()
                assert {row.text(0) for row in dialog.results.selectedItems()} == {
                    row.text(0) for row in rows.values() if not row.isHidden()}
        for checkbox in dialog.property_filters.values():
            checkbox.setChecked(False)
        for checkbox in dialog.state_filters.values():
            checkbox.setChecked(True)
        dialog.results.clearSelection()

        assert not dialog.select_job_button.isEnabled()
        rows["pass"].setSelected(True)
        assert dialog.select_job_button.isEnabled()
        window.jobsManagerSearchBox.setText("missing")
        dialog.select_job_button.click()
        assert window.jobsManagerSearchBox.text() == ""
        assert [item.data(JobDataRole.JobNameRole) for item in window.jobQueueList.selectedItems()] == ["pass"]
        assert not window.jobQueueList.currentItem().isHidden()
        assert dialog.isVisible()
        rows["same-assets"].setSelected(True)
        assert not dialog.select_job_button.isEnabled()
        dialog.results.clearSelection()

        assert dialog.results.isSortingEnabled()
        sorting_tree = QtWidgets.QTreeWidget()
        sorting_tree.setColumnCount(7)
        for value in ("100", "2", "10", ""):
            sorting_tree.addTopLevelItem(smart.JobSmartCheckItem(
                [value, "Passed", "Saved", value, value, value, value]))
        for column in (3, 4, 5, 6):
            for order, expected in (
                (QtCore.Qt.AscendingOrder, ["", "2", "10", "100"]),
                (QtCore.Qt.DescendingOrder, ["100", "10", "2", ""]),
            ):
                sorting_tree.sortItems(column, order)
                assert [sorting_tree.topLevelItem(i).text(column) for i in range(4)] == expected
        sorting_tree.clear()
        for value in ("29.97", "9.5", "100.0"):
            sorting_tree.addTopLevelItem(smart.JobSmartCheckItem(
                ["job", "Passed", "Saved", "1", value, "10", "100"]))
        sorting_tree.sortItems(4, QtCore.Qt.DescendingOrder)
        assert [sorting_tree.topLevelItem(i).text(4) for i in range(3)] == ["100.0", "29.97", "9.5"]
        sorting_tree.clear()
        sorting_tree.setHeaderLabels(["Job", "Status", "Embedding name", "Embeddings", "FPS", "Frames", "Bytes"])
        sorting_tree.setSortingEnabled(True)
        for index in range(1200):
            sorting_tree.addTopLevelItem(smart.JobSmartCheckItem([
                f"job-{index}", "Passed" if index % 2 else "Failed", f"embedding-{index % 10}",
                str(index % 10), str(index / 10), str(index), str(index * 100),
            ]))
            # Force pending sorts while new scan results arrive.
            sorting_tree.topLevelItem(0).setHidden(False)
        sorting_tree.show()
        app.processEvents()
        for column in range(7):
            header = sorting_tree.header()
            sorting_tree.scrollToItem(sorting_tree.topLevelItem(0), QtWidgets.QAbstractItemView.PositionAtTop)
            sorting_tree.horizontalScrollBar().setValue(header.sectionPosition(column))
            point = QtCore.QPoint(header.sectionViewportPosition(column) + header.sectionSize(column) // 2,
                                 header.height() // 2)
            for _ in range(2):
                QtTest.QTest.mouseClick(header.viewport(), QtCore.Qt.LeftButton, pos=point)
                assert sorting_tree.sortColumn() == column
                values = [sorting_tree.topLevelItem(i).text(column) for i in range(1200)]
                key = float if column == 4 else int if column in (3, 5, 6) else str
                assert values == sorted(values, key=key,
                    reverse=header.sortIndicatorOrder() == QtCore.Qt.DescendingOrder)
        sorting_tree.close()
        dialog.results.sortItems(6, QtCore.Qt.DescendingOrder)
        assert [int(dialog.results.topLevelItem(i).text(6)) for i in range(6)] == sorted(
            (int(row.text(6)) for row in rows.values()), reverse=True)

        writer = cv2.VideoWriter(str(media), cv2.VideoWriter_fourcc(*"mp4v"), 25, (32, 32))
        assert writer.isOpened()
        for _ in range(10):
            writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
        writer.release()
        for name in ("pass", "same-assets"):
            payload = copy.deepcopy(valid)
            payload["embeddings_data"]["unused"] = {"embedding_name": "Unused", "embedding_store": {}}
            if name == "pass":
                payload["target_medias_data"][0]["fps"] = 30.0
                payload["embeddings_data"]["second"] = {"embedding_name": "Second", "embedding_store": {}}
                payload["target_faces_data"]["second-face"] = {"assigned_merged_embeddings": ["second"]}
            (jobs / f"{name}.json").write_text(json.dumps(payload))
        untouched = (jobs / "same-assets.json").read_bytes()
        rows["pass"].setSelected(True)
        assert dialog.remove_embeddings_button.isEnabled()
        dialog.remove_embeddings_button.click()
        cleaned = json.loads((jobs / "pass.json").read_text())
        assert set(cleaned["embeddings_data"]) == {"embed", "second"}
        assert rows["pass"].text(3) == "2"
        assert (jobs / "same-assets.json").read_bytes() == untouched
        rows["same-assets"].setSelected(True)
        dialog.update_metadata_button.click()
        for name, fps in (("pass", 30.0), ("same-assets", 25.0)):
            saved = json.loads((jobs / f"{name}.json").read_text())
            assert saved["target_medias_data"][0]["fps"] == fps
            assert saved["target_medias_data"][0]["frame_count"] == 10
            assert rows[name].text(4) == str(fps)
            assert rows[name].text(5) == "10"
            assert int(rows[name].text(6)) == (jobs / f"{name}.json").stat().st_size
        assert int(dialog.total_bytes_label.text()) == sum(
            (jobs / f"{name}.json").stat().st_size for name in names)
        with patch.object(smart.cv2, "VideoCapture") as capture:
            dialog.update_metadata_button.click()
            capture.assert_not_called()
        assert dialog.property_filters["Embeddings > 1"].text() == "Embeddings > 1 (2)"
        assert dialog.property_filters["Missing FPS"].text() == "Missing FPS (4)"
        assert dialog.property_filters["Missing Frames"].text() == "Missing Frames (4)"
        dialog.results.clearSelection()
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
                assert int(partial.total_bytes_label.text()) == (jobs / "missing-media.json").stat().st_size
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
            dialog.results.sortItems(1, QtCore.Qt.AscendingOrder)
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
        assert int(dialog.total_bytes_label.text()) == sum(path.stat().st_size for path in jobs.glob("*.json"))
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
