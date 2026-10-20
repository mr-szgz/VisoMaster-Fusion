"""Cluster selection and the normal job-processing handoff using offscreen Qt."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


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
                    "SwapModelSelection": "Inswapper128", "StrengthAmountSlider": ord(name[0]),
                }, "embedding_store": {name: [len(name)]}}},
                "markers": {}, "job_marker_pairs": [], "dropped_frames": [],
                "swap_faces_enabled": True, "edit_faces_enabled": True,
                "target_medias_data": [{"media_path": name + ".mp4"}],
                "embeddings_data": {name: {"embedding_store": {name: [1]}}},
            }
            (jobs_dir / f"{name}.json").write_text(json.dumps(payloads[name]), encoding="utf-8")
            item = QtWidgets.QListWidgetItem(name)
            item.setData(JobDataRole.JobNameRole, name)
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
            assert "Showing 5 of 7 clusters" in dialog.metrics_label.text()
            assert dialog.selected_jobs() == []
            assert not dialog.send_button.isEnabled()
            assert dialog.send_button.text() == "Send"
            clusters = dialog.clusters
            with patch.object(JobSimilarityWorker, "start", side_effect=forbidden):
                dialog.cluster_limit.setValue(7)
                assert list(dialog.items) == [2, 1, 3, 4, 5, 6, 7]
                dialog.items[7].setCheckState(0, QtCore.Qt.Checked)
                dialog.cluster_limit.setValue(5)
                assert dialog.selected_jobs() == []
                assert not dialog.send_button.isEnabled()
                dialog.cluster_limit.setValue(7)
                assert dialog.items[7].checkState(0) == QtCore.Qt.Unchecked
                dialog.items[7].setCheckState(0, QtCore.Qt.Checked)
                dialog.items[2].setCheckState(0, QtCore.Qt.Checked)
                assert dialog.items[7].checkState(0) == QtCore.Qt.Unchecked
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
            assert dialog.items[2].checkState(0) == QtCore.Qt.Unchecked
            assert dialog.selected_jobs() == [name for name in names if name.startswith("A")]
            dialog.items[1].setCheckState(0, QtCore.Qt.Unchecked)
            assert dialog.selected_jobs() == []
            assert not dialog.send_button.isEnabled()
            dialog.items[3].setCheckState(0, QtCore.Qt.Checked)
            assert dialog.items[1].checkState(0) == QtCore.Qt.Unchecked
            expected = [name for name in names if name.startswith("C")]
            assert dialog.selected_jobs() == expected
            assert dialog.send_button.isEnabled()

            # Send uses the calculated cluster, without rereading or starting a worker.
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
            single.items[1].setCheckState(0, QtCore.Qt.Checked)
            assert single.send_button.isEnabled()
            single.send_button.click()
            wait_for_check(single)
            assert single.jobs_to_process == ["D1"]
            assert single.result() == QtWidgets.QDialog.Accepted

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
            assert not hasattr(early, "worker")

        # Exercise the real modal review and intercept only the normal processor.
        for selected_only in (True, False):
            for send in (True, False):
                input_jobs = selected_input if selected_only else queue_names
                chosen_letters = ("A",) if selected_only else ("B",)
                expected = [name for name in input_jobs if name.startswith(chosen_letters)]
                reviews = []
                class ReviewDialog(JobSimilarityDialog):
                    def __init__(self, parent, jobs):
                        super().__init__(parent, jobs)
                        assert jobs == input_jobs
                        reviews.append(self)
                    def check_finished(self):
                        super().check_finished()
                        if send:
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
                    assert actions.get_selected_jobs(window) == selected_input
                    assert processing_button is (window.buttonProcessSelectedSimilar if selected_only else window.buttonProcessAllSimilar)
                with patch.object(similarity, "JobSimilarityDialog", ReviewDialog), \
                     patch.object(actions, "start_job_processor", side_effect=process) as processor:
                    actions.prepare_similar_jobs(window, selected_only)
                    assert processor.call_count == int(send)
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
