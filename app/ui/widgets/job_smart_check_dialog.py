import json

import cv2
from PySide6 import QtCore, QtGui, QtWidgets
from send2trash import send2trash

from app.ui.widgets.actions.job_manager_actions import (
    JobProcessor,
    filter_jobs,
    update_job_manager_buttons,
)
from app.ui.widgets.job_list_widgets import JobDataRole
import app.helpers.miscellaneous as misc_helpers


class JobSmartCheckWorker(JobProcessor):
    """Run the batch pre-flight analysis without loading or processing jobs."""

    metadata_signal = QtCore.Signal(str, list)

    def _read_job_file(self, job_name):
        data = super()._read_job_file(job_name)
        if data is not None:
            used_ids = {
                embedding_id
                for face in data.get("target_faces_data", {}).values()
                for embedding_id in face.get("assigned_merged_embeddings", [])
            }
            embeddings = data.get("embeddings_data", {})
            names = ", ".join(
                embedding["embedding_name"]
                for embedding_id, embedding in embeddings.items()
                if embedding_id in used_ids
            )
            metadata = [names, str(len(embeddings)), "", ""]
            for media in data.get("target_medias_data", []):
                if media["media_id"] == data.get("selected_media_id"):
                    metadata[2] = str(media.get("fps", ""))
                    metadata[3] = str(media.get("frame_count", ""))
                    break
            self.metadata_signal.emit(job_name, metadata)
        return data

    def __init__(self, main_window, jobs, parent):
        # The scan only needs these inputs; do not connect video processing signals.
        QtCore.QThread.__init__(self, parent)
        self.jobs_dir = main_window.project_root_path / "jobs"
        self.jobs = jobs
        self.skipped_jobs = []

    def run(self):
        self.master_data = self._analyze_job_batch()


class JobSmartCheckItem(QtWidgets.QTreeWidgetItem):
    def __lt__(self, other):
        column = self.treeWidget().sortColumn()
        if column in (3, 4, 5, 6):
            left, right = self.text(column), other.text(column)
            if left == "" or right == "":
                return left == "" and right != ""
            if column == 4:
                return float(left) < float(right)
            return int(left) < int(right)
        return self.text(column) < other.text(column)


class JobSmartCheckDialog(QtWidgets.QDialog):
    """Live saved-job validation and its final report."""

    def __init__(self, main_window, jobs):
        super().__init__(main_window)
        self.main_window = main_window
        self.failed_jobs = {}
        self.job_metadata = {}
        self.checked_jobs = 0
        self.passed_jobs = 0
        self.scan_complete = False
        self.stop_requested = False
        self.cancelled = False
        self.setWindowTitle("S.M.A.R.T. Job Check")
        self.setWindowIcon(QtGui.QIcon(":/media/media/visomaster_small.png"))
        self.resize(1000, 480)
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
        self.total_bytes_label = QtWidgets.QLabel("0", self)
        properties.addRow("Total bytes:", self.total_bytes_label)
        layout.addLayout(properties)
        filters = QtWidgets.QHBoxLayout()
        filters.addWidget(QtWidgets.QLabel("Show:", self))
        self.state_filters = {}
        self.state_counts = {"Passed": 0, "Failed": 0, "Removed": 0}
        for state in ("Passed", "Failed", "Removed"):
            checkbox = QtWidgets.QCheckBox(state, self)
            checkbox.setChecked(True)
            checkbox.toggled.connect(self.filter_results)
            self.state_filters[state] = checkbox
            filters.addWidget(checkbox)
        self.property_filters = {}
        for name in ("Embeddings > 1", "Missing FPS", "Missing Frames"):
            checkbox = QtWidgets.QCheckBox(name, self)
            checkbox.setToolTip("Show jobs matching any checked property, within the checked statuses.")
            checkbox.toggled.connect(self.filter_results)
            self.property_filters[name] = checkbox
            filters.addWidget(checkbox)
        filters.addStretch()
        layout.addLayout(filters)
        self.results = QtWidgets.QTreeWidget(self)
        self.results.setHeaderLabels(
            ["Job", "Status", "Embedding name", "Embeddings", "FPS", "Frames", "Bytes"]
        )
        self.results.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.results.itemSelectionChanged.connect(self.update_selection_actions)
        self.results.setRootIsDecorated(False)
        self.results.setAlternatingRowColors(True)
        self.results.setColumnWidth(0, 230)
        self.results.setColumnWidth(1, 80)
        self.results.sortItems(0, QtCore.Qt.AscendingOrder)
        self.results.setSortingEnabled(True)
        layout.addWidget(self.results)

        buttons = QtWidgets.QHBoxLayout()
        self.select_all_button = QtWidgets.QPushButton("Select All", self)
        self.select_all_button.setAutoDefault(False)
        self.select_all_button.setToolTip("Select only the jobs currently visible in this list.")
        self.select_all_button.clicked.connect(self.select_visible_jobs)
        buttons.addWidget(self.select_all_button)
        self.select_job_button = QtWidgets.QPushButton("Select in Job Manager", self)
        self.select_job_button.setAutoDefault(False)
        self.select_job_button.setEnabled(False)
        self.select_job_button.setToolTip("Select and reveal the single selected job in the loaded Job Manager list.")
        self.select_job_button.clicked.connect(self.select_in_job_manager)
        buttons.addWidget(self.select_job_button)
        self.remove_button = QtWidgets.QPushButton("Remove Failures", self)
        self.remove_button.setAutoDefault(False)
        self.remove_button.setEnabled(False)
        self.remove_button.setToolTip(
            "Move failed job JSON files to the Recycle Bin. Media and face files are kept."
        )
        self.remove_button.clicked.connect(self.remove_failures)
        buttons.addWidget(self.remove_button)
        self.remove_embeddings_button = QtWidgets.QPushButton("Remove Extraneous Embeddings", self)
        self.remove_embeddings_button.setAutoDefault(False)
        self.remove_embeddings_button.setEnabled(False)
        self.remove_embeddings_button.setToolTip(
            "Remove saved embeddings not assigned to any target face in the selected jobs."
        )
        self.remove_embeddings_button.clicked.connect(self.remove_extraneous_embeddings)
        buttons.addWidget(self.remove_embeddings_button)
        self.update_metadata_button = QtWidgets.QPushButton("Update Metadata", self)
        self.update_metadata_button.setAutoDefault(False)
        self.update_metadata_button.setEnabled(False)
        self.update_metadata_button.setToolTip(
            "Read the selected jobs' videos and save missing FPS and frame counts."
        )
        self.update_metadata_button.clicked.connect(self.update_metadata)
        buttons.addWidget(self.update_metadata_button)
        buttons.addStretch()
        self.stop_button = QtWidgets.QPushButton("Stop", self)
        self.stop_button.setAutoDefault(False)
        self.stop_button.setToolTip("Stop scanning and keep the results found so far.")
        self.stop_button.clicked.connect(self.stop_scan)
        buttons.addWidget(self.stop_button)
        self.cancel_button = QtWidgets.QPushButton("Cancel", self)
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        self.close_button = QtWidgets.QPushButton("Close", self)
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.worker = JobSmartCheckWorker(main_window, jobs, self)
        self.worker.metadata_signal.connect(self.receive_metadata)
        self.worker.analysis_started_signal.connect(self.job_started)
        self.worker.analysis_result_signal.connect(self.job_checked)
        self.worker.finished.connect(self.check_finished)
        self.update_metrics()
        self.worker.start()

    def update_metrics(self):
        self.total_bytes_label.setText(str(sum(
            int(self.results.topLevelItem(index).text(6))
            for index in range(self.results.topLevelItemCount())
            if self.results.topLevelItem(index).text(1) != "Removed"
        )))
        for state, checkbox in self.state_filters.items():
            checkbox.setText(f"{state} ({self.state_counts[state]})")
        self.metrics_label.setText(
            f"Total: {len(self.worker.jobs)}   Checked: {self.checked_jobs}   "
            f"Passed: {self.passed_jobs}   Failed: {len(self.failed_jobs)}"
        )
        self.filter_results()

    @QtCore.Slot(str)
    def job_started(self, job_name):
        if self.stop_requested or self.cancelled:
            return
        self.status_label.setText(f"Checking: {job_name}")

    @QtCore.Slot()
    def filter_results(self):
        counts = dict.fromkeys(self.property_filters, 0)
        active = [name for name, checkbox in self.property_filters.items() if checkbox.isChecked()]
        for index in range(self.results.topLevelItemCount()):
            item = self.results.topLevelItem(index)
            matches = {
                "Embeddings > 1": item.text(3) != "" and int(item.text(3)) > 1,
                "Missing FPS": item.text(4) == "",
                "Missing Frames": item.text(5) == "",
            }
            for name, matched in matches.items():
                counts[name] += matched
            visible = self.state_filters[item.text(1)].isChecked() and (
                not active or any(matches[name] for name in active)
            )
            if not visible:
                item.setSelected(False)
            item.setHidden(not visible)
        for name, checkbox in self.property_filters.items():
            checkbox.setText(f"{name} ({counts[name]})")

    @QtCore.Slot()
    def select_visible_jobs(self):
        for index in range(self.results.topLevelItemCount()):
            item = self.results.topLevelItem(index)
            item.setSelected(not item.isHidden())

    @QtCore.Slot(str, str)
    def job_checked(self, job_name, reason):
        if self.cancelled:
            return
        self.checked_jobs += 1
        if reason:
            self.failed_jobs[job_name] = reason
        else:
            self.passed_jobs += 1
        item = JobSmartCheckItem(
            [job_name, "Failed" if reason else "Passed"]
            + self.job_metadata.get(job_name, ["", "", "", ""])
            + [str((self.worker.jobs_dir / f"{job_name}.json").stat().st_size)]
        )
        item.setToolTip(0, job_name)
        item.setToolTip(1, reason)
        item.setToolTip(2, item.text(2))
        self.results.addTopLevelItem(item)
        self.state_counts[item.text(1)] += 1
        item.setHidden(not self.state_filters[item.text(1)].isChecked())
        self.progress_bar.setValue(self.checked_jobs)
        self.update_metrics()

    @QtCore.Slot()
    def stop_scan(self):
        self.stop_requested = True
        self.worker.requestInterruption()
        self.stop_button.setEnabled(False)
        self.status_label.setText("Stopping check…")

    @QtCore.Slot()
    def check_finished(self):
        self.scan_complete = True
        if self.cancelled:
            super().done(QtWidgets.QDialog.Rejected)
            return
        assets = self.worker.master_data
        self.assets_label.setText(
            f"Media: {len(assets['target_medias_data'])}   "
            f"Input faces: {len(assets['input_faces_data'])}   "
            f"Embeddings: {len(assets['embeddings_data'])}"
        )
        self.status_label.setText(
            "Check stopped. Results found so far are available."
            if self.stop_requested
            else "Check complete." if self.worker.jobs else "No saved jobs to check."
        )
        if not self.worker.jobs:
            self.progress_bar.setValue(1)
            self.progress_bar.setFormat("No jobs")
        self.remove_button.setEnabled(bool(self.failed_jobs))
        self.stop_button.hide()
        self.cancel_button.hide()
        self.close_button.setEnabled(True)
        self.update_selection_actions()

    @QtCore.Slot(str, list)
    def receive_metadata(self, job_name, metadata):
        self.job_metadata[job_name] = metadata

    @QtCore.Slot()
    def update_selection_actions(self):
        selected = self.results.selectedItems()
        model = self.main_window.jobQueueList.model()
        self.select_job_button.setEnabled(
            len(selected) == 1 and selected[0].text(1) != "Removed" and bool(model.match(
                model.index(0, 0), JobDataRole.JobNameRole, selected[0].text(0),
                1, QtCore.Qt.MatchExactly,
            ))
        )
        enabled = self.scan_complete and any(
            item.text(1) != "Removed" for item in self.results.selectedItems()
        )
        self.remove_embeddings_button.setEnabled(enabled)
        self.update_metadata_button.setEnabled(enabled)

    @QtCore.Slot()
    def select_in_job_manager(self):
        job_name = self.results.selectedItems()[0].text(0)
        job_list = self.main_window.jobQueueList
        model = job_list.model()
        index = model.match(
            model.index(0, 0), JobDataRole.JobNameRole, job_name,
            1, QtCore.Qt.MatchExactly,
        )[0]
        if job_list.isRowHidden(index.row()):
            self.main_window.jobsManagerSearchBox.clear()
            filter_jobs(self.main_window)
        job_list.clearSelection()
        job_list.setCurrentIndex(index)
        job_list.scrollTo(index, QtWidgets.QAbstractItemView.EnsureVisible)

    @QtCore.Slot()
    def remove_extraneous_embeddings(self):
        removed = 0
        for item in self.results.selectedItems():
            if item.text(1) == "Removed":
                continue
            path = self.worker.jobs_dir / f"{item.text(0)}.json"
            with open(path) as job_file:
                data = json.load(job_file)
            used_ids = {
                embedding_id
                for face in data.get("target_faces_data", {}).values()
                for embedding_id in face.get("assigned_merged_embeddings", [])
            }
            embeddings = data.get("embeddings_data", {})
            retained = {
                embedding_id: embedding
                for embedding_id, embedding in embeddings.items()
                if embedding_id in used_ids
            }
            if len(retained) != len(embeddings):
                removed += len(embeddings) - len(retained)
                data["embeddings_data"] = retained
                with open(path, "w") as job_file:
                    json.dump(data, job_file, indent=4)
            item.setText(3, str(len(retained)))
            item.setText(6, str(path.stat().st_size))
        self.update_metrics()
        self.status_label.setText(f"Removed {removed} extraneous embedding(s).")

    @QtCore.Slot()
    def update_metadata(self):
        updated = 0
        for item in self.results.selectedItems():
            if item.text(1) == "Removed":
                continue
            path = self.worker.jobs_dir / f"{item.text(0)}.json"
            with open(path) as job_file:
                data = json.load(job_file)
            media = next(
                media for media in data["target_medias_data"]
                if media["media_id"] == data["selected_media_id"]
            )
            if misc_helpers.get_file_type(media["media_path"]) != "video":
                continue
            if "fps" not in media or "frame_count" not in media:
                capture = cv2.VideoCapture()
                capture.setExceptionMode(True)
                capture.open(media["media_path"])
                if "fps" not in media:
                    media["fps"] = capture.get(cv2.CAP_PROP_FPS)
                if "frame_count" not in media:
                    media["frame_count"] = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
                capture.release()
                with open(path, "w") as job_file:
                    json.dump(data, job_file, indent=4)
                updated += 1
            item.setText(4, str(media["fps"]))
            item.setText(5, str(media["frame_count"]))
            item.setText(6, str(path.stat().st_size))
        self.update_metrics()
        self.status_label.setText(f"Updated metadata for {updated} job(s).")

    @QtCore.Slot()
    def remove_failures(self):
        for job_name in self.failed_jobs:
            send2trash(str(self.worker.jobs_dir / f"{job_name}.json"))
        job_list = self.main_window.jobQueueList
        for index in range(job_list.count() - 1, -1, -1):
            if job_list.item(index).data(JobDataRole.JobNameRole) in self.failed_jobs:
                job_list.takeItem(index)
        items = [self.results.topLevelItem(index)
                 for index in range(self.results.topLevelItemCount())]
        for item in items:
            if item.text(0) in self.failed_jobs:
                self.state_counts[item.text(1)] -= 1
                item.setText(1, "Removed")
                self.state_counts["Removed"] += 1
        self.update_metrics()
        self.filter_results()
        self.status_label.setText(
            f"Removed {len(self.failed_jobs)} failed job(s) to the Recycle Bin."
        )
        self.remove_button.setEnabled(False)
        self.update_selection_actions()
        update_job_manager_buttons(self.main_window)

    def done(self, result):
        if self.scan_complete:
            super().done(result)
        else:
            self.cancelled = True
            self.worker.requestInterruption()
            self.failed_jobs.clear()
            self.results.clear()
            for state in self.state_counts:
                self.state_counts[state] = 0
            self.update_metrics()
            self.stop_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Cancelling check…")

    def closeEvent(self, event):
        if self.scan_complete:
            super().closeEvent(event)
        else:
            event.ignore()
            self.reject()
