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
        def isolated_settings(namespace, parent):
            assert namespace == "Dialogs/JobRefresh"
            settings = QtCore.QSettings(str(jobs / "settings.ini"), QtCore.QSettings.IniFormat, parent)
            settings.setFallbacksEnabled(False)
            settings.beginGroup(namespace)
            return settings
        refresh.settings_group = isolated_settings
        preferences = refresh.JobRefreshDialog(window, jobs)
        assert preferences.worker_threads_spinbox.value() == 4
        preferences.worker_threads_spinbox.setValue(8)
        preferences.cancel_button.click()
        preferences.dialog_settings.sync()
        saved = QtCore.QSettings(str(jobs / "settings.ini"), QtCore.QSettings.IniFormat)
        assert saved.value("Dialogs/JobRefresh/worker_threads", type=int) == 8
        reopened = refresh.JobRefreshDialog(window, jobs, preserve_existing=True)
        assert reopened.worker_threads_spinbox.value() == 8
        reopened.worker_threads_spinbox.setValue(4)
        reopened.cancel_button.click()
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
        discovery_order = [path.stem for path in jobs.glob("*.json")]
        first_reads = threading.Barrier(4)
        read_lock = threading.Lock()
        active = 0
        peak_active = 0
        started_reads = 0
        def record_load(file):
            global active, peak_active, started_reads
            with read_lock:
                read_threads.add(threading.get_ident())
                active += 1
                peak_active = max(peak_active, active)
                started_reads += 1
                read_number = started_reads
            if read_number <= 4:
                first_reads.wait(10)
                if read_number == 1:
                    time.sleep(0.03)
            data = load(file)
            with read_lock:
                active -= 1
            return data

        dialog = refresh.JobRefreshDialog(window, jobs, "job-500")
        assert dialog.worker_threads_spinbox.value() == 4
        assert dialog.worker_threads_spinbox.minimum() == 1
        assert dialog.worker_threads_spinbox.maximum() == 64
        dialog.worker_threads_spinbox.setValue(4)
        dialog.show()
        app.processEvents()
        assert dialog.status_label.text() == ""
        assert dialog.worker_threads_spinbox.y() > dialog.progress_bar.geometry().bottom()
        assert dialog.start_button.y() == dialog.stop_button.y() == dialog.cancel_button.y()
        with patch.object(refresh.json, "load", side_effect=record_load):
            QtCore.QTimer.singleShot(0, dialog.start_button.click)
            assert dialog.exec() == QtWidgets.QDialog.Accepted
        assert window.jobQueueList.count() == 1001
        assert dialog.loaded_count == 1001
        assert peak_active == 4
        assert len(read_threads) == 4
        assert not dialog.worker_threads_spinbox.isEnabled()
        assert not dialog.start_button.isEnabled()
        assert dialog.progress_bar.value() == 1001
        assert dialog.progress_bar.format() == "%v / %m jobs loaded"
        assert [window.jobQueueList.item(i).data(JobDataRole.JobNameRole)
                for i in range(1001)] == discovery_order
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
        check.worker_threads_spinbox.setValue(4)
        with patch.object(refresh.json, "load", side_effect=new_only):
            QtCore.QTimer.singleShot(0, check.start_button.click)
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
            partial.worker_threads_spinbox.setValue(1)
            ticks = []
            timer = QtCore.QTimer()
            timer.timeout.connect(lambda: ticks.append(1))
            timer.start(1)
            with patch.object(refresh.json, "load", side_effect=slow_load):
                partial.show()
                partial.start_button.click()
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

        # Cancel with every pool thread inside a read. Nothing may be inserted
        # after cancellation, and the dialog must stay open until reads finish.
        for cancel_action in ("button", "escape", "close"):
            entered = threading.Event()
            release = threading.Event()
            reads = []
            def blocked_load(file):
                with read_lock:
                    reads.append(file.name)
                    if len(reads) == 4:
                        entered.set()
                assert release.wait(10)
                return load(file)
            parallel = refresh.JobRefreshDialog(window, jobs)
            parallel.worker_threads_spinbox.setValue(4)
            with patch.object(refresh.json, "load", side_effect=blocked_load):
                parallel.show()
                parallel.start_button.click()
                deadline = time.monotonic() + 10
                while not entered.is_set() and time.monotonic() < deadline:
                    app.processEvents()
                    QtTest.QTest.qWait(5)
                assert entered.is_set()
                assert window.jobQueueList.count() == 0
                if cancel_action == "button":
                    parallel.cancel_button.click()
                elif cancel_action == "escape":
                    QtTest.QTest.keyClick(parallel, QtCore.Qt.Key_Escape)
                else:
                    parallel.close()
                QtTest.QTest.qWait(30)
                assert parallel.isVisible()
                assert parallel.worker.isRunning()
                assert not parallel.cancel_button.isEnabled()
                release.set()
                deadline = time.monotonic() + 10
                while parallel.isVisible() and time.monotonic() < deadline:
                    app.processEvents()
                    QtTest.QTest.qWait(5)
            assert not parallel.isVisible()
            assert not parallel.worker.isRunning()
            assert parallel.result() == QtWidgets.QDialog.Rejected
            assert len(reads) == 4
            assert window.jobQueueList.count() == 0

        # Stop retains the dialog and partial rows; restart resets counts and
        # snapshots existing rows again so incremental refresh cannot duplicate them.
        for preserve_existing in (False, True):
            window.jobQueueList.clear()
            entered = threading.Event()
            release = threading.Event()
            reads = []
            def stop_load(file):
                reads.append(file.name)
                if len(reads) == 2:
                    entered.set()
                    assert release.wait(10)
                return load(file)
            stopped = refresh.JobRefreshDialog(window, jobs, preserve_existing=preserve_existing)
            assert not stopped.stop_button.isEnabled()
            stopped.worker_threads_spinbox.setValue(1)
            with patch.object(refresh.json, "load", side_effect=stop_load):
                stopped.show()
                stopped.start_button.click()
                deadline = time.monotonic() + 10
                while not entered.is_set() and time.monotonic() < deadline:
                    app.processEvents()
                    QtTest.QTest.qWait(5)
                assert entered.is_set()
                assert window.jobQueueList.count() == 1
                kept = window.jobQueueList.item(0)
                stopped.stop_button.click()
                assert stopped.worker.isInterruptionRequested()
                assert not stopped.start_button.isEnabled()
                assert not stopped.stop_button.isEnabled()
                assert not stopped.worker_threads_spinbox.isEnabled()
                assert stopped.cancel_button.isEnabled()
                release.set()
                deadline = time.monotonic() + 10
                while not stopped.start_button.isEnabled() and time.monotonic() < deadline:
                    app.processEvents()
                    QtTest.QTest.qWait(5)
            assert stopped.isVisible()
            assert not stopped.worker.isRunning()
            assert stopped.start_button.isEnabled()
            assert stopped.worker_threads_spinbox.isEnabled()
            assert window.jobQueueList.count() == 1
            assert stopped.loaded_count == 1
            assert len(reads) == 2
            stopped.worker_threads_spinbox.setValue(4)
            QtCore.QTimer.singleShot(0, stopped.start_button.click)
            assert stopped.exec() == QtWidgets.QDialog.Accepted
            assert not stopped.worker.isRunning()
            assert stopped.worker.worker_count == 4
            assert stopped.checked_count == 1000
            assert stopped.loaded_count == (999 if preserve_existing else 1000)
            names = [window.jobQueueList.item(i).data(JobDataRole.JobNameRole)
                     for i in range(window.jobQueueList.count())]
            assert len(names) == len(set(names)) == 1000
            if preserve_existing:
                assert window.jobQueueList.item(0) is kept

        window.jobQueueList.clear()
        retained = refresh.JobQueueListWidgetItem(QtCore.QFileInfo(str(retained_path)), payload)
        window.jobQueueList.addItem(retained)
        immediate = refresh.JobRefreshDialog(window, jobs)
        QtCore.QTimer.singleShot(0, immediate.reject)
        assert immediate.exec() == QtWidgets.QDialog.Rejected
        assert not immediate.worker.isRunning()
        assert window.jobQueueList.count() == 1
        assert window.jobQueueList.item(0) is retained
        empty = jobs / "empty"
        empty.mkdir()
        report = refresh.JobRefreshDialog(window, empty)
        QtCore.QTimer.singleShot(0, report.start_button.click)
        assert report.exec() == QtWidgets.QDialog.Accepted
        assert report.loaded_count == 0
        (empty / "invalid.json").write_text("{}", encoding="utf-8")
        errors = []
        def record_error(kind, value, traceback):
            errors.append((kind, value, threading.get_ident()))
        invalid = refresh.JobRefreshDialog(window, empty)
        with patch.object(sys, "excepthook", side_effect=record_error):
            QtCore.QTimer.singleShot(0, invalid.start_button.click)
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
