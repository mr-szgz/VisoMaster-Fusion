import json
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import cv2
from PySide6 import QtCore, QtGui, QtWidgets
from send2trash import send2trash

from app.settings import settings_group
from app.ui.widgets.actions import job_manager_actions
from app.ui.widgets.actions.job_manager_actions import (
    JobProcessor,
    filter_jobs,
    update_job_manager_buttons,
)
from app.ui.widgets.job_list_widgets import JobDataRole, JobQueueListWidgetItem
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
            metadata.append(sorted({
                embedding["embedding_name"]
                for embedding_id, embedding in embeddings.items()
                if embedding_id in used_ids
            }))
            self.metadata_signal.emit(job_name, metadata)
        return data

    def __init__(self, main_window, jobs, parent, worker_count=4):
        # The scan only needs these inputs; do not connect video processing signals.
        QtCore.QThread.__init__(self, parent)
        self.jobs_dir = main_window.project_root_path / "jobs"
        self.jobs = jobs
        self.worker_count = worker_count
        self.skipped_jobs = []

    def check_job(self, job_name):
        data = self._read_job_file(job_name)
        valid, reason = (
            job_manager_actions._validate_job_files_exist(data)
            if data is not None else (False, None)
        )
        return job_name, data, valid, reason

    def _iter_checked_jobs(self):
        with ThreadPoolExecutor(max_workers=self.worker_count) as executor:
            pending = deque()
            submitted = 0
            while pending or submitted < len(self.jobs):
                if self.isInterruptionRequested():
                    for future in pending:
                        future.cancel()
                    for future in pending:
                        if not future.cancelled():
                            future.result()
                    return
                while len(pending) < self.worker_count and submitted < len(self.jobs):
                    job_name = self.jobs[submitted]
                    self.analysis_started_signal.emit(job_name)
                    pending.append(executor.submit(self.check_job, job_name))
                    submitted += 1
                result = pending.popleft().result()
                if not self.isInterruptionRequested():
                    yield result

    def run(self):
        self.master_data = self._analyze_job_batch()


class JobSmartActionWorker(QtCore.QThread):
    job_finished = QtCore.Signal(str, object)

    def __init__(self, jobs_dir, jobs, action, worker_count, parent):
        super().__init__(parent)
        self.jobs_dir = jobs_dir
        self.jobs = jobs
        self.action = action
        self.worker_count = worker_count
        self.item_updated = QtCore.QSemaphore()

    def process_job(self, job_name):
        path = self.jobs_dir / f"{job_name}.json"
        if self.action == "remove":
            send2trash(str(path))
            return {"changed": 1}
        with open(path) as job_file:
            data = json.load(job_file)
        if self.action == "embeddings":
            used_ids = {
                embedding_id
                for face in data.get("target_faces_data", {}).values()
                for embedding_id in face.get("assigned_merged_embeddings", [])
            }
            embeddings = data.get("embeddings_data", {})
            retained = {key: value for key, value in embeddings.items() if key in used_ids}
            changed = len(embeddings) - len(retained)
            if changed:
                data["embeddings_data"] = retained
                with open(path, "w") as job_file:
                    json.dump(data, job_file, indent=4)
            return {
                "changed": changed, "count": len(retained), "size": path.stat().st_size,
                "names": sorted({embedding["embedding_name"] for embedding in retained.values()}),
            }
        media = next(media for media in data["target_medias_data"]
                     if media["media_id"] == data["selected_media_id"])
        result = {"changed": 0}
        if misc_helpers.get_file_type(media["media_path"]) == "video":
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
                result["changed"] = 1
            result.update(fps=media["fps"], frames=media["frame_count"], size=path.stat().st_size)
        return result

    def run(self):
        with ThreadPoolExecutor(max_workers=self.worker_count) as executor:
            pending = deque()
            submitted = 0
            while pending or (submitted < len(self.jobs) and not self.isInterruptionRequested()):
                if self.isInterruptionRequested():
                    for _, future in pending:
                        future.cancel()
                while (not self.isInterruptionRequested()
                       and len(pending) < self.worker_count and submitted < len(self.jobs)):
                    job_name = self.jobs[submitted]
                    pending.append((job_name, executor.submit(self.process_job, job_name)))
                    submitted += 1
                if not pending:
                    break
                job_name, future = pending.popleft()
                if future.cancelled():
                    continue
                result = future.result()
                # Completed writes must reach the UI even after Stop is requested.
                self.job_finished.emit(job_name, result)
                self.item_updated.acquire()


class JobSizeDelegate(QtWidgets.QStyledItemDelegate):
    def displayText(self, value, locale):
        if value == "":
            return ""
        size = int(value)
        if size < 1024:
            return f"{size} bytes"
        for unit in ("KB", "MB", "GB", "TB", "PB", "EB"):
            size /= 1024
            if size < 1024 or unit == "EB":
                return f"{size:.2f} {unit}"


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
        self.action_worker = None
        self.failed_jobs = {}
        self.job_metadata = {}
        self.changed_jobs = set()
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
        self.worker_threads_spinbox = QtWidgets.QSpinBox(self)
        self.worker_threads_spinbox.setRange(1, 64)
        self.worker_threads_spinbox.setValue(4)
        self.dialog_settings = settings_group("Dialogs/JobSmartCheck", self)
        if self.dialog_settings.contains("worker_threads"):
            self.worker_threads_spinbox.setValue(
                self.dialog_settings.value("worker_threads", type=int)
            )
        self.worker_threads_spinbox.valueChanged.connect(
            partial(self.dialog_settings.setValue, "worker_threads")
        )
        properties.addRow("Worker threads:", self.worker_threads_spinbox)
        self.metrics_label = QtWidgets.QLabel(self)
        self.metrics_label.setWordWrap(True)
        properties.addRow("Jobs:", self.metrics_label)
        self.assets_label = QtWidgets.QLabel("Available when the scan completes", self)
        self.assets_label.setWordWrap(True)
        properties.addRow("Unique assets in passing jobs:", self.assets_label)
        self.total_bytes_label = QtWidgets.QLabel("0 bytes", self)
        properties.addRow("Total size:", self.total_bytes_label)
        layout.addLayout(properties)
        filters = QtWidgets.QHBoxLayout()
        filters.addWidget(QtWidgets.QLabel("Show:", self))
        self.state_filters = {}
        self.state_counts = {"Passed": 0, "Failed": 0}
        for state in ("Passed", "Failed"):
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
        self.embedding_filters = {}
        embedding_group = QtWidgets.QGroupBox("Show embeddings:", self)
        embedding_layout = QtWidgets.QVBoxLayout(embedding_group)
        embedding_buttons = QtWidgets.QHBoxLayout()
        self.embedding_selection_buttons = {}
        for action, label in (("none", "Select None"), ("all", "Select All"), ("invert", "Invert Selection")):
            button = QtWidgets.QPushButton(label, embedding_group)
            button.setAutoDefault(False)
            button.clicked.connect(lambda checked=False, action=action: self.set_embedding_selection(action))
            self.embedding_selection_buttons[action] = button
            embedding_buttons.addWidget(button)
        embedding_buttons.addStretch()
        embedding_layout.addLayout(embedding_buttons)
        self.embedding_scroll = QtWidgets.QScrollArea(embedding_group)
        self.embedding_scroll.setWidgetResizable(True)
        embedding_contents = QtWidgets.QWidget(self.embedding_scroll)
        self.embedding_filter_layout = QtWidgets.QGridLayout(embedding_contents)
        self.embedding_filter_layout.setAlignment(QtCore.Qt.AlignTop)
        self.embedding_columns = 0
        self.embedding_scroll.setWidget(embedding_contents)
        self.embedding_scroll.viewport().installEventFilter(self)
        embedding_layout.addWidget(self.embedding_scroll)
        self.results_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        self.results_splitter.setChildrenCollapsible(False)
        self.results_splitter.addWidget(embedding_group)
        self.results = QtWidgets.QTreeWidget(self)
        self.results.setHeaderLabels(
            ["Job", "Status", "Embedding name", "Embeddings", "FPS", "Frames", "Size", "Changed"]
        )
        self.results.setItemDelegateForColumn(6, JobSizeDelegate(self.results))
        self.results.header().moveSection(7, 2)
        self.results.setColumnWidth(7, 80)
        self.results.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.results.itemSelectionChanged.connect(self.update_selection_actions)
        self.results.setRootIsDecorated(False)
        self.results.setAlternatingRowColors(True)
        self.results.setColumnWidth(0, 230)
        self.results.setColumnWidth(1, 80)
        self.results.sortItems(0, QtCore.Qt.AscendingOrder)
        self.results.setSortingEnabled(True)
        self.results_splitter.addWidget(self.results)
        self.results_splitter.setStretchFactor(0, 1)
        self.results_splitter.setStretchFactor(1, 3)
        self.results_splitter.setSizes([140, 300])
        layout.addWidget(self.results_splitter, 1)

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
        self.restart_button = QtWidgets.QPushButton("Restart", self)
        self.restart_button.setAutoDefault(False)
        self.restart_button.setEnabled(False)
        self.restart_button.clicked.connect(self.restart_scan)
        buttons.addWidget(self.restart_button)
        self.close_button = QtWidgets.QPushButton("Close", self)
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.start_scan(jobs)

    def start_scan(self, jobs):
        self.worker_threads_spinbox.setEnabled(False)
        self.worker = JobSmartCheckWorker(
            self.main_window, jobs, self, self.worker_threads_spinbox.value()
        )
        self.worker.metadata_signal.connect(self.receive_metadata)
        self.worker.analysis_started_signal.connect(self.job_started)
        self.worker.analysis_result_signal.connect(self.job_checked)
        self.worker.finished.connect(self.check_finished)
        self.update_metrics()
        self.worker.start()

    @QtCore.Slot()
    def restart_scan(self):
        self.worker.deleteLater()
        self.scan_complete = False
        self.stop_requested = False
        self.cancelled = False
        self.failed_jobs.clear()
        self.job_metadata.clear()
        self.checked_jobs = 0
        self.passed_jobs = 0
        self.results.clear()
        for checkbox in self.embedding_filters.values():
            self.embedding_filter_layout.removeWidget(checkbox)
            checkbox.deleteLater()
        self.embedding_filters.clear()
        self.embedding_columns = 0
        for state in self.state_counts:
            self.state_counts[state] = 0
        jobs = job_manager_actions.list_jobs(self.main_window)
        self.progress_bar.setRange(0, max(1, len(jobs)))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m jobs checked")
        self.assets_label.setText("Available when the scan completes")
        self.status_label.setText("Preparing job check…")
        self.restart_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.remove_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.stop_button.show()
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.update_selection_actions()
        self.start_scan(jobs)

    def update_metrics(self):
        total_bytes = sum(
            int(self.results.topLevelItem(index).text(6))
            for index in range(self.results.topLevelItemCount())
        )
        self.total_bytes_label.setText(
            self.results.itemDelegateForColumn(6).displayText(total_bytes, self.locale())
        )
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
        embedding_counts = dict.fromkeys(self.embedding_filters, 0)
        active = [name for name, checkbox in self.property_filters.items() if checkbox.isChecked()]
        for index in range(self.results.topLevelItemCount()):
            item = self.results.topLevelItem(index)
            for name in item.data(2, QtCore.Qt.UserRole):
                if name not in self.embedding_filters:
                    checkbox = QtWidgets.QCheckBox(self)
                    checkbox.setChecked(True)
                    checkbox.setToolTip(name)
                    checkbox.toggled.connect(self.filter_results)
                    self.embedding_filters[name] = checkbox
                    self.embedding_columns = 0
                    embedding_counts[name] = 0
                embedding_counts[name] += 1
        all_embeddings = all(checkbox.isChecked() for checkbox in self.embedding_filters.values())
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
            ) and (
                all_embeddings or any(self.embedding_filters[name].isChecked()
                                      for name in item.data(2, QtCore.Qt.UserRole))
            )
            if not visible:
                item.setSelected(False)
            item.setHidden(not visible)
        for name, checkbox in self.property_filters.items():
            checkbox.setText(f"{name} ({counts[name]})")
        for name, checkbox in self.embedding_filters.items():
            checkbox.setText(f"{name.replace('&', '&&')} ({embedding_counts[name]})")
        self.layout_embedding_filters()

    @QtCore.Slot(str)
    def set_embedding_selection(self, action):
        for checkbox in self.embedding_filters.values():
            with QtCore.QSignalBlocker(checkbox):
                checkbox.setChecked(not checkbox.isChecked() if action == "invert" else action == "all")
        self.filter_results()

    def layout_embedding_filters(self):
        if not self.embedding_filters:
            return
        margins = self.embedding_filter_layout.contentsMargins()
        width = self.embedding_scroll.viewport().width() - margins.left() - margins.right()
        spacing = self.embedding_filter_layout.horizontalSpacing()
        item_width = max(checkbox.sizeHint().width() for checkbox in self.embedding_filters.values())
        columns = max(1, (width + spacing) // (item_width + spacing))
        if columns == self.embedding_columns:
            return
        self.embedding_columns = columns
        while self.embedding_filter_layout.count():
            self.embedding_filter_layout.takeAt(0)
        for index, checkbox in enumerate(self.embedding_filters.values()):
            self.embedding_filter_layout.addWidget(checkbox, index // columns, index % columns)

    def eventFilter(self, watched, event):
        if watched is self.embedding_scroll.viewport() and event.type() == QtCore.QEvent.Resize:
            self.layout_embedding_filters()
        return super().eventFilter(watched, event)

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
        metadata = self.job_metadata.get(job_name, ["", "", "", "", []])
        item = JobSmartCheckItem(
            [job_name, "Failed" if reason else "Passed"]
            + metadata[:4]
            + [str((self.worker.jobs_dir / f"{job_name}.json").stat().st_size)]
            + ["Yes" if job_name in self.changed_jobs else "No"]
        )
        item.setToolTip(0, job_name)
        item.setToolTip(1, reason)
        item.setToolTip(2, item.text(2))
        item.setData(2, QtCore.Qt.UserRole, metadata[4])
        self.results.addTopLevelItem(item)
        self.state_counts[item.text(1)] += 1
        item.setHidden(not self.state_filters[item.text(1)].isChecked())
        self.progress_bar.setValue(self.checked_jobs)
        self.update_metrics()

    @QtCore.Slot()
    def stop_scan(self):
        self.stop_requested = True
        if self.action_worker is not None:
            self.action_worker.requestInterruption()
            self.status_label.setText("Stopping after active job operations finish…")
        else:
            self.worker.requestInterruption()
            self.status_label.setText("Stopping check…")
        self.stop_button.setEnabled(False)

    @QtCore.Slot()
    def check_finished(self):
        self.scan_complete = True
        if self.cancelled:
            self.done(QtWidgets.QDialog.Rejected)
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
        self.restart_button.setEnabled(True)
        self.worker_threads_spinbox.setEnabled(True)
        self.update_selection_actions()

    @QtCore.Slot(str, list)
    def receive_metadata(self, job_name, metadata):
        self.job_metadata[job_name] = metadata

    @QtCore.Slot()
    def update_selection_actions(self):
        selected = self.results.selectedItems()
        model = self.main_window.jobQueueList.model()
        self.select_job_button.setEnabled(
            len(selected) == 1 and bool(model.match(
                model.index(0, 0), JobDataRole.JobNameRole, selected[0].text(0),
                1, QtCore.Qt.MatchExactly,
            ))
        )
        enabled = self.scan_complete and self.action_worker is None and bool(selected)
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
        self.start_action("embeddings", self.results.selectedItems())

    @QtCore.Slot()
    def update_metadata(self):
        self.start_action("metadata", self.results.selectedItems())

    @QtCore.Slot()
    def remove_failures(self):
        items = [self.results.topLevelItem(index)
                 for index in range(self.results.topLevelItemCount())
                 if self.results.topLevelItem(index).text(0) in self.failed_jobs]
        self.start_action("remove", items)

    def start_action(self, action, items):
        self.action_items = {item.text(0): item for item in items}
        self.action_completed = 0
        self.action_changed = 0
        self.close_after_action = None
        self.stop_requested = False
        self.progress_bar.setRange(0, max(1, len(items)))
        self.progress_bar.setFormat({
            "remove": "%v / %m failed jobs removed",
            "embeddings": "%v / %m jobs cleaned",
            "metadata": "%v / %m jobs checked for metadata",
        }[action])
        self.progress_bar.setValue(0)
        self.status_label.setText({
            "remove": "Removing failed jobs…",
            "embeddings": "Removing extraneous embeddings…",
            "metadata": "Updating metadata…",
        }[action])
        self.action_worker = JobSmartActionWorker(
            self.worker.jobs_dir, list(self.action_items), action,
            self.worker_threads_spinbox.value(), self,
        )
        self.action_worker.job_finished.connect(self.action_job_finished)
        self.action_worker.finished.connect(self.action_finished)
        self.remove_button.setEnabled(False)
        self.restart_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.worker_threads_spinbox.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.stop_button.show()
        self.update_selection_actions()
        self.action_worker.start()

    @QtCore.Slot(str, object)
    def action_job_finished(self, job_name, result):
        item = self.action_items[job_name]
        action = self.action_worker.action
        if action == "remove":
            job_list = self.main_window.jobQueueList
            for index in range(job_list.count() - 1, -1, -1):
                if job_list.item(index).data(JobDataRole.JobNameRole) == job_name:
                    job_list.takeItem(index)
            self.state_counts[item.text(1)] -= 1
            self.changed_jobs.discard(job_name)
            self.results.takeTopLevelItem(self.results.indexOfTopLevelItem(item))
            self.worker.jobs = [name for name in self.worker.jobs if name != job_name]
            self.job_metadata = {
                name: metadata for name, metadata in self.job_metadata.items() if name != job_name
            }
            del self.failed_jobs[job_name]
            self.checked_jobs -= 1
        else:
            if result["changed"]:
                self.changed_jobs.add(job_name)
                item.setText(7, "Yes")
            if action == "embeddings":
                item.setText(3, str(result["count"]))
                item.setData(2, QtCore.Qt.UserRole, result["names"])
                item.setText(6, str(result["size"]))
            elif "fps" in result:
                item.setText(4, str(result["fps"]))
                item.setText(5, str(result["frames"]))
                item.setText(6, str(result["size"]))
        self.action_completed += 1
        self.action_changed += result["changed"]
        self.update_metrics()
        self.progress_bar.setValue(self.action_completed)
        if not self.stop_requested:
            self.status_label.setText(f"Processed: {job_name}")
        self.action_worker.item_updated.release()

    @QtCore.Slot()
    def action_finished(self):
        action = self.action_worker.action
        self.action_worker.deleteLater()
        self.action_worker = None
        self.action_items.clear()
        summary = {
            "remove": f"Removed {self.action_changed} failed job(s) to the Recycle Bin.",
            "embeddings": f"Removed {self.action_changed} extraneous embedding(s).",
            "metadata": f"Updated metadata for {self.action_changed} job(s).",
        }[action]
        self.status_label.setText(f"Stopped. {summary}" if self.stop_requested else summary)
        self.stop_button.hide()
        self.remove_button.setEnabled(bool(self.failed_jobs))
        self.restart_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.worker_threads_spinbox.setEnabled(True)
        self.update_selection_actions()
        update_job_manager_buttons(self.main_window)
        if self.close_after_action is not None:
            self.done(self.close_after_action)

    def done(self, result):
        if self.action_worker is not None:
            self.close_after_action = result
            self.stop_scan()
            return
        if self.scan_complete:
            job_list = self.main_window.jobQueueList
            changed_items = [
                job_list.item(index) for index in range(job_list.count())
                if job_list.item(index).data(JobDataRole.JobNameRole) in self.changed_jobs
            ]
            for item in changed_items:
                job_name = item.data(JobDataRole.JobNameRole)
                updated = JobQueueListWidgetItem(
                    QtCore.QFileInfo(str(self.worker.jobs_dir / f"{job_name}.json"))
                )
                updated.setData(JobDataRole.JobNameRole, job_name)
                for role in JobDataRole:
                    item.setData(role, updated.data(role))
                item.setText(updated.to_label(self.main_window.jobListLabelTemplateComboBox.currentText()))
                item.setToolTip(updated.to_tooltip())
            self.changed_jobs.clear()
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
