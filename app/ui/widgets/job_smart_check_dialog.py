from PySide6 import QtCore, QtGui, QtWidgets
from send2trash import send2trash

from app.ui.widgets.actions.job_manager_actions import (
    JobProcessor,
    update_job_manager_buttons,
)
from app.ui.widgets.job_list_widgets import JobDataRole


class JobSmartCheckWorker(JobProcessor):
    """Run the batch pre-flight analysis without loading or processing jobs."""

    def __init__(self, main_window, jobs, parent):
        # The scan only needs these inputs; do not connect video processing signals.
        QtCore.QThread.__init__(self, parent)
        self.jobs_dir = main_window.project_root_path / "jobs"
        self.jobs = jobs
        self.skipped_jobs = []

    def run(self):
        self.master_data = self._analyze_job_batch()


class JobSmartCheckDialog(QtWidgets.QDialog):
    """Live saved-job validation and its final report."""

    def __init__(self, main_window, jobs):
        super().__init__(main_window)
        self.main_window = main_window
        self.failed_jobs = {}
        self.checked_jobs = 0
        self.passed_jobs = 0
        self.scan_complete = False
        self.setWindowTitle("S.M.A.R.T. Job Check")
        self.setWindowIcon(QtGui.QIcon(":/media/media/visomaster_small.png"))
        self.resize(760, 480)
        self.setMinimumWidth(540)

        layout = QtWidgets.QVBoxLayout(self)
        self.status_label = QtWidgets.QLabel("Preparing job check…", self)
        self.status_label.setTextFormat(QtCore.Qt.PlainText)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.progress_bar = QtWidgets.QProgressBar(self)
        self.progress_bar.setRange(0, max(1, len(jobs)))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m jobs checked")
        layout.addWidget(self.progress_bar)

        properties = QtWidgets.QFormLayout()
        self.metrics_label = QtWidgets.QLabel(self)
        self.metrics_label.setWordWrap(True)
        properties.addRow("Jobs:", self.metrics_label)
        self.assets_label = QtWidgets.QLabel("Available when the scan completes", self)
        self.assets_label.setWordWrap(True)
        properties.addRow("Unique assets in passing jobs:", self.assets_label)
        layout.addLayout(properties)
        self.results = QtWidgets.QTreeWidget(self)
        self.results.setHeaderLabels(["Job", "Status", "Details"])
        self.results.setRootIsDecorated(False)
        self.results.setAlternatingRowColors(True)
        self.results.setColumnWidth(0, 230)
        self.results.setColumnWidth(1, 80)
        layout.addWidget(self.results)

        buttons = QtWidgets.QHBoxLayout()
        self.remove_button = QtWidgets.QPushButton("Remove Failures", self)
        self.remove_button.setAutoDefault(False)
        self.remove_button.setEnabled(False)
        self.remove_button.setToolTip(
            "Move failed job JSON files to the Recycle Bin. Media and face files are kept."
        )
        self.remove_button.clicked.connect(self.remove_failures)
        buttons.addWidget(self.remove_button)
        buttons.addStretch()
        self.close_button = QtWidgets.QPushButton("Close", self)
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.worker = JobSmartCheckWorker(main_window, jobs, self)
        self.worker.analysis_started_signal.connect(self.job_started)
        self.worker.analysis_result_signal.connect(self.job_checked)
        self.worker.finished.connect(self.check_finished)
        self.update_metrics()
        QtCore.QTimer.singleShot(0, self.worker.start)

    def update_metrics(self):
        self.metrics_label.setText(
            f"Total: {len(self.worker.jobs)}   Checked: {self.checked_jobs}   "
            f"Passed: {self.passed_jobs}   Failed: {len(self.failed_jobs)}"
        )

    @QtCore.Slot(str)
    def job_started(self, job_name):
        self.status_label.setText(f"Checking: {job_name}")

    @QtCore.Slot(str, str)
    def job_checked(self, job_name, reason):
        self.checked_jobs += 1
        if reason:
            self.failed_jobs[job_name] = reason
        else:
            self.passed_jobs += 1
        item = QtWidgets.QTreeWidgetItem(
            [job_name, "Failed" if reason else "Passed", reason]
        )
        item.setToolTip(0, job_name)
        item.setToolTip(2, reason)
        self.results.addTopLevelItem(item)
        self.progress_bar.setValue(self.checked_jobs)
        self.update_metrics()

    @QtCore.Slot()
    def check_finished(self):
        assets = self.worker.master_data
        self.assets_label.setText(
            f"Media: {len(assets['target_medias_data'])}   "
            f"Input faces: {len(assets['input_faces_data'])}   "
            f"Embeddings: {len(assets['embeddings_data'])}"
        )
        self.scan_complete = True
        self.status_label.setText(
            "Check complete." if self.worker.jobs else "No saved jobs to check."
        )
        if not self.worker.jobs:
            self.progress_bar.setValue(1)
            self.progress_bar.setFormat("No jobs")
        self.remove_button.setEnabled(bool(self.failed_jobs))
        self.close_button.setEnabled(True)

    @QtCore.Slot()
    def remove_failures(self):
        for job_name in self.failed_jobs:
            send2trash(str(self.worker.jobs_dir / f"{job_name}.json"))
        job_list = self.main_window.jobQueueList
        for index in range(job_list.count() - 1, -1, -1):
            if job_list.item(index).data(JobDataRole.JobNameRole) in self.failed_jobs:
                job_list.takeItem(index)
        for index in range(self.results.topLevelItemCount()):
            item = self.results.topLevelItem(index)
            if item.text(0) in self.failed_jobs:
                item.setText(1, "Removed")
        self.status_label.setText(
            f"Removed {len(self.failed_jobs)} failed job(s) to the Recycle Bin."
        )
        self.remove_button.setEnabled(False)
        update_job_manager_buttons(self.main_window)

    def done(self, result):
        if self.scan_complete:
            super().done(result)

    def closeEvent(self, event):
        if self.scan_complete:
            super().closeEvent(event)
        else:
            event.ignore()
