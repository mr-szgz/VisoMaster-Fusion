import json

from PySide6 import QtCore, QtGui, QtWidgets

from app.helpers.job_similarity import (
    add_job_to_cluster,
    saved_render_configuration,
)
from app.ui.widgets.job_list_widgets import JobDataRole


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
    """Group saved jobs and send checked clusters to normal job processing."""

    def __init__(self, main_window, jobs):
        super().__init__(main_window)
        self.jobs_dir = main_window.project_root_path / "jobs"
        self.jobs = jobs
        self.clusters = []
        self.items = {}
        self.job_details = {}
        for index in range(main_window.jobQueueList.count()):
            item = main_window.jobQueueList.item(index)
            job = item.data(JobDataRole.JobNameRole)
            if job in jobs:
                frame_rate = item.data(JobDataRole.FrameRateRole)
                seconds = (
                    item.data(JobDataRole.FrameCountRole) / frame_rate
                    if item.data(JobDataRole.MediaTypeRole) == "video"
                    and frame_rate > 0
                    else 0
                )
                self.job_details[job] = (
                    item.data(JobDataRole.EmbeddingNamesRole),
                    seconds,
                )
        self.jobs_to_process = []
        self.checking = False
        self.closed = False
        self.worker = None
        self.setWindowTitle("Process Similar Jobs")
        self.setWindowFlag(QtCore.Qt.WindowMinimizeButtonHint, True)
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
            "Select clusters to send to the job processor.", self
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

        self.embedding_filters = QtWidgets.QGroupBox("Embeddings", self)
        self.embedding_filters.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.embedding_filters.setToolTip(
            "Include jobs using any checked embedding. Click Rerun to apply."
        )
        filter_grid = QtWidgets.QGridLayout(self.embedding_filters)
        filter_grid.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.embedding_checkboxes = {}
        embedding_names = dict.fromkeys(
            name for job in self.jobs for name in self.job_details[job][0]
        )
        for index, name in enumerate(embedding_names):
            checkbox = QtWidgets.QCheckBox(name, self.embedding_filters)
            checkbox.setChecked(True)
            filter_grid.addWidget(checkbox, index // 3, index % 3)
            self.embedding_checkboxes[name] = checkbox
        layout.addWidget(self.embedding_filters)

        self.length_filters = QtWidgets.QWidget(self)
        length_layout = QtWidgets.QHBoxLayout(self.length_filters)
        length_layout.setContentsMargins(0, 0, 0, 0)
        self.minimum_length_checkbox = QtWidgets.QCheckBox(
            "Minimum length", self.length_filters
        )
        self.minimum_length = QtWidgets.QLineEdit(self.length_filters)
        self.maximum_length_checkbox = QtWidgets.QCheckBox(
            "Maximum length", self.length_filters
        )
        self.maximum_length = QtWidgets.QLineEdit(self.length_filters)
        for checkbox, editor in (
            (self.minimum_length_checkbox, self.minimum_length),
            (self.maximum_length_checkbox, self.maximum_length),
        ):
            editor.setInputMask("00:00:00;_")
            editor.setText("00:00:00")
            editor.setFixedWidth(90)
            editor.setEnabled(False)
            editor.setToolTip(
                "Job length in HH:MM:SS. Type six digits; colons are inserted automatically. Click Rerun to apply."
            )
            checkbox.toggled.connect(editor.setEnabled)
            length_layout.addWidget(checkbox)
            length_layout.addWidget(editor)
        length_layout.addStretch()
        layout.addWidget(self.length_filters)

        self.results = QtWidgets.QTreeWidget(self)
        self.results.setHeaderLabels(
            [
                "Cluster",
                "Jobs",
                "Job",
                "Embeddings",
                "Total length",
                "Average length",
                "Model",
            ]
        )
        self.results.setRootIsDecorated(True)
        self.results.setAlternatingRowColors(True)
        self.results.setColumnWidth(0, 150)
        self.results.setColumnWidth(1, 80)
        self.results.setColumnWidth(2, 200)
        self.results.setColumnWidth(3, 180)
        self.results.setColumnWidth(4, 110)
        self.results.setColumnWidth(5, 120)
        layout.addWidget(self.results, 1)

        buttons = QtWidgets.QHBoxLayout()
        self.rerun_button = QtWidgets.QPushButton("Rerun", self)
        self.rerun_button.setAutoDefault(False)
        self.rerun_button.setEnabled(False)
        self.rerun_button.clicked.connect(self.check_jobs)
        buttons.addWidget(self.rerun_button)
        buttons.addStretch()
        self.cancel_button = QtWidgets.QPushButton("Cancel", self)
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        self.send_button = QtWidgets.QPushButton("Send", self)
        self.send_button.setEnabled(False)
        self.send_button.setToolTip(
            "Send jobs from the checked clusters to the job processor."
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
        if self.worker is not None:
            self.worker.deleteLater()
        selected_embeddings = {
            name
            for name, checkbox in self.embedding_checkboxes.items()
            if checkbox.isChecked()
        }
        minimum_seconds = (
            sum(
                int(value) * factor
                for value, factor in zip(
                    self.minimum_length.text().split(":"), (3600, 60, 1)
                )
            )
            if self.minimum_length_checkbox.isChecked()
            else None
        )
        maximum_seconds = (
            sum(
                int(value) * factor
                for value, factor in zip(
                    self.maximum_length.text().split(":"), (3600, 60, 1)
                )
            )
            if self.maximum_length_checkbox.isChecked()
            else None
        )
        filtered_jobs = [
            job
            for job in self.jobs
            if (
                not self.job_details[job][0]
                or selected_embeddings.intersection(self.job_details[job][0])
            )
            and (minimum_seconds is None or self.job_details[job][1] >= minimum_seconds)
            and (maximum_seconds is None or self.job_details[job][1] <= maximum_seconds)
        ]
        self.checking = True
        self.clusters = []
        self.items = {}
        self.jobs_to_process = []
        self.results.clear()
        self.metrics_label.clear()
        self.status_label.setText("Reading jobs…")
        self.results.setEnabled(False)
        self.embedding_filters.setEnabled(False)
        self.length_filters.setEnabled(False)
        self.rerun_button.setEnabled(False)
        self.cluster_limit.setEnabled(False)
        self.send_button.setEnabled(False)
        self.progress_bar.setRange(0, max(1, len(filtered_jobs)))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"%v / {len(filtered_jobs)} jobs checked")
        self.worker = JobSimilarityWorker(self.jobs_dir, filtered_jobs, self)
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
            self.embedding_filters.setEnabled(True)
            self.length_filters.setEnabled(True)
            self.rerun_button.setEnabled(True)
            self.cluster_limit.setEnabled(True)
            self.show_clusters()

    def show_clusters(self):
        expanded_ids = {
            cluster_id for cluster_id, item in self.items.items() if item.isExpanded()
        }
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
            embedding_names = ", ".join(
                dict.fromkeys(
                    name for job in cluster["jobs"] for name in self.job_details[job][0]
                )
            )
            total_seconds = sum(self.job_details[job][1] for job in cluster["jobs"])
            average_hours, remainder = divmod(
                int(total_seconds / len(cluster["jobs"])), 3600
            )
            average_minutes, average_seconds = divmod(remainder, 60)
            hours, remainder = divmod(int(total_seconds), 3600)
            minutes, seconds = divmod(remainder, 60)
            models = ", ".join(
                dict.fromkeys(
                    parameters["SwapModelSelection"]
                    for parameters in cluster["configuration"]["parameters"]
                )
            )
            item = QtWidgets.QTreeWidgetItem(
                [
                    f"Cluster {cluster['id']}",
                    str(len(cluster["jobs"])),
                    cluster["representative_job"],
                    embedding_names,
                    f"{hours:02d}:{minutes:02d}:{seconds:02d}",
                    f"{average_hours:02d}:{average_minutes:02d}:{average_seconds:02d}",
                    models,
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
            item.setToolTip(3, embedding_names)
            item.setToolTip(6, models)
            self.results.addTopLevelItem(item)
            for job in cluster["jobs"]:
                child = QtWidgets.QTreeWidgetItem(item, [job])
                child.setFlags(QtCore.Qt.ItemIsEnabled)
                child.setToolTip(0, job)
                child.setFirstColumnSpanned(True)
            item.setExpanded(cluster["id"] in expanded_ids)
            self.items[cluster["id"]] = item
        self.results.blockSignals(False)
        self.selection_changed()

    def selected_jobs(self):
        selected = {
            job
            for cluster in self.clusters
            if cluster["id"] in self.items
            and self.items[cluster["id"]].checkState(0) == QtCore.Qt.Checked
            for job in cluster["jobs"]
        }
        return [job for job in self.jobs if job in selected]

    def selection_changed(self):
        self.jobs_to_process = []
        selected_jobs = self.selected_jobs()
        self.metrics_label.setText(
            f"Showing {len(self.items)} of {len(self.clusters)} clusters · {sum(len(cluster['jobs']) for cluster in self.clusters)} jobs\n"
            f"Selected: {len(selected_jobs)} jobs"
        )
        self.send_button.setEnabled(bool(selected_jobs) and not self.checking)
        self.status_label.setText(
            "Ready to send."
            if selected_jobs
            else "Select clusters to send."
            if self.clusters
            else "No jobs match the filters."
        )

    def send_selected(self):
        self.jobs_to_process = self.selected_jobs()
        self.accept()

    def run(self):
        loop = QtCore.QEventLoop(self)
        self.finished.connect(loop.quit)
        self.show()
        loop.exec()
        return self.result()

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def done(self, result):
        self.closed = True
        self.check_timer.stop()
        if self.checking:
            self.worker.requestInterruption()
            self.worker.wait()
        super().done(result)
