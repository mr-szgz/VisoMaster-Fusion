import json
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from PySide6 import QtCore, QtWidgets

from app.settings import settings_group
from app.ui.widgets.job_list_widgets import JobDataRole, JobQueueListWidgetItem


class JobRefreshWorker(QtCore.QThread):
    scan_started = QtCore.Signal(int)
    job_loaded = QtCore.Signal(str, object)
    existing_checked = QtCore.Signal(str, bool)

    def __init__(self, jobs_dir, parent, existing_names=(), worker_count=4):
        super().__init__(parent)
        self.jobs_dir = jobs_dir
        self.worker_count = worker_count
        self.item_added = QtCore.QSemaphore()
        self.existing_names = set(existing_names)

    def run(self):
        paths = list(self.jobs_dir.glob("*.json"))
        paths = [path for path in paths if path.stem not in self.existing_names]
        self.scan_started.emit(len(paths) + len(self.existing_names))
        with ThreadPoolExecutor(max_workers=self.worker_count) as executor:
            for inputs, task, signal in (
                (list(self.existing_names), self.check_existing, self.existing_checked),
                (paths, self.load_job, self.job_loaded),
            ):
                pending = deque()
                submitted = 0
                while pending or submitted < len(inputs):
                    if self.isInterruptionRequested():
                        for future in pending:
                            future.cancel()
                        for future in pending:
                            if not future.cancelled():
                                future.result()
                        return
                    while len(pending) < self.worker_count and submitted < len(inputs):
                        pending.append(executor.submit(task, inputs[submitted]))
                        submitted += 1
                    result = pending.popleft().result()
                    if not self.isInterruptionRequested():
                        signal.emit(*result)
                        # Only the coordinator waits for GUI insertion; pool tasks keep reading.
                        self.item_added.acquire()

    def check_existing(self, job_name):
        return job_name, (self.jobs_dir / f"{job_name}.json").exists()

    def load_job(self, path):
        with open(path, encoding="utf-8") as job_file:
            data = json.load(job_file)
        return path.stem, JobQueueListWidgetItem(QtCore.QFileInfo(str(path)), data)


class JobRefreshDialog(QtWidgets.QDialog):
    """Display incremental refresh progress until completion or cancellation."""

    def __init__(self, main_window, jobs_dir, selected_job_name=None, preserve_existing=False):
        super().__init__(main_window)
        self.main_window = main_window
        self.selected_job_name = selected_job_name
        self.cancelled = False
        self.started = False
        self.stop_requested = False
        self.preserve_existing = preserve_existing
        self.loaded_count = 0
        self.checked_count = 0
        self.existing_items = {}
        self.setWindowTitle("Loading Jobs")
        self.setMinimumWidth(380)
        layout = QtWidgets.QVBoxLayout(self)
        options = QtWidgets.QFormLayout()
        self.worker_threads_spinbox = QtWidgets.QSpinBox(self)
        self.worker_threads_spinbox.setRange(1, 64)
        self.worker_threads_spinbox.setValue(4)
        self.dialog_settings = settings_group("Dialogs/JobRefresh", self)
        if self.dialog_settings.contains("worker_threads"):
            self.worker_threads_spinbox.setValue(
                self.dialog_settings.value("worker_threads", type=int)
            )
        self.worker_threads_spinbox.valueChanged.connect(
            partial(self.dialog_settings.setValue, "worker_threads")
        )
        options.addRow("Worker threads:", self.worker_threads_spinbox)
        self.status_label = QtWidgets.QLabel(self)
        self.status_label.setTextFormat(QtCore.Qt.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        layout.addWidget(self.status_label)
        self.progress_bar = QtWidgets.QProgressBar(self)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setFormat("%v / %m jobs loaded")
        if preserve_existing:
            self.setWindowTitle("Checking for Jobs")
            self.progress_bar.setFormat("%v / %m jobs checked")
        layout.addWidget(self.progress_bar)
        layout.addLayout(options)
        self.start_button = QtWidgets.QPushButton("Start refresh", self)
        self.start_button.clicked.connect(self.start_scan)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.start_button)
        self.stop_button = QtWidgets.QPushButton("Stop", self)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_scan)
        buttons.addWidget(self.stop_button)
        self.cancel_button = QtWidgets.QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        self.worker = JobRefreshWorker(jobs_dir, self, self.existing_items)
        self.worker.scan_started.connect(self.scan_started)
        self.worker.job_loaded.connect(self.add_job)
        self.worker.existing_checked.connect(self.check_existing)
        self.worker.finished.connect(self.scan_finished)

    @QtCore.Slot()
    def start_scan(self):
        self.started = True
        self.stop_requested = False
        self.loaded_count = 0
        self.checked_count = 0
        self.existing_items = {
            self.main_window.jobQueueList.item(index).data(JobDataRole.JobNameRole):
                self.main_window.jobQueueList.item(index)
            for index in range(self.main_window.jobQueueList.count())
        } if self.preserve_existing else {}
        self.worker.existing_names = set(self.existing_items)
        self.stop_button.setEnabled(True)
        self.start_button.setEnabled(False)
        self.worker_threads_spinbox.setEnabled(False)
        self.worker.worker_count = self.worker_threads_spinbox.value()
        if not self.preserve_existing:
            self.main_window.jobQueueList.clear()
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("Scanning saved jobs…")
        self.status_label.show()
        self.worker.start()

    @QtCore.Slot(int)
    def scan_started(self, count):
        self.progress_bar.setRange(0, max(1, count))
        self.progress_bar.setValue(0)

    @QtCore.Slot(str, object)
    def add_job(self, job_name, item):
        if not self.cancelled and not self.stop_requested:
            item.setData(JobDataRole.JobNameRole, job_name)
            item.setText(item.to_label(self.main_window.jobListLabelTemplateComboBox.currentText()))
            item.setToolTip(item.to_tooltip())
            job_list = self.main_window.jobQueueList
            job_list.addItem(item)
            if job_name == self.selected_job_name:
                job_list.setCurrentItem(item)
                job_list.scrollToItem(item, QtWidgets.QAbstractItemView.EnsureVisible)
            item.setHidden(
                self.main_window.jobsManagerSearchBox.text().lower().strip() not in job_name.lower()
            )
            self.loaded_count += 1
            self.checked_count += 1
            self.progress_bar.setValue(self.checked_count)
            self.status_label.setText(f"Loaded: {job_name}")
        self.worker.item_added.release()

    @QtCore.Slot(str, bool)
    def check_existing(self, job_name, exists):
        if not self.cancelled and not self.stop_requested:
            item = self.existing_items[job_name]
            job_list = self.main_window.jobQueueList
            if not exists:
                job_list.takeItem(job_list.row(item))
            elif job_name == self.selected_job_name:
                job_list.setCurrentItem(item)
                job_list.scrollToItem(item, QtWidgets.QAbstractItemView.EnsureVisible)
            self.checked_count += 1
            self.progress_bar.setValue(self.checked_count)
            self.status_label.setText(f"Checked: {job_name}" if exists else f"Removed: {job_name}")
        self.worker.item_added.release()

    @QtCore.Slot()
    def stop_scan(self):
        self.stop_requested = True
        self.worker.requestInterruption()
        self.stop_button.setEnabled(False)
        self.status_label.setText("Stopping…")

    @QtCore.Slot()
    def scan_finished(self):
        self.started = False
        self.stop_button.setEnabled(False)
        if self.stop_requested and not self.cancelled:
            self.start_button.setEnabled(True)
            self.worker_threads_spinbox.setEnabled(True)
            self.status_label.setText("Stopped")
        else:
            self.done(QtWidgets.QDialog.Rejected if self.cancelled else QtWidgets.QDialog.Accepted)

    def reject(self):
        self.cancelled = True
        if not self.started:
            self.scan_finished()
            return
        self.worker.requestInterruption()
        self.cancel_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.status_label.setText("Cancelling…")

    def closeEvent(self, event):
        event.ignore()
        self.reject()
