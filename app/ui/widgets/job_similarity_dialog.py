import json

from PySide6 import QtCore, QtGui, QtWidgets

from app.helpers.job_similarity import (
    add_job_to_cluster,
    saved_render_configuration,
)


class JobSimilarityWorker(QtCore.QThread):
    progress_changed = QtCore.Signal(int)

    def __init__(self, jobs_dir, jobs, parent):
        super().__init__(parent)
        self.jobs_dir = jobs_dir
        self.jobs = jobs
        self.clusters = []
        self.completed = False

    def run(self):
        for checked_count, job in enumerate(self.jobs, 1):
            if self.isInterruptionRequested():
                return
            with (self.jobs_dir / f"{job}.json").open(encoding="utf-8") as source:
                data = json.load(source)
            add_job_to_cluster(self.clusters, job, saved_render_configuration(data))
            self.progress_changed.emit(checked_count)
        self.completed = True


class JobSimilarityDialog(QtWidgets.QDialog):
    """Group saved jobs and send one checked cluster to normal job processing."""

    def __init__(self, main_window, jobs):
        super().__init__(main_window)
        self.jobs_dir = main_window.project_root_path / "jobs"
        self.jobs = jobs
        self.clusters = []
        self.items = {}
        self.jobs_to_process = []
        self.checking = False
        self.closed = False
        self.setWindowTitle("Process Similar Jobs")
        self.setWindowIcon(QtGui.QIcon(":/media/media/visomaster_small.png"))
        self.resize(840, 480)
        self.setMinimumSize(600, 360)

        layout = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QHBoxLayout()
        limit_label = QtWidgets.QLabel("Clusters to show:", self)
        self.cluster_limit = QtWidgets.QSpinBox(self)
        self.cluster_limit.setRange(1, 2147483647)
        self.cluster_limit.setValue(5)
        self.cluster_limit.setEnabled(False)
        limit_label.setBuddy(self.cluster_limit)
        controls.addWidget(limit_label)
        controls.addWidget(self.cluster_limit)
        controls.addStretch()
        layout.addLayout(controls)
        description = QtWidgets.QLabel(
            "Select a cluster to send to the job processor.", self
        )
        layout.addWidget(description)
        self.status_label = QtWidgets.QLabel("Reading selected jobs…", self)
        self.status_label.setTextFormat(QtCore.Qt.PlainText)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.progress_bar = QtWidgets.QProgressBar(self)
        layout.addWidget(self.progress_bar)
        self.metrics_label = QtWidgets.QLabel(self)
        self.metrics_label.setWordWrap(True)
        layout.addWidget(self.metrics_label)

        self.results = QtWidgets.QTreeWidget(self)
        self.results.setHeaderLabels(["Cluster", "Jobs", "Representative job"])
        self.results.setRootIsDecorated(False)
        self.results.setAlternatingRowColors(True)
        self.results.setColumnWidth(0, 150)
        self.results.setColumnWidth(1, 80)
        layout.addWidget(self.results, 1)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QtWidgets.QPushButton("Cancel", self)
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        self.send_button = QtWidgets.QPushButton("Send", self)
        self.send_button.setEnabled(False)
        self.send_button.setToolTip(
            "Send jobs from the checked cluster to the job processor."
        )
        self.send_button.clicked.connect(self.send_selected)
        buttons.addWidget(self.send_button)
        layout.addLayout(buttons)

        self.results.itemChanged.connect(self.selection_changed)
        self.cluster_limit.valueChanged.connect(self.show_clusters)
        self.check_timer = QtCore.QTimer(self)
        self.check_timer.setSingleShot(True)
        self.check_timer.timeout.connect(self.check_jobs)
        self.check_timer.start(0)

    def check_jobs(self):
        self.check_timer.stop()
        self.checking = True
        self.results.setEnabled(False)
        self.cluster_limit.setEnabled(False)
        self.send_button.setEnabled(False)
        self.progress_bar.setRange(0, len(self.jobs))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m jobs checked")
        self.worker = JobSimilarityWorker(self.jobs_dir, self.jobs, self)
        self.worker.progress_changed.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.check_finished)
        self.worker.start()

    @QtCore.Slot()
    def check_finished(self):
        if self.closed:
            return
        self.checking = False
        if self.worker.completed:
            self.clusters = self.worker.clusters
            self.results.setEnabled(True)
            self.cluster_limit.setEnabled(True)
            self.show_clusters()

    def show_clusters(self):
        checked_ids = {
            cluster_id
            for cluster_id, item in self.items.items()
            if item.checkState(0) == QtCore.Qt.Checked
        }
        visible = sorted(
            self.clusters, key=lambda cluster: (-len(cluster["jobs"]), cluster["id"])
        )[: self.cluster_limit.value()]
        self.results.blockSignals(True)
        self.results.clear()
        self.items = {}
        for cluster in visible:
            item = QtWidgets.QTreeWidgetItem(
                [
                    f"Cluster {cluster['id']}",
                    str(len(cluster["jobs"])),
                    cluster["representative_job"],
                ]
            )
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(
                0,
                QtCore.Qt.Checked
                if cluster["id"] in checked_ids
                else QtCore.Qt.Unchecked,
            )
            item.setToolTip(2, cluster["representative_job"])
            self.results.addTopLevelItem(item)
            self.items[cluster["id"]] = item
        self.results.blockSignals(False)
        self.selection_changed()

    def selected_cluster(self):
        for cluster in self.clusters:
            if (
                cluster["id"] in self.items
                and self.items[cluster["id"]].checkState(0) == QtCore.Qt.Checked
            ):
                return cluster

    def selected_jobs(self):
        cluster = self.selected_cluster()
        selected = set(cluster["jobs"]) if cluster is not None else set()
        return [job for job in self.jobs if job in selected]

    def selection_changed(self, item=None, column=0):
        if item is not None and item.checkState(0) == QtCore.Qt.Checked:
            self.results.blockSignals(True)
            for other in self.items.values():
                if other is not item:
                    other.setCheckState(0, QtCore.Qt.Unchecked)
            self.results.blockSignals(False)
        self.jobs_to_process = []
        cluster = self.selected_cluster()
        self.metrics_label.setText(
            f"Showing {len(self.items)} of {len(self.clusters)} clusters · {len(self.jobs)} jobs\n"
            f"Selected: {len(self.selected_jobs())} jobs"
        )
        self.send_button.setEnabled(cluster is not None and not self.checking)
        self.status_label.setText(
            "Ready to send." if cluster is not None else "Select a cluster to send."
        )

    def send_selected(self):
        self.jobs_to_process = self.selected_jobs()
        self.accept()

    def done(self, result):
        self.closed = True
        self.check_timer.stop()
        if self.checking:
            self.worker.requestInterruption()
            self.worker.wait()
        super().done(result)
