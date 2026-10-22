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
        def isolated_settings(namespace, parent):
            assert namespace == "Dialogs/JobSmartCheck"
            settings = QtCore.QSettings(str(root / "settings.ini"), QtCore.QSettings.IniFormat, parent)
            settings.setFallbacksEnabled(False)
            settings.beginGroup(namespace)
            return settings
        smart.settings_group = isolated_settings
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
            "use_job_name_for_output": True,
            "output_file_name": None,
            "restore_selected_face": False,
            "selected_media_id": "media",
            "target_medias_data": [{"media_id": "media", "media_path": str(media)}],
            "target_faces_data": {"face": {
                "assigned_input_faces": ["input"], "assigned_merged_embeddings": ["embed"]}},
            "input_faces_data": {"input": {"media_path": str(face)}},
            "embeddings_data": {"embed": {"embedding_name": "Saved", "embedding_store": {}}},
        }
        payloads = {"pass": valid, "same-assets": copy.deepcopy(valid)}
        payloads["same-assets"]["embeddings_data"]["unused"] = {
            "embedding_name": "Unused, & Extra", "embedding_store": {}}
        payloads["same-assets"]["embeddings_data"]["duplicate-name"] = {
            "embedding_name": "Unused, & Extra", "embedding_store": {}}
        payloads["same-assets"]["embeddings_data"]["library-only"] = {
            "embedding_name": "Library only", "embedding_store": {}}
        payloads["same-assets"]["target_faces_data"]["face"]["assigned_merged_embeddings"] += [
            "unused", "duplicate-name"]
        payloads["same-assets"]["target_faces_data"]["another-face"] = {
            "assigned_merged_embeddings": ["unused"]}
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

        validate = actions._validate_job_files_exist
        barrier = threading.Barrier(4)
        lock = threading.Lock()
        validation_threads = set()
        validation_count = 0
        def concurrent_validation(data):
            global validation_count
            with lock:
                validation_threads.add(threading.get_ident())
                validation_count += 1
                number = validation_count
            if number <= 4:
                barrier.wait(10)
            return validate(data)
        validation_patch = patch.object(actions, "_validate_job_files_exist", concurrent_validation)
        validation_patch.start()
        def wait_for_action(report):
            deadline = time.monotonic() + 15
            while report.action_worker is not None and time.monotonic() < deadline:
                app.processEvents()
                QtTest.QTest.qWait(5)
            assert report.action_worker is None

        dialog = smart.JobSmartCheckDialog(window, names)
        assert dialog.worker_threads_spinbox.value() == 4
        assert not dialog.worker_threads_spinbox.isEnabled()
        assert not dialog.restart_button.isEnabled()
        dialog.show()
        assert not dialog.remove_button.isEnabled()
        assert not dialog.close_button.isEnabled()
        assert set(dialog.state_filters) == {"Passed", "Failed"}
        assert all(checkbox.isChecked() for checkbox in dialog.state_filters.values())
        assert all(checkbox.text() == f"{state} (0)" for state, checkbox in dialog.state_filters.items())
        dialog.state_filters["Failed"].setChecked(False)
        wait_for_scan(dialog)
        validation_patch.stop()
        sequential = smart.JobSmartCheckWorker(window, names, window)
        with patch.object(smart.JobSmartCheckWorker, "_iter_checked_jobs", actions.JobProcessor._iter_checked_jobs):
            sequential.run()
        assert sequential.master_data == dialog.worker.master_data
        assert sequential.job_data_list == dialog.worker.job_data_list
        assert sequential.skipped_jobs == dialog.worker.skipped_jobs
        assert len(validation_threads) == 4
        assert threading.get_ident() not in validation_threads
        assert dialog.worker_threads_spinbox.isEnabled()
        assert dialog.restart_button.isEnabled()
        dialog.worker_threads_spinbox.setValue(8)
        dialog.dialog_settings.sync()
        persisted = QtCore.QSettings(str(root / "settings.ini"), QtCore.QSettings.IniFormat)
        assert persisted.value("Dialogs/JobSmartCheck/worker_threads", type=int) == 8
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
        assert set(dialog.failed_jobs) == set(names) - {"pass", "same-assets"}
        assert dialog.progress_bar.value() == 6
        assert "Media: 1" in dialog.assets_label.text()
        assert "Input faces: 1" in dialog.assets_label.text()
        assert "Embeddings: 2" in dialog.assets_label.text()
        assert "Target media file not found" in dialog.failed_jobs["missing-media"]
        assert "Input face file not found" in dialog.failed_jobs["missing-face"]
        assert "Required embedding ID" in dialog.failed_jobs["missing-embedding"]
        assert "read or parsed" in dialog.failed_jobs["broken-json"]
        assert dialog.remove_button.isEnabled()
        assert dialog.close_button.isEnabled()
        assert dialog.results.topLevelItemCount() == 6
        assert [dialog.results.headerItem().text(i) for i in range(8)] == [
            "Job", "Status", "Embedding name", "Embeddings", "FPS", "Frames", "Size", "Changed"]
        size_delegate = dialog.results.itemDelegateForColumn(6)
        for size, expected in (
            (0, "0 bytes"), (1023, "1023 bytes"), (1024, "1.00 KB"),
            (1536, "1.50 KB"), (1024 ** 2, "1.00 MB"),
            (1024 ** 3, "1.00 GB"), (1024 ** 4, "1.00 TB"),
        ):
            assert size_delegate.displayText(str(size), QtCore.QLocale()) == expected
        assert dialog.results.header().visualIndex(7) == 2
        rows = {dialog.results.topLevelItem(i).text(0): dialog.results.topLevelItem(i)
                for i in range(dialog.results.topLevelItemCount())}
        assert all(row.text(7) == "No" for row in rows.values())
        assert [rows["pass"].text(i) for i in range(2, 6)] == ["Saved", "1", "", ""]
        for name, row in rows.items():
            assert int(row.text(6)) == (jobs / f"{name}.json").stat().st_size
        assert dialog.total_bytes_label.text() == size_delegate.displayText(sum(
            (jobs / f"{name}.json").stat().st_size for name in names), dialog.locale())
        assert not dialog.remove_embeddings_button.isEnabled()
        assert not dialog.update_metadata_button.isEnabled()

        assert dialog.property_filters["Embeddings > 1"].text() == "Embeddings > 1 (1)"
        assert dialog.property_filters["Missing FPS"].text() == "Missing FPS (5)"
        assert dialog.property_filters["Missing Frames"].text() == "Missing Frames (5)"
        for states in product((False, True), repeat=2):
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

        assert set(dialog.embedding_filters) == {"Saved", "Unused, & Extra"}
        assert "Library only" not in dialog.embedding_filters
        assert rows["same-assets"].text(3) == "4"
        assert dialog.embedding_filters["Saved"].text() == "Saved (4)"
        assert dialog.embedding_filters["Unused, & Extra"].text() == "Unused, && Extra (1)"
        dialog.embedding_filters["Saved"].setChecked(False)
        assert {name for name, row in rows.items() if not row.isHidden()} == {"same-assets"}
        dialog.select_all_button.click()
        assert [row.text(0) for row in dialog.results.selectedItems()] == ["same-assets"]
        dialog.state_filters["Passed"].setChecked(False)
        assert all(row.isHidden() for row in rows.values())
        assert not dialog.results.selectedItems()
        dialog.state_filters["Passed"].setChecked(True)
        dialog.embedding_filters["Unused, & Extra"].setChecked(False)
        assert all(row.isHidden() for row in rows.values())
        for checkbox in dialog.embedding_filters.values():
            checkbox.setChecked(True)

        dialog.embedding_selection_buttons["none"].click()
        assert not any(checkbox.isChecked() for checkbox in dialog.embedding_filters.values())
        assert all(row.isHidden() for row in rows.values())
        dialog.embedding_selection_buttons["all"].click()
        assert all(checkbox.isChecked() for checkbox in dialog.embedding_filters.values())
        assert all(not row.isHidden() for row in rows.values())
        dialog.embedding_filters["Saved"].setChecked(False)
        dialog.embedding_selection_buttons["invert"].click()
        assert dialog.embedding_filters["Saved"].isChecked()
        assert not dialog.embedding_filters["Unused, & Extra"].isChecked()
        assert {name for name, row in rows.items() if not row.isHidden()} == {
            "pass", "same-assets", "missing-media", "missing-face"}
        dialog.embedding_selection_buttons["all"].click()

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
        cleanup_progress = []
        def record_cleanup_progress(value):
            if value > 0:
                cleanup_progress.append(value)
        dialog.progress_bar.valueChanged.connect(record_cleanup_progress)
        dialog.remove_embeddings_button.click()
        wait_for_action(dialog)
        dialog.progress_bar.valueChanged.disconnect(record_cleanup_progress)
        assert cleanup_progress == [1]
        assert dialog.progress_bar.maximum() == 1
        cleaned = json.loads((jobs / "pass.json").read_text())
        assert set(cleaned["embeddings_data"]) == {"embed", "second"}
        assert rows["pass"].text(3) == "2"
        assert rows["pass"].text(7) == "Yes"
        assert dialog.embedding_filters["Second"].text() == "Second (1)"
        assert rows["same-assets"].text(7) == "No"
        assert (jobs / "same-assets.json").read_bytes() == untouched
        rows["same-assets"].setSelected(True)
        metadata_progress = []
        def record_metadata_progress(value):
            if value > 0:
                metadata_progress.append(value)
        dialog.progress_bar.valueChanged.connect(record_metadata_progress)
        dialog.update_metadata_button.click()
        wait_for_action(dialog)
        dialog.progress_bar.valueChanged.disconnect(record_metadata_progress)
        assert metadata_progress == [1, 2]
        assert dialog.progress_bar.maximum() == 2
        for name, fps in (("pass", 30.0), ("same-assets", 25.0)):
            saved = json.loads((jobs / f"{name}.json").read_text())
            assert saved["target_medias_data"][0]["fps"] == fps
            assert saved["target_medias_data"][0]["frame_count"] == 10
            assert rows[name].text(4) == str(fps)
            assert rows[name].text(5) == "10"
            assert rows[name].text(7) == "Yes"
            assert int(rows[name].text(6)) == (jobs / f"{name}.json").stat().st_size
        assert dialog.total_bytes_label.text() == size_delegate.displayText(sum(
            (jobs / f"{name}.json").stat().st_size for name in names), dialog.locale())
        with patch.object(smart.cv2, "VideoCapture") as capture:
            dialog.update_metadata_button.click()
            wait_for_action(dialog)
            capture.assert_not_called()
        assert dialog.property_filters["Embeddings > 1"].text() == "Embeddings > 1 (2)"
        assert dialog.property_filters["Missing FPS"].text() == "Missing FPS (4)"
        assert dialog.property_filters["Missing Frames"].text() == "Missing Frames (4)"
        dialog.results.clearSelection()
        dialog.grab().save(str(root / "report.png"))

        def check_filters(report):
            metrics = report.metrics_label.text()
            for checked in product((False, True), repeat=2):
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
                assert partial.worker.worker_count == 8
                partial.show()
                deadline = time.monotonic() + 10
                while (not entered.is_set() or partial.checked_jobs != 1) and time.monotonic() < deadline:
                    app.processEvents()
                    QtTest.QTest.qWait(5)
                assert entered.is_set()
                assert partial.checked_jobs == 1
                assert partial.embedding_filters["Saved"].text() == "Saved (1)"
                assert partial.total_bytes_label.text() == size_delegate.displayText(
                    (jobs / "missing-media.json").stat().st_size, partial.locale())
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
                    wait_for_action(partial)
                    stopped_trash.assert_called_once_with(str(jobs / "missing-media.json"))
                assert partial.results.topLevelItemCount() == 0
                assert not partial.failed_jobs
                assert partial.checked_jobs == 0
                check_filters(partial)
                assert partial.restart_button.isEnabled()
                partial.worker_threads_spinbox.setValue(2)
                partial.restart_button.click()
                assert not partial.restart_button.isEnabled()
                assert not partial.worker_threads_spinbox.isEnabled()
                wait_for_scan(partial)
                assert partial.worker.worker_count == 2
                assert partial.checked_jobs == 6
                assert partial.results.topLevelItemCount() == 6
                partial.worker_threads_spinbox.setValue(8)
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
        removal_progress = []
        def record_removal_progress(completed):
            if completed > 0:
                removal_progress.append(completed)
                assert dialog.results.topLevelItemCount() == 6 - completed
                assert len(dialog.failed_jobs) == 4 - completed
        dialog.progress_bar.valueChanged.connect(record_removal_progress)
        with patch.object(smart, "send2trash", side_effect=trash):
            dialog.results.sortItems(1, QtCore.Qt.AscendingOrder)
            dialog.remove_button.click()
            wait_for_action(dialog)
        dialog.progress_bar.valueChanged.disconnect(record_removal_progress)
        assert removal_progress == [1, 2, 3, 4]
        assert dialog.results.topLevelItemCount() == 2
        assert {dialog.results.topLevelItem(i).text(0) for i in range(2)} == {"pass", "same-assets"}
        check_filters(dialog)
        assert set(trashed) == set(names) - {"pass", "same-assets"}
        assert not dialog.failed_jobs
        assert {path.stem for path in jobs.glob("*.json")} == {"pass", "same-assets"}
        assert {window.jobQueueList.item(i).data(JobDataRole.JobNameRole)
                for i in range(window.jobQueueList.count())} == {"pass", "same-assets"}
        assert media.exists() and face.exists()
        assert not dialog.remove_button.isEnabled()
        assert "Removed 4" in dialog.status_label.text()
        assert dialog.state_filters["Passed"].text() == "Passed (2)"
        assert dialog.state_filters["Failed"].text() == "Failed (0)"
        assert dialog.checked_jobs == 2
        assert dialog.progress_bar.value() == dialog.progress_bar.maximum() == 4
        assert set(dialog.worker.jobs) == {"pass", "same-assets"}
        assert dialog.total_bytes_label.text() == size_delegate.displayText(
            sum(path.stat().st_size for path in jobs.glob("*.json")), dialog.locale())
        # Restart a completed, edited report with a fresh directory scan.
        dialog.worker_threads_spinbox.setValue(2)
        dialog.restart_button.click()
        wait_for_scan(dialog)
        assert dialog.worker.worker_count == 2
        assert dialog.checked_jobs == dialog.passed_jobs == 2
        assert not dialog.failed_jobs
        assert dialog.results.topLevelItemCount() == 2
        assert dialog.changed_jobs == {"pass", "same-assets"}
        assert all(dialog.results.topLevelItem(i).text(7) == "Yes" for i in range(2))
        untouched_item = QtWidgets.QListWidgetItem("Unchanged")
        untouched_item.setData(JobDataRole.JobNameRole, "Unchanged")
        window.jobQueueList.addItem(untouched_item)
        before = {window.jobQueueList.item(i).data(JobDataRole.JobNameRole): window.jobQueueList.item(i)
                  for i in range(window.jobQueueList.count())}
        window.jobQueueList.setCurrentItem(before["pass"])
        with patch.object(smart, "JobQueueListWidgetItem", wraps=smart.JobQueueListWidgetItem) as reload_item, \
             patch.object(actions, "refresh_job_list", side_effect=AssertionError("No full refresh")), \
             patch.object(actions, "refresh_new_jobs", side_effect=AssertionError("No directory scan")):
            dialog.close_button.click()
        assert {Path(call.args[0].filePath()).stem for call in reload_item.call_args_list} == {"pass", "same-assets"}
        assert reload_item.call_count == 2
        assert before["pass"].data(JobDataRole.FrameRateRole) == 30.0
        assert before["same-assets"].data(JobDataRole.FrameCountRole) == 10
        assert window.jobQueueList.currentItem() is before["pass"]
        assert window.jobQueueList.currentItem().isSelected()
        assert all(window.jobQueueList.item(i) is before[window.jobQueueList.item(i).data(JobDataRole.JobNameRole)]
                   for i in range(window.jobQueueList.count()))
        assert not dialog.isVisible()

        for job_names in (["pass", "same-assets"], []):
            report = smart.JobSmartCheckDialog(window, job_names)
            report.show()
            wait_for_scan(report)
            assert not report.remove_button.isEnabled()
            assert report.passed_jobs == len(job_names)
            assert report.close_button.isEnabled()
            check_filters(report)
            if job_names:
                report.results.topLevelItem(0).setSelected(True)
                report.update_metadata_button.click()
                wait_for_action(report)
                assert report.results.topLevelItem(0).text(7) == "No"
                assert not report.changed_jobs
            with patch.object(smart, "JobQueueListWidgetItem") as reload_item:
                report.close()
                reload_item.assert_not_called()
        assert not (jobs / "completed").exists()
        resizing = smart.JobSmartCheckDialog(window, [])
        resizing.resize(1100, 800)
        resizing.show()
        wait_for_scan(resizing)
        embedding_names = [f"Embedding {index:03d}" for index in range(100)]
        resizing.receive_metadata("pass", ["Saved", "100", "25", "10", embedding_names])
        resizing.job_checked("pass", "")
        resizing.results.topLevelItem(0).setText(6, str(5 * 1024 ** 3))
        resizing.update_metrics()
        assert resizing.total_bytes_label.text() == "5.00 GB"
        QtTest.QTest.qWait(30)
        assert resizing.results_splitter.orientation() == QtCore.Qt.Vertical
        assert resizing.results_splitter.widget(1) is resizing.results
        narrow_columns = resizing.embedding_columns
        resizing.resize(1900, 800)
        QtTest.QTest.qWait(30)
        assert resizing.embedding_columns > narrow_columns
        resizing.resize(1100, 800)
        QtTest.QTest.qWait(30)
        assert resizing.embedding_columns == narrow_columns
        assert resizing.embedding_scroll.horizontalScrollBar().maximum() == 0
        resizing.results_splitter.setSizes([160, 440])
        QtTest.QTest.qWait(30)
        short_height = resizing.embedding_scroll.height()
        tall_jobs = resizing.results.height()
        resizing.results_splitter.setSizes([420, 180])
        QtTest.QTest.qWait(30)
        assert resizing.embedding_scroll.height() > short_height
        assert resizing.results.height() < tall_jobs
        group = resizing.results_splitter.widget(0)
        assert group.height() - resizing.embedding_scroll.height() < 100
        assert resizing.embedding_filter_layout.count() == 100
        resizing.results_splitter.setSizes([160, 440])
        QtTest.QTest.qWait(30)
        last_checkbox = resizing.embedding_filters[embedding_names[-1]]
        resizing.embedding_scroll.ensureWidgetVisible(last_checkbox)
        QtTest.QTest.qWait(30)
        assert resizing.embedding_scroll.verticalScrollBar().value() > 0
        assert last_checkbox.isChecked()
        resizing.grab().save(str(root / "resizable-report.png"))
        resizing.close()
        # Exercise each mutating action with two active workers and four jobs
        # still unsubmitted, then stop or close while disk work is blocked.
        for action, close_while_running in (
            ("remove", False), ("embeddings", False), ("metadata", False), ("metadata", True),
        ):
            action_root = root / f"action-{action}-{close_while_running}"
            action_jobs = action_root / "jobs"
            action_jobs.mkdir(parents=True)
            window.project_root_path = action_root
            window.jobQueueList.clear()
            action_names = [f"action-{i}" for i in range(6)]
            for name in action_names:
                data = copy.deepcopy(valid)
                data["embeddings_data"]["unused"] = {"embedding_name": "Unused", "embedding_store": {}}
                if action == "remove":
                    data["target_medias_data"][0]["media_path"] = str(root / "missing.mp4")
                path = action_jobs / f"{name}.json"
                path.write_text(json.dumps(data))
                item = smart.JobQueueListWidgetItem(QtCore.QFileInfo(str(path)), data)
                item.setData(JobDataRole.JobNameRole, name)
                window.jobQueueList.addItem(item)
            report = smart.JobSmartCheckDialog(window, action_names)
            report.show()
            wait_for_scan(report)
            report.worker_threads_spinbox.setValue(2)
            report.select_all_button.click()
            action_button = {
                "remove": report.remove_button,
                "embeddings": report.remove_embeddings_button,
                "metadata": report.update_metadata_button,
            }[action]
            entered = threading.Event()
            release = threading.Event()
            started = []
            worker_threads = set()
            process_job = smart.JobSmartActionWorker.process_job
            def blocked_action(worker, job_name):
                with lock:
                    started.append(job_name)
                    worker_threads.add(threading.get_ident())
                    if len(started) == 2:
                        entered.set()
                assert release.wait(10)
                return process_job(worker, job_name)
            progress = []
            report.progress_bar.valueChanged.connect(lambda value: progress.append(value))
            with patch.object(smart.JobSmartActionWorker, "process_job", blocked_action), \
                 patch.object(smart, "send2trash", side_effect=lambda path: Path(path).unlink()):
                action_button.click()
                deadline = time.monotonic() + 10
                while not entered.is_set() and time.monotonic() < deadline:
                    app.processEvents()
                    QtTest.QTest.qWait(5)
                assert entered.is_set()
                assert len(worker_threads) == 2
                assert threading.get_ident() not in worker_threads
                assert report.action_worker.worker_count == 2
                assert not report.restart_button.isEnabled()
                assert not report.close_button.isEnabled()
                assert not report.worker_threads_spinbox.isEnabled()
                assert not report.remove_embeddings_button.isEnabled()
                assert not report.update_metadata_button.isEnabled()
                assert report.stop_button.isEnabled()
                # The GUI event loop continues while both operations are blocked.
                ticks = []
                QtCore.QTimer.singleShot(0, lambda: ticks.append(True))
                QtTest.QTest.qWait(20)
                assert ticks
                if close_while_running:
                    report.close()
                else:
                    report.stop_button.click()
                assert report.isVisible()
                assert report.action_worker.isRunning()
                assert not report.stop_button.isEnabled()
                release.set()
                wait_for_action(report)
            assert len(started) == 2
            assert report.action_completed == 2
            assert [value for value in progress if value > 0] == [1, 2]
            if action == "remove":
                assert report.results.topLevelItemCount() == 4
                assert len(report.failed_jobs) == 4
                assert len(list(action_jobs.glob("*.json"))) == 4
                assert window.jobQueueList.count() == 4
            else:
                assert report.changed_jobs == (set() if close_while_running else set(started))
                for name in action_names:
                    data = json.loads((action_jobs / f"{name}.json").read_text())
                    if action == "embeddings":
                        assert ("unused" not in data["embeddings_data"]) == (name in started)
                    else:
                        assert ("fps" in data["target_medias_data"][0]) == (name in started)
            if close_while_running:
                assert not report.isVisible()
            else:
                assert report.isVisible()
                assert "Stopped" in report.status_label.text()
                assert report.restart_button.isEnabled()
                assert report.worker_threads_spinbox.isEnabled()
                # A stopped action can run again using an updated thread count.
                report.worker_threads_spinbox.setValue(3)
                with patch.object(smart, "send2trash", side_effect=lambda path: Path(path).unlink()):
                    action_button.click()
                    assert report.action_worker.worker_count == 3
                    wait_for_action(report)
                assert report.progress_bar.value() == report.progress_bar.maximum()
                if action == "remove":
                    assert not list(action_jobs.glob("*.json"))
                    assert report.results.topLevelItemCount() == 0
                report.close_button.click()
        print("PASS SMART scan and cleanup")
    """)
    result = subprocess.run(
        [sys.executable, "-u", "-", str(tmp_path), theme],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_SCALE_FACTOR": scale},
        input=script,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "PASS SMART scan and cleanup" in result.stdout
