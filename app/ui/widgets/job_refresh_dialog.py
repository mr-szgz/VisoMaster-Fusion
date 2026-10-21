import json

from PySide6 import QtCore, QtWidgets

from app.ui.widgets.job_list_widgets import JobDataRole, JobQueueListWidgetItem


class JobRefreshWorker(QtCore.QThread):
    scan_started = QtCore.Signal(int)
    job_loaded = QtCore.Signal(str, object)
    existing_checked = QtCore.Signal(str, bool)

    def __init__(self, jobs_dir, parent, existing_names=()):
        super().__init__(parent)
        self.jobs_dir = jobs_dir
        self.item_added = QtCore.QSemaphore()
        self.existing_names = set(existing_names)

    def run(self):
        paths = list(self.jobs_dir.glob("*.json"))
        paths = [path for path in paths if path.stem not in self.existing_names]
        self.scan_started.emit(len(paths) + len(self.existing_names))
        for job_name in self.existing_names:
            if self.isInterruptionRequested():
                return
            exists = (self.jobs_dir / f"{job_name}.json").exists()
            self.existing_checked.emit(job_name, exists)
            self.item_added.acquire()
        for path in paths:
            if self.isInterruptionRequested():
                break
            with open(path, encoding="utf-8") as job_file:
                data = json.load(job_file)
            item = JobQueueListWidgetItem(QtCore.QFileInfo(str(path)), data)
            if self.isInterruptionRequested():
                break
            self.job_loaded.emit(path.stem, item)
            # Keep only one pending job payload while the UI inserts its row.
            self.item_added.acquire()


class JobRefreshDialog(QtWidgets.QDialog):
    """Display incremental refresh progress until completion or cancellation."""

    def __init__(self, main_window, jobs_dir, selected_job_name=None, preserve_existing=False):
        super().__init__(main_window)
        self.main_window = main_window
        self.selected_job_name = selected_job_name
        self.cancelled = False
        self.loaded_count = 0
        self.checked_count = 0
        self.existing_items = {
            main_window.jobQueueList.item(index).data(JobDataRole.JobNameRole):
                main_window.jobQueueList.item(index)
            for index in range(main_window.jobQueueList.count())
        } if preserve_existing else {}
        self.setWindowTitle("Loading Jobs")
        self.setMinimumWidth(380)
        layout = QtWidgets.QVBoxLayout(self)
        self.status_label = QtWidgets.QLabel("Scanning saved jobs…", self)
        self.status_label.setTextFormat(QtCore.Qt.PlainText)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.progress_bar = QtWidgets.QProgressBar(self)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFormat("%v / %m jobs loaded")
        if preserve_existing:
            self.setWindowTitle("Checking for Jobs")
            self.progress_bar.setFormat("%v / %m jobs checked")
        layout.addWidget(self.progress_bar)
        self.cancel_button = QtWidgets.QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)
        self.worker = JobRefreshWorker(jobs_dir, self, self.existing_items)
        self.worker.scan_started.connect(self.scan_started)
        self.worker.job_loaded.connect(self.add_job)
        self.worker.existing_checked.connect(self.check_existing)
        self.worker.finished.connect(self.scan_finished)
        QtCore.QTimer.singleShot(0, self.start_scan)

    @QtCore.Slot()
    def start_scan(self):
        if self.cancelled:
            self.scan_finished()
        else:
            self.worker.start()

    @QtCore.Slot(int)
    def scan_started(self, count):
        self.progress_bar.setRange(0, max(1, count))
        self.progress_bar.setValue(0)

    @QtCore.Slot(str, object)
    def add_job(self, job_name, item):
        if not self.cancelled:
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
        if not self.cancelled:
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
    def scan_finished(self):
        self.done(QtWidgets.QDialog.Rejected if self.cancelled else QtWidgets.QDialog.Accepted)

    def reject(self):
        self.cancelled = True
        self.worker.requestInterruption()
        self.cancel_button.setEnabled(False)
        self.status_label.setText("Cancelling after the current file read…")

    def closeEvent(self, event):
        event.ignore()
        self.reject()
