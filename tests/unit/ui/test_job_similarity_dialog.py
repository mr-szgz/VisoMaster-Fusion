"""Cluster selection and the normal job-processing handoff using offscreen Qt."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


def test_similarity_preferences_survive_restart(tmp_path):
    script = textwrap.dedent("""
        import json
        from pathlib import Path
        import sys
        import time
        from PySide6 import QtCore, QtWidgets, QtTest
        from app.ui.widgets import job_similarity_dialog as similarity
        from app.ui.widgets.job_list_widgets import JobDataRole

        app = QtWidgets.QApplication([])
        root = Path(sys.argv[1])
        mode = sys.argv[2]
        def isolated_settings(namespace, parent):
            settings = QtCore.QSettings(str(root / "dialogs.ini"), QtCore.QSettings.IniFormat, parent)
            settings.setFallbacksEnabled(False)
            settings.beginGroup(namespace)
            return settings
        similarity.settings_group = isolated_settings
        window = QtWidgets.QWidget()
        window.project_root_path = root
        window.jobQueueList = QtWidgets.QListWidget(window)
        jobs_dir = root / "jobs"
        jobs_dir.mkdir(exist_ok=True)
        jobs = ["short", "long", "other"]
        names = ["A/B", "Other", "a/b"]
        durations = [30, 90, 100]
        if mode == "restore":
            jobs.append("new")
            names.append("New embedding")
            durations.append(90)
        for index, (job, name, duration) in enumerate(zip(jobs, names, durations)):
            item = QtWidgets.QListWidgetItem(job, window.jobQueueList)
            item.setData(JobDataRole.JobNameRole, job)
            item.setData(JobDataRole.EmbeddingNamesRole, [name])
            item.setData(JobDataRole.MediaTypeRole, "video")
            item.setData(JobDataRole.FrameCountRole, duration * 30)
            item.setData(JobDataRole.FrameRateRole, 30.0)
            data = {
                "control": {"strength": index},
                "target_faces_data": {job: {"parameters": {"SwapModelSelection": "Inswapper128"}}},
                "markers": {}, "job_marker_pairs": [], "dropped_frames": [],
                "swap_faces_enabled": True, "edit_faces_enabled": False,
            }
            (jobs_dir / f"{job}.json").write_text(json.dumps(data), encoding="utf-8")
        dialog = similarity.JobSimilarityDialog(window, jobs)
        assert dialog.dialog_settings.group() == "Dialogs/JobSimilarity"
        if mode == "save":
            assert dialog.cluster_limit.value() == 5
            assert not dialog.minimum_length_checkbox.isChecked()
            assert not dialog.maximum_length_checkbox.isChecked()
            dialog.cluster_limit.setValue(2)
            dialog.minimum_length.setText("00:01:00")
            dialog.maximum_length.setText("00:02:00")
            dialog.minimum_length_checkbox.setChecked(True)
            dialog.maximum_length_checkbox.setChecked(True)
            dialog.embedding_checkboxes["A/B"].setChecked(False)
            dialog.embedding_checkboxes["a/b"].setChecked(False)
            dialog.embedding_checkboxes["a/b"].setChecked(True)
        else:
            assert dialog.cluster_limit.value() == 2
            assert dialog.minimum_length.text() == "00:01:00"
            assert dialog.maximum_length.text() == "00:02:00"
            assert dialog.minimum_length_checkbox.isChecked()
            assert dialog.maximum_length_checkbox.isChecked()
            assert dialog.minimum_length.isEnabled()
            assert dialog.maximum_length.isEnabled()
            assert not dialog.embedding_checkboxes["A/B"].isChecked()
            assert dialog.embedding_checkboxes["a/b"].isChecked()
            assert dialog.embedding_checkboxes["New embedding"].isChecked()
            assert dialog.size() == QtCore.QSize(700, 720)
            assert dialog.results.columnWidth(0) == 210
            assert dialog.results.columnWidth(2) == 275
        dialog.show()
        deadline = time.monotonic() + 10
        while (dialog.check_timer.isActive() or dialog.checking) and time.monotonic() < deadline:
            app.processEvents()
            QtTest.QTest.qWait(5)
        assert not dialog.checking
        assert dialog.worker.completed
        assert dialog.worker.jobs == (["long", "other"] if mode == "save" else ["long", "other", "new"])
        assert dialog.results.topLevelItemCount() == 2
        assert not dialog.selected_jobs()
        assert not dialog.send_button.isEnabled()
        if mode == "save":
            dialog.resize(700, 720)
            dialog.results.setColumnWidth(0, 210)
            dialog.results.setColumnWidth(2, 275)
            app.processEvents()
            dialog.close()
            assert not dialog.isVisible()
            assert not dialog.closed
            assert dialog.dialog_settings.contains("geometry")
            assert dialog.dialog_settings.contains("columns")
            dialog.showNormal()
            dialog.reject()
            assert dialog.result() == QtWidgets.QDialog.Rejected
        else:
            dialog.items[1].setCheckState(0, QtCore.Qt.Checked)
            dialog.items[2].setCheckState(0, QtCore.Qt.Checked)
            dialog.send_button.click()
            assert dialog.jobs_to_process == ["long", "other"]
            assert dialog.result() == QtWidgets.QDialog.Accepted
            assert not dialog.isVisible()
        dialog.dialog_settings.sync()
    """)
    for mode in ("save", "restore"):
        result = subprocess.run(
            [sys.executable, "-u", "-c", script, str(tmp_path), mode],
            cwd=Path(__file__).resolve().parents[3],
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Traceback" not in result.stderr, result.stderr


@pytest.mark.parametrize("theme,scale", [("light", "1"), ("dark", "1.5")])
def test_similarity_clusters_and_processing_selection(tmp_path, theme, scale):
    script = textwrap.dedent("""
        import json
        from pathlib import Path
        import sys
        import time
        from unittest.mock import patch
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
        import qdarktheme
        from app.ui.core.main_window import Ui_MainWindow
        from app.ui.widgets.actions import job_manager_actions as actions
        from app.ui.widgets import job_similarity_dialog as similarity
        from app.ui.widgets.job_similarity_dialog import JobSimilarityDialog, JobSimilarityWorker
        from app.ui.widgets.job_list_widgets import JobDataRole

        app = QtWidgets.QApplication([])
        app.setFont(QtGui.QFont("Segoe UI", 10))
        app.setStyleSheet(qdarktheme.load_stylesheet(theme=sys.argv[2]))
        root = Path(sys.argv[1])
        def isolated_settings(namespace, parent):
            settings = QtCore.QSettings(str(root / "dialogs.ini"), QtCore.QSettings.IniFormat, parent)
            settings.beginGroup(namespace)
            settings.clear()
            return settings
        similarity.settings_group = isolated_settings
        jobs_dir = root / "jobs"
        jobs_dir.mkdir()
        window = QtWidgets.QMainWindow()
        ui = Ui_MainWindow()
        ui.setupUi(window)
        for name in ("jobQueueList", "buttonProcessAll", "buttonProcessSelected",
                     "buttonProcessSelectedSimilar", "buttonProcessAllSimilar", "buttonStopProcessing", "loadJobButton",
                     "deleteJobButton", "smartJobListButton", "checkNewJobListButton",
                     "refreshJobListButton", "addJobButton", "jobListLabelTemplateComboBox"):
            setattr(window, name, getattr(ui, name))
        window.project_root_path = root
        window.job_progress_dialog = None
        window.job_processing_button = None
        window.job_similarity_dialog = None
        window.job_similarity_button = None
        window.jobQueueList.clear()
        window.jobQueueList.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        actions.connect_job_manager_signals(window)
        actions.update_job_manager_buttons(window)
        assert not window.buttonProcessSelectedSimilar.isEnabled()
        assert not window.buttonProcessAllSimilar.isEnabled()

        names = ["A1", "B1", "C1", "D1", "E1", "F1", "G1", "B2", "A2", "C2", "B3", "A3", "B4", "B5", "B6"]
        payloads = {}
        for name in names:
            payloads[name] = {
                "control": {"ProvidersPrioritySelection": "TensorRT-Engine"},
                "target_faces_data": {"face-" + name: {"parameters": {
                    "SwapModelSelection": "AlphaFace" if name.startswith("C") else "Inswapper128", "StrengthAmountSlider": ord(name[0]),
                }, "embedding_store": {name: [len(name)]}}},
                "markers": {}, "job_marker_pairs": [], "dropped_frames": [],
                "swap_faces_enabled": True, "edit_faces_enabled": True,
                "target_medias_data": [{"media_path": name + ".mp4"}],
                "embeddings_data": {name: {"embedding_store": {name: [1]}}},
            }
            (jobs_dir / f"{name}.json").write_text(json.dumps(payloads[name]), encoding="utf-8")
            item = QtWidgets.QListWidgetItem(name)
            item.setData(JobDataRole.JobNameRole, name)
            item.setData(JobDataRole.EmbeddingNamesRole, ["Shared", "Embedding " + name[-1]])
            item.setData(JobDataRole.MediaTypeRole, "image" if name == "D1" else "video")
            item.setData(JobDataRole.FrameCountRole, 18015)
            item.setData(JobDataRole.FrameRateRole, 0.0 if name == "D1" else 30.0)
            if name == "B6":
                item.setData(JobDataRole.FrameRateRole, 60.0)
            if name == "F1":
                item.setData(JobDataRole.FrameCountRole, 18000)
            window.jobQueueList.addItem(item)
            item.setSelected(name.startswith(("A", "B")))
        selected_input = actions.get_selected_jobs(window)
        queue_names = [window.jobQueueList.item(i).data(JobDataRole.JobNameRole)
                       for i in range(window.jobQueueList.count())]
        assert window.buttonProcessSelected.text() == "Process (9)"
        assert window.buttonProcessSelectedSimilar.text() == "Process Similar (9)"
        with patch.object(actions, "prepare_similar_jobs") as prepare:
            window.buttonProcessSelectedSimilar.click()
            prepare.assert_called_once_with(window, selected_only=True)
            prepare.reset_mock()
            window.buttonProcessAllSimilar.click()
            prepare.assert_called_once_with(window, selected_only=False)

        def wait_for_check(dialog):
            deadline = time.monotonic() + 10
            while (dialog.check_timer.isActive() or dialog.checking) and time.monotonic() < deadline:
                app.processEvents()
                QtTest.QTest.qWait(5)
            assert not dialog.checking
            assert not dialog.worker.isRunning()
            assert dialog.worker.completed

        def forbidden(*args, **kwargs):
            raise AssertionError("Cluster review must not load or process jobs")
        with patch.object(actions, "start_job_processor", side_effect=forbidden), \
             patch.object(actions, "load_master_assets", side_effect=forbidden), \
             patch.object(actions, "load_job_settings", side_effect=forbidden):
            dialog = JobSimilarityDialog(window, names)
            dialog.show()
            wait_for_check(dialog)
            assert len(dialog.clusters) == 7
            assert sum(len(cluster["jobs"]) for cluster in dialog.clusters) == 15
            assert dialog.progress_bar.value() == 15
            assert dialog.cluster_limit.value() == 5
            assert list(dialog.items) == [2, 1, 3, 4, 5]
            assert [dialog.results.topLevelItem(i).text(1) for i in range(5)] == ["6", "3", "2", "1", "1"]
            assert dialog.results.topLevelItemCount() == 5
            assert [dialog.results.headerItem().text(i) for i in range(7)] == ["Cluster", "Jobs", "Job", "Embeddings", "Total length", "Average length", "Model"]
            assert dialog.items[2].text(6) == "Inswapper128"
            assert dialog.items[3].text(6) == "AlphaFace"
            assert dialog.items[3].toolTip(6) == "AlphaFace"
            assert dialog.items[2].text(2) == "B1"
            assert dialog.items[2].text(3) == "Shared, Embedding 1, Embedding 2, Embedding 3, Embedding 4, Embedding 5, Embedding 6"
            assert dialog.items[2].toolTip(3) == dialog.items[2].text(3)
            assert dialog.items[2].text(4) == "00:55:02"
            assert dialog.items[1].text(4) == "00:30:01"
            assert dialog.items[4].text(4) == "00:00:00"
            assert dialog.items[2].text(5) == "00:09:10"
            assert dialog.items[1].text(5) == "00:10:00"
            assert dialog.items[4].text(5) == "00:00:00"
            assert dialog.items[5].text(5) == dialog.items[5].text(4) == "00:10:00"
            assert "Showing 5 of 7 clusters" in dialog.metrics_label.text()
            assert dialog.selected_jobs() == []
            assert not dialog.send_button.isEnabled()
            assert dialog.send_button.text() == "Send"
            assert dialog.results.rootIsDecorated()
            for cluster in dialog.clusters:
                if cluster["id"] in dialog.items:
                    item = dialog.items[cluster["id"]]
                    assert not item.isExpanded()
                    assert [item.child(i).text(0) for i in range(item.childCount())] == cluster["jobs"]
                    for i in range(item.childCount()):
                        child = item.child(i)
                        assert child.flags() == QtCore.Qt.ItemIsEnabled
                        assert child.isFirstColumnSpanned()
                        assert child.data(0, QtCore.Qt.CheckStateRole) is None
            dialog.items[2].setExpanded(True)
            app.processEvents()
            assert dialog.items[2].isExpanded()
            assert dialog.selected_jobs() == []
            assert not dialog.send_button.isEnabled()
            clusters = dialog.clusters
            with patch.object(JobSimilarityWorker, "start", side_effect=forbidden):
                dialog.cluster_limit.setValue(7)
                assert dialog.items[2].isExpanded()
                assert list(dialog.items) == [2, 1, 3, 4, 5, 6, 7]
                dialog.items[7].setCheckState(0, QtCore.Qt.Checked)
                dialog.cluster_limit.setValue(5)
                assert dialog.selected_jobs() == []
                assert not dialog.send_button.isEnabled()
                dialog.cluster_limit.setValue(7)
                assert dialog.items[7].checkState(0) == QtCore.Qt.Unchecked
                dialog.items[7].setCheckState(0, QtCore.Qt.Checked)
                dialog.items[2].setCheckState(0, QtCore.Qt.Checked)
                assert dialog.items[7].checkState(0) == QtCore.Qt.Checked
                assert dialog.selected_jobs() == [name for name in names if name.startswith(("B", "G"))]
                dialog.cluster_limit.setValue(5)
                assert dialog.selected_jobs() == [name for name in names if name.startswith("B")]
                dialog.cluster_limit.setValue(7)
                assert dialog.items[7].checkState(0) == QtCore.Qt.Unchecked
                dialog.cluster_limit.setValue(1)
                assert list(dialog.items) == [2]
                assert dialog.selected_jobs() == [name for name in names if name.startswith("B")]
                dialog.cluster_limit.setValue(5)
                assert dialog.items[2].checkState(0) == QtCore.Qt.Checked
            assert dialog.clusters is clusters
            dialog.items[1].setCheckState(0, QtCore.Qt.Checked)
            assert dialog.items[2].checkState(0) == QtCore.Qt.Checked
            assert dialog.selected_jobs() == [name for name in names if name.startswith(("A", "B"))]
            dialog.items[1].setCheckState(0, QtCore.Qt.Unchecked)
            assert dialog.selected_jobs() == [name for name in names if name.startswith("B")]
            assert dialog.send_button.isEnabled()
            dialog.items[2].setCheckState(0, QtCore.Qt.Unchecked)
            assert dialog.selected_jobs() == []
            assert not dialog.send_button.isEnabled()
            dialog.items[3].setCheckState(0, QtCore.Qt.Checked)
            assert dialog.items[1].checkState(0) == QtCore.Qt.Unchecked
            dialog.items[1].setCheckState(0, QtCore.Qt.Checked)
            expected = [name for name in names if name.startswith(("A", "C"))]
            assert dialog.selected_jobs() == expected
            assert dialog.send_button.isEnabled()
            dialog.items[3].setExpanded(True)
            dialog.results.setCurrentItem(dialog.items[2].child(0))
            QtTest.QTest.keyClick(dialog.results, QtCore.Qt.Key_Space)
            assert not dialog.items[2].child(0).isSelected()
            assert dialog.items[2].child(0).data(0, QtCore.Qt.CheckStateRole) is None
            assert dialog.selected_jobs() == expected
            assert dialog.items[3].checkState(0) == QtCore.Qt.Checked
            assert dialog.items[2].checkState(0) == QtCore.Qt.Unchecked

            # Send uses the checked clusters, without rereading or starting a worker.
            payloads["C2"]["control"]["ProvidersPrioritySelection"] = "CUDA"
            (jobs_dir / "C2.json").write_text(json.dumps(payloads["C2"]), encoding="utf-8")
            worker = dialog.worker
            with patch.object(JobSimilarityWorker, "start", side_effect=forbidden), \
                 patch.object(Path, "open", side_effect=forbidden):
                dialog.send_button.click()
            assert dialog.jobs_to_process == expected
            assert dialog.worker is worker
            assert dialog.result() == QtWidgets.QDialog.Accepted
            assert not dialog.isVisible()

            single = JobSimilarityDialog(window, ["D1"])
            single.show()
            wait_for_check(single)
            assert not single.embedding_filters.findChildren(QtWidgets.QScrollArea)
            assert single.embedding_filters.layout().rowCount() == 1
            assert single.embedding_filters.sizePolicy().verticalPolicy() == QtWidgets.QSizePolicy.Fixed
            first, second = single.embedding_checkboxes.values()
            single.resize(1800, 700)
            app.processEvents()
            assert first.y() == second.y()
            assert second.x() - first.geometry().right() < first.width()
            assert single.embedding_filters.height() == single.embedding_filters.sizeHint().height()
            single.items[1].setCheckState(0, QtCore.Qt.Checked)
            assert single.send_button.isEnabled()
            single.send_button.click()
            wait_for_check(single)
            assert single.jobs_to_process == ["D1"]
            assert single.result() == QtWidgets.QDialog.Accepted

            filtered = JobSimilarityDialog(window, names)
            filtered.show()
            wait_for_check(filtered)
            assert list(filtered.embedding_checkboxes) == ["Shared"] + ["Embedding " + str(i) for i in range(1, 7)]
            assert all(checkbox.isChecked() for checkbox in filtered.embedding_checkboxes.values())
            assert filtered.rerun_button.text() == "Rerun"
            filtered.items[2].setCheckState(0, QtCore.Qt.Checked)
            filtered.items[1].setCheckState(0, QtCore.Qt.Checked)
            for name, checkbox in filtered.embedding_checkboxes.items():
                checkbox.setChecked(name in ("Embedding 2", "Embedding 3"))
            assert len(filtered.clusters) == 8
            filtered.rerun_button.click()
            assert filtered.checking
            assert not filtered.rerun_button.isEnabled()
            assert not filtered.embedding_filters.isEnabled()
            assert not filtered.send_button.isEnabled()
            assert not filtered.jobs_to_process
            wait_for_check(filtered)
            assert filtered.worker.jobs == ["B2", "A2", "C2", "B3", "A3"]
            assert [cluster["jobs"] for cluster in filtered.clusters] == [["B2", "B3"], ["A2", "A3"], ["C2"]]
            assert "3 clusters · 5 jobs" in filtered.metrics_label.text()
            assert filtered.progress_bar.value() == 5
            assert filtered.items[1].text(4) == "00:20:01"
            assert filtered.items[1].text(5) == "00:10:00"
            assert filtered.items[1].childCount() == 2
            assert not filtered.selected_jobs()
            assert not filtered.send_button.isEnabled()
            assert len(filtered.embedding_checkboxes) == 7
            for checkbox in filtered.embedding_checkboxes.values():
                checkbox.setChecked(False)
            filtered.rerun_button.click()
            wait_for_check(filtered)
            assert not filtered.clusters
            assert filtered.results.topLevelItemCount() == 0
            assert filtered.progress_bar.maximum() == 1
            assert not filtered.send_button.isEnabled()
            assert filtered.rerun_button.isEnabled()
            assert filtered.status_label.text() == "No jobs match the filters."
            filtered.embedding_checkboxes["Embedding 2"].setChecked(True)
            filtered.rerun_button.click()
            wait_for_check(filtered)
            assert filtered.worker.jobs == ["B2", "A2", "C2"]
            filtered.items[2].setCheckState(0, QtCore.Qt.Checked)
            filtered.send_button.click()
            assert filtered.jobs_to_process == ["A2"]
            assert not filtered.isVisible()
            assert filtered.result() == QtWidgets.QDialog.Accepted

            unassigned = JobSimilarityDialog(window, ["D1"])
            unassigned.job_details["D1"] = ([], 0)
            for checkbox in unassigned.embedding_checkboxes.values():
                checkbox.setChecked(False)
            unassigned.show()
            wait_for_check(unassigned)
            assert unassigned.worker.jobs == ["D1"]
            unassigned.reject()

            lengths = JobSimilarityDialog(window, names)
            lengths.show()
            wait_for_check(lengths)
            assert not lengths.minimum_length_checkbox.isChecked()
            assert not lengths.maximum_length_checkbox.isChecked()
            assert not lengths.minimum_length.isEnabled()
            assert not lengths.maximum_length.isEnabled()
            lengths.minimum_length_checkbox.setChecked(True)
            assert lengths.minimum_length.isEnabled()
            lengths.minimum_length.selectAll()
            QtTest.QTest.keyClicks(lengths.minimum_length, "001000")
            assert lengths.minimum_length.text() == "00:10:00"
            assert len(lengths.worker.jobs) == 15
            lengths.rerun_button.click()
            assert not lengths.length_filters.isEnabled()
            wait_for_check(lengths)
            assert lengths.worker.jobs == [name for name in names if name not in ("D1", "B6")]
            lengths.maximum_length_checkbox.setChecked(True)
            lengths.maximum_length.selectAll()
            QtTest.QTest.keyClicks(lengths.maximum_length, "001000")
            assert lengths.maximum_length.text() == "00:10:00"
            lengths.rerun_button.click()
            wait_for_check(lengths)
            assert lengths.worker.jobs == ["F1"]
            lengths.minimum_length_checkbox.setChecked(False)
            assert not lengths.minimum_length.isEnabled()
            lengths.rerun_button.click()
            wait_for_check(lengths)
            assert lengths.worker.jobs == ["D1", "F1", "B6"]
            lengths.minimum_length_checkbox.setChecked(True)
            lengths.maximum_length.selectAll()
            QtTest.QTest.keyClicks(lengths.maximum_length, "001001")
            for name, checkbox in lengths.embedding_checkboxes.items():
                checkbox.setChecked(name == "Embedding 2")
            lengths.rerun_button.click()
            wait_for_check(lengths)
            assert lengths.worker.jobs == ["B2", "A2", "C2"]
            lengths.minimum_length.selectAll()
            QtTest.QTest.keyClicks(lengths.minimum_length, "250000")
            assert lengths.minimum_length.text() == "25:00:00"
            lengths.rerun_button.click()
            wait_for_check(lengths)
            assert not lengths.clusters
            assert not lengths.send_button.isEnabled()
            lengths.minimum_length_checkbox.setChecked(False)
            lengths.rerun_button.click()
            wait_for_check(lengths)
            assert lengths.worker.jobs == ["B2", "A2", "C2"]
            lengths.items[1].setCheckState(0, QtCore.Qt.Checked)
            lengths.items[2].setCheckState(0, QtCore.Qt.Checked)
            lengths.send_button.click()
            assert lengths.jobs_to_process == ["B2", "A2"]
            assert not lengths.isVisible()

            # Cancel sends nothing, both after checking and while the scan is running.
            cancelled = JobSimilarityDialog(window, names)
            cancelled.show()
            wait_for_check(cancelled)
            cancelled.items[2].setCheckState(0, QtCore.Qt.Checked)
            cancelled.reject()
            app.processEvents()
            assert not cancelled.worker.isRunning()
            assert cancelled.result() == QtWidgets.QDialog.Rejected
            assert not cancelled.jobs_to_process
            assert not cancelled.isVisible()
            loading = JobSimilarityDialog(window, names)
            loading.check_jobs()
            loading.reject()
            app.processEvents()
            assert not loading.worker.isRunning()
            assert loading.result() == QtWidgets.QDialog.Rejected
            assert not loading.jobs_to_process
            early = JobSimilarityDialog(window, names)
            early.reject()
            app.processEvents()
            assert not early.check_timer.isActive()
            assert early.worker is None

        # Exercise the non-modal review, reopening it before the normal handoff.
        for selected_only in (True, False):
            for send in (True, False):
                input_jobs = selected_input if selected_only else queue_names
                chosen_letters = ("A", "B") if selected_only else ("B", "C")
                expected = [name for name in input_jobs if name.startswith(chosen_letters) and name.endswith("2")]
                reviews = []
                class ReviewDialog(JobSimilarityDialog):
                    def __init__(self, parent, jobs):
                        super().__init__(parent, jobs)
                        assert jobs == input_jobs
                        self.reran = False
                        reviews.append(self)
                    def check_finished(self):
                        super().check_finished()
                        assert not self.isModal()
                        assert self.windowFlags() & QtCore.Qt.WindowMinimizeButtonHint
                        assert window.job_similarity_dialog is self
                        origin = window.buttonProcessSelectedSimilar if selected_only else window.buttonProcessAllSimilar
                        assert origin.isEnabled()
                        assert origin.isChecked()
                        assert not window.buttonProcessAll.isEnabled()
                        assert not window.buttonProcessSelected.isEnabled()
                        assert not window.deleteJobButton.isEnabled()
                        assert not window.loadJobButton.isEnabled()
                        self.items[1].setCheckState(0, QtCore.Qt.Checked)
                        self.items[2].setCheckState(0, QtCore.Qt.Checked)
                        self.items[1].setExpanded(True)
                        worker = self.worker
                        self.showMinimized()
                        app.processEvents()
                        assert self.isMinimized()
                        with patch.object(JobSimilarityWorker, "start", side_effect=forbidden):
                            origin.click()
                        assert window.job_similarity_dialog is self
                        assert self.worker is worker
                        assert not self.isMinimized()
                        assert self.items[1].isExpanded()
                        assert self.items[1].checkState(0) == QtCore.Qt.Checked
                        assert self.items[2].checkState(0) == QtCore.Qt.Checked
                        self.close()
                        assert not self.isVisible()
                        assert not self.closed
                        origin.click()
                        assert self.isVisible()
                        assert origin.isChecked()
                        assert self.items[1].isExpanded()
                        checked_jobs = set(self.clusters[0]["jobs"] + self.clusters[1]["jobs"])
                        assert self.selected_jobs() == [job for job in input_jobs if job in checked_jobs]
                        if send:
                            if not self.reran:
                                for name, checkbox in self.embedding_checkboxes.items():
                                    checkbox.setChecked(name == "Embedding 2")
                                self.minimum_length_checkbox.setChecked(True)
                                self.minimum_length.setText("00:10:00")
                                self.maximum_length_checkbox.setChecked(True)
                                self.maximum_length.setText("00:10:01")
                                self.reran = True
                                self.rerun_button.click()
                                return
                            for item in self.items.values():
                                item.setCheckState(0, QtCore.Qt.Unchecked)
                            for cluster in self.clusters:
                                if cluster["representative_job"].startswith(chosen_letters):
                                    self.items[cluster["id"]].setCheckState(0, QtCore.Qt.Checked)
                            self.send_button.click()
                        else:
                            self.reject()
                def process(parent, jobs_to_process, processing_button):
                    assert parent is window
                    assert jobs_to_process == expected
                    assert not reviews[0].isVisible()
                    assert reviews[0].result() == QtWidgets.QDialog.Accepted
                    assert window.job_similarity_dialog is None
                    assert window.job_similarity_button is None
                    assert actions.get_selected_jobs(window) == selected_input
                    assert processing_button is (window.buttonProcessSelectedSimilar if selected_only else window.buttonProcessAllSimilar)
                with patch.object(similarity, "JobSimilarityDialog", ReviewDialog), \
                     patch.object(actions, "start_job_processor", side_effect=process) as processor:
                    actions.prepare_similar_jobs(window, selected_only)
                    assert processor.call_count == int(send)
                    assert window.job_similarity_dialog is None
                    assert window.buttonProcessAll.isEnabled()
                    assert window.buttonProcessSelected.isEnabled()
                    origin = window.buttonProcessSelectedSimilar if selected_only else window.buttonProcessAllSimilar
                    assert not origin.isCheckable()
                app.processEvents()
        assert set(path.stem for path in jobs_dir.glob("*.json")) == set(names)
        assert not (jobs_dir / "completed").exists()
        print("PASS cluster review and handoff")
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
    assert "PASS cluster review and handoff" in result.stdout
