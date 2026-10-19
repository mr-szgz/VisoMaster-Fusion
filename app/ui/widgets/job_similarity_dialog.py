import json

from PySide6 import QtCore, QtGui, QtWidgets

from app.helpers.job_similarity import (
    configuration_differences,
    saved_render_configuration,
)


class JobSimilarityWorker(QtCore.QThread):
    job_checked = QtCore.Signal(str, object)

    def __init__(self, jobs_dir, jobs, parent):
        super().__init__(parent)
        self.jobs_dir = jobs_dir
        self.jobs = jobs

    def run(self):
        for job in self.jobs:
            if self.isInterruptionRequested():
                return
            with (self.jobs_dir / f"{job}.json").open(encoding="utf-8") as source:
                data = json.load(source)
            configuration = saved_render_configuration(data)
            self.job_checked.emit(job, configuration)


class JobSimilarityDialog(QtWidgets.QDialog):
    """Compare saved jobs and return the checked jobs for normal job processing."""

    def __init__(self, main_window, jobs):
        super().__init__(main_window)
        self.jobs_dir = main_window.project_root_path / "jobs"
        self.jobs = jobs
        self.configurations = {}
        self.items = {}
        self.differences = {}
        self.jobs_to_process = []
        self.checking = False
        self.setWindowTitle("Process Similar Jobs")
        self.setWindowIcon(QtGui.QIcon(":/media/media/visomaster_small.png"))
        self.resize(940, 620)
        self.setMinimumSize(600, 440)

        layout = QtWidgets.QVBoxLayout(self)
        description = QtWidgets.QLabel(
            "Select jobs with matching saved settings to send to the job processor.",
            self,
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.status_label = QtWidgets.QLabel("Reading selected jobs…", self)
        self.status_label.setTextFormat(QtCore.Qt.PlainText)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.progress_bar = QtWidgets.QProgressBar(self)
        layout.addWidget(self.progress_bar)
        self.reference_label = QtWidgets.QLabel(self)
        self.reference_label.setTextFormat(QtCore.Qt.PlainText)
        self.reference_label.setWordWrap(True)
        layout.addWidget(self.reference_label)
        self.metrics_label = QtWidgets.QLabel(self)
        layout.addWidget(self.metrics_label)

        self.results = QtWidgets.QTreeWidget(self)
        self.results.setHeaderLabels(["Job", "Similarity", "Differences"])
        self.results.setRootIsDecorated(False)
        self.results.setAlternatingRowColors(True)
        self.results.setColumnWidth(0, 340)
        self.results.setColumnWidth(1, 130)
        self.results.setColumnWidth(2, 250)
        self.results.setMinimumHeight(140)
        layout.addWidget(self.results, 2)
        layout.addWidget(QtWidgets.QLabel("Details for the highlighted job:", self))
        self.details = QtWidgets.QPlainTextEdit(self)
        self.details.setReadOnly(True)
        layout.addWidget(self.details, 1)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QtWidgets.QPushButton("Cancel", self)
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        self.start_button = QtWidgets.QPushButton("Send", self)
        self.start_button.setEnabled(False)
        self.start_button.setToolTip("Send checked jobs to the job processor.")
        self.start_button.clicked.connect(self.recheck_selected)
        buttons.addWidget(self.start_button)
        layout.addLayout(buttons)

        self.results.itemChanged.connect(self.selection_changed)
        self.results.currentItemChanged.connect(self.show_details)
        self.check_timer = QtCore.QTimer(self)
        self.check_timer.setSingleShot(True)
        self.check_timer.timeout.connect(self.check_jobs)
        self.check_timer.start(0)

    def check_jobs(self):
        self.check_timer.stop()
        self.begin_check(self.jobs, rechecking=False)

    def begin_check(self, jobs, rechecking):
        self.checking = True
        self.rechecking = rechecking
        self.checked_jobs = []
        self.jobs_to_process = []
        self.results.setEnabled(False)
        self.start_button.setEnabled(False)
        self.progress_bar.setRange(0, len(jobs))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m jobs checked")
        self.status_label.setText(
            "Rechecking chosen jobs…" if rechecking else "Reading selected jobs…"
        )
        self.worker = JobSimilarityWorker(self.jobs_dir, jobs, self)
        self.worker.job_checked.connect(self.job_checked)
        self.worker.finished.connect(self.check_finished)
        self.worker.start()

    @QtCore.Slot(str, object)
    def job_checked(self, job, configuration):
        self.configurations[job] = configuration
        self.checked_jobs.append(job)
        if not self.rechecking:
            item = QtWidgets.QTreeWidgetItem([job, "", ""])
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(0, QtCore.Qt.Unchecked)
            item.setToolTip(0, job)
            self.results.addTopLevelItem(item)
            self.items[job] = item
        self.progress_bar.setValue(len(self.checked_jobs))

    @QtCore.Slot()
    def check_finished(self):
        complete = self.checked_jobs == self.worker.jobs
        if not self.rechecking and complete:
            reference = self.configurations[self.jobs[0]]
            for job in self.jobs:
                if not configuration_differences(reference, self.configurations[job]):
                    self.items[job].setCheckState(0, QtCore.Qt.Checked)
            self.results.setCurrentItem(self.items[self.jobs[0]])
        self.checking = False
        self.results.setEnabled(complete)
        if complete:
            self.update_comparison()
            if self.rechecking and self.start_button.isEnabled():
                self.jobs_to_process = self.selected_jobs()
                self.accept()

    def selected_jobs(self):
        return [
            job
            for job in self.jobs
            if job in self.items and self.items[job].checkState(0) == QtCore.Qt.Checked
        ]

    def selection_changed(self, item, column):
        if not self.checking:
            self.jobs_to_process = []
            self.update_comparison()

    def update_comparison(self):
        selected = self.selected_jobs()
        reference_job = selected[0] if selected else self.jobs[0]
        reference = self.configurations[reference_job]
        self.reference_label.setText(f"Reference: {reference_job}")
        similar_count = 0
        self.results.blockSignals(True)
        for job in self.jobs:
            differences = configuration_differences(reference, self.configurations[job])
            self.differences[job] = differences
            similar_count += not differences
            item = self.items[job]
            item.setText(1, "Different" if differences else "Same settings")
            item.setText(
                2,
                f"{len(differences)} difference(s) — {differences[0]}"
                if differences
                else "No differences",
            )
            item.setToolTip(2, "\n".join(differences))
        self.results.blockSignals(False)
        self.metrics_label.setText(
            f"Same settings: {similar_count} / {len(self.jobs)}    Checked: {len(selected)}"
        )
        ready = bool(selected) and all(not self.differences[job] for job in selected)
        self.start_button.setEnabled(ready)
        self.status_label.setText(
            "Ready to send."
            if ready
            else "Check jobs with the same settings. Uncheck jobs with differences."
        )
        self.show_details()

    def show_details(self, current=None, previous=None):
        item = self.results.currentItem()
        if item is not None and item.text(0) in self.differences:
            differences = self.differences[item.text(0)]
            self.details.setPlainText(
                "\n".join(differences) if differences else "No differences."
            )

    def recheck_selected(self):
        self.begin_check(self.selected_jobs(), rechecking=True)

    def done(self, result):
        self.check_timer.stop()
        if self.checking:
            self.worker.requestInterruption()
            self.worker.wait()
        super().done(result)
