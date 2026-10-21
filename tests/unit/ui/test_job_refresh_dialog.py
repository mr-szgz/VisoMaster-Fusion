import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_incremental_refresh_and_cancel(tmp_path):
    script = textwrap.dedent("""
        import json
        import sys
        import threading
        import time
        from pathlib import Path
        from unittest.mock import patch
        from PySide6 import QtCore, QtWidgets, QtTest
        from app.ui.widgets import job_refresh_dialog as refresh
        from app.ui.widgets.job_list_widgets import JobDataRole

        app = QtWidgets.QApplication([])
        window = QtWidgets.QMainWindow()
        window.jobQueueList = QtWidgets.QListWidget(window)
        window.jobListLabelTemplateComboBox = QtWidgets.QComboBox(window)
        window.jobListLabelTemplateComboBox.addItem("{job_name}")
        window.jobsManagerSearchBox = QtWidgets.QLineEdit(window)
        jobs = Path(sys.argv[1])
        payload = {
            "use_job_name_for_output": True, "output_file_name": None,
            "restore_selected_face": False, "selected_media_id": "target",
            "target_medias_data": [{"media_id": "target", "media_path": "missing.mp4"}],
            "target_faces_data": {}, "embeddings_data": {},
        }
        for index in range(1001):
            (jobs / f"job-{index}.json").write_text(json.dumps(payload), encoding="utf-8")

        main_thread = threading.get_ident()
        read_threads = set()
        load = json.load
        def record_load(file):
            read_threads.add(threading.get_ident())
            return load(file)

        dialog = refresh.JobRefreshDialog(window, jobs, "job-500")
        with patch.object(refresh.json, "load", side_effect=record_load):
            assert dialog.exec() == QtWidgets.QDialog.Accepted
        assert window.jobQueueList.count() == 1001
        assert dialog.loaded_count == 1001
        assert window.jobQueueList.currentItem().data(JobDataRole.JobNameRole) == "job-500"
        assert read_threads and main_thread not in read_threads
        assert not dialog.worker.isRunning()
        assert not dialog.isVisible()

        retained = window.jobQueueList.currentItem()
        retained_path = jobs / "job-500.json"
        retained_path.write_text("existing jobs must not be parsed again", encoding="utf-8")
        for index in (0, 1, 2):
            (jobs / f"job-{index}.json").unlink()
        for index in (1001, 1002):
            (jobs / f"job-{index}.json").write_text(json.dumps(payload), encoding="utf-8")
        reads = []
        def new_only(file):
            assert threading.get_ident() != main_thread
            reads.append(Path(file.name).stem)
            return load(file)
        check = refresh.JobRefreshDialog(window, jobs, preserve_existing=True)
        with patch.object(refresh.json, "load", side_effect=new_only):
            assert check.exec() == QtWidgets.QDialog.Accepted
        assert set(reads) == {"job-1001", "job-1002"}
        assert check.loaded_count == 2
        assert check.checked_count == 1003
        assert window.jobQueueList.count() == 1000
        assert window.jobQueueList.currentItem() is retained
        assert all(window.jobQueueList.item(i).data(JobDataRole.JobNameRole)
                   not in {"job-0", "job-1", "job-2"} for i in range(1000))
        retained_path.write_text(json.dumps(payload), encoding="utf-8")

        for cancel_action in ("button", "escape", "close", "preserve"):
            window.jobQueueList.clear()
            if cancel_action == "preserve":
                retained = refresh.JobQueueListWidgetItem(QtCore.QFileInfo(str(retained_path)), payload)
                retained.setData(JobDataRole.JobNameRole, "job-500")
                window.jobQueueList.addItem(retained)
                window.jobQueueList.setCurrentItem(retained)
            entered = threading.Event()
            release = threading.Event()
            reads = []
            def slow_load(file):
                reads.append(file.name)
                if len(reads) == 2:
                    entered.set()
                    assert release.wait(10)
                return load(file)

            partial = refresh.JobRefreshDialog(window, jobs, preserve_existing=cancel_action == "preserve")
            ticks = []
            timer = QtCore.QTimer()
            timer.timeout.connect(lambda: ticks.append(1))
            timer.start(1)
            with patch.object(refresh.json, "load", side_effect=slow_load):
                partial.show()
                deadline = time.monotonic() + 10
                while not entered.is_set() and time.monotonic() < deadline:
                    app.processEvents()
                    QtTest.QTest.qWait(5)
                assert entered.is_set()
                expected_count = 2 if cancel_action == "preserve" else 1
                assert window.jobQueueList.count() == expected_count
                retained_name = window.jobQueueList.item(0).data(JobDataRole.JobNameRole)
                tick_count = len(ticks)
                QtTest.QTest.qWait(30)
                assert len(ticks) > tick_count
                if cancel_action in ("button", "preserve"):
                    partial.cancel_button.click()
                elif cancel_action == "escape":
                    QtTest.QTest.keyClick(partial, QtCore.Qt.Key_Escape)
                else:
                    partial.close()
                assert partial.worker.isInterruptionRequested()
                release.set()
                deadline = time.monotonic() + 10
                while partial.isVisible() and time.monotonic() < deadline:
                    app.processEvents()
                    QtTest.QTest.qWait(5)
            timer.stop()
            assert not partial.isVisible()
            assert not partial.worker.isRunning()
            assert len(reads) == 2
            assert window.jobQueueList.count() == expected_count
            assert window.jobQueueList.item(0).data(JobDataRole.JobNameRole) == retained_name
            if cancel_action == "preserve":
                assert window.jobQueueList.currentItem() is retained

        immediate = refresh.JobRefreshDialog(window, jobs)
        immediate.reject()
        assert immediate.exec() == QtWidgets.QDialog.Rejected
        assert not immediate.worker.isRunning()
        assert window.jobQueueList.count() == 2
        empty = jobs / "empty"
        empty.mkdir()
        report = refresh.JobRefreshDialog(window, empty)
        assert report.exec() == QtWidgets.QDialog.Accepted
        assert report.loaded_count == 0
        (empty / "invalid.json").write_text("{}", encoding="utf-8")
        errors = []
        def record_error(kind, value, traceback):
            errors.append((kind, value, threading.get_ident()))
        invalid = refresh.JobRefreshDialog(window, empty)
        with patch.object(sys, "excepthook", side_effect=record_error):
            invalid.exec()
        assert len(errors) == 1
        assert errors[0][0] is KeyError
        assert errors[0][2] != main_thread
        assert not invalid.worker.isRunning()
        assert invalid.loaded_count == 0
    """)
    result = subprocess.run(
        [sys.executable, "-u", "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
