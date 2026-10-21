import json
import cv2
from functools import partial
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from app.settings import settings_group
from app.helpers.miscellaneous import get_file_type


class BatchSaveJobsDialog(QtWidgets.QDialog):
    """Create job files with cooperative cancellation during JSON writing."""

    minimizedChanged = QtCore.Signal(bool)

    def __init__(self, parent, media_items):
        super().__init__(parent)
        self.media_items = media_items
        self.saved_names = []
        self.started_count = 0
        self.cancel_requested = False
        self.is_paused = False
        self.control_loop = QtCore.QEventLoop(self)
        self.finished.connect(self.control_loop.quit)
        self.is_finished = False
        self.setWindowTitle("Batch Saving Jobs...")
        self.setWindowIcon(QtGui.QIcon(":/media/media/visomaster_small.png"))
        self.setWindowFlag(QtCore.Qt.WindowMinimizeButtonHint, True)
        self.setMinimumWidth(540)
        layout = QtWidgets.QVBoxLayout(self)
        num_images = sum(media.file_type == "image" for media in media_items)
        num_videos = sum(media.file_type == "video" for media in media_items)
        self.summary_label = QtWidgets.QLabel(
            f"Found {num_images} images and {num_videos} videos in the target list.\n\n"
            "This will save a job for each item using the current face configuration.", self
        )
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        self.status_label = QtWidgets.QLabel("Configure settings, then press Start.", self)
        self.status_label.setTextFormat(QtCore.Qt.PlainText)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.progress_bar = QtWidgets.QProgressBar(self)
        self.progress_bar.setRange(0, len(media_items))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p% - %v / %m jobs saved")
        layout.addWidget(self.progress_bar)
        self.report_labels = {}
        report = QtWidgets.QFormLayout()
        for field, initial in (
            ("Queued:", len(media_items)), ("Saved:", 0),
            ("Cancelled:", 0), ("Not started:", len(media_items)),
        ):
            value = QtWidgets.QLabel(str(initial), self)
            value.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            report.addRow(field, value)
            self.report_labels[field] = value
        layout.addLayout(report)
        self.details = QtWidgets.QPlainTextEdit(self)
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Saved jobs will appear here.")
        layout.addWidget(self.details)
        properties = QtWidgets.QFormLayout()
        layout.addLayout(properties)
        self.remove_completed_checkbox = QtWidgets.QCheckBox("Clear target media", self)
        self.remove_completed_checkbox.setToolTip(
            "Remove items from the target list after their jobs have been saved"
        )
        properties.addRow(self.remove_completed_checkbox)
        self.stop_after_completion_checkbox = QtWidgets.QCheckBox("Stop after current item", self)
        properties.addRow(self.stop_after_completion_checkbox)
        self.stop_after_processing_row = QtWidgets.QWidget(self)
        stop_limit_layout = QtWidgets.QHBoxLayout(self.stop_after_processing_row)
        stop_limit_layout.setContentsMargins(0, 0, 0, 0)
        self.stop_after_processing_checkbox = QtWidgets.QCheckBox("Stop after saving", self.stop_after_processing_row)
        self.stop_after_processing_checkbox.setToolTip("Stop saving new jobs once the saved job count reaches the limit")
        self.stop_after_processing_spinbox = QtWidgets.QSpinBox(self.stop_after_processing_row)
        self.stop_after_processing_spinbox.setRange(1, 2147483647)
        self.stop_after_processing_spinbox.setValue(100)
        self.stop_after_processing_spinbox.setSuffix(" items")
        stop_limit_layout.addWidget(self.stop_after_processing_checkbox)
        stop_limit_layout.addWidget(self.stop_after_processing_spinbox)
        stop_limit_layout.addStretch()
        properties.addRow(self.stop_after_processing_row)
        self.dialog_settings = settings_group("Dialogs/BatchSaveJobs", self)
        self.dialog_settings.remove("stop_after_completion_checkbox")
        for name in (
            "remove_completed_checkbox",
            "stop_after_processing_checkbox",
        ):
            checkbox = getattr(self, name)
            if self.dialog_settings.contains(name):
                checkbox.setChecked(self.dialog_settings.value(name, type=bool))
            checkbox.toggled.connect(partial(self.dialog_settings.setValue, name))
        if self.dialog_settings.contains("stop_after_processing"):
            self.stop_after_processing_spinbox.setValue(
                self.dialog_settings.value("stop_after_processing", type=int)
            )
        self.stop_after_processing_spinbox.valueChanged.connect(
            partial(self.dialog_settings.setValue, "stop_after_processing")
        )
        self.stop_after_processing_spinbox.setEnabled(self.stop_after_processing_checkbox.isChecked())
        self.stop_after_processing_checkbox.toggled.connect(self.stop_after_processing_spinbox.setEnabled)
        buttons = QtWidgets.QHBoxLayout()
        self.runtime_label = QtWidgets.QLabel("Runtime: 00:00:00", self)
        buttons.addWidget(self.runtime_label)
        buttons.addStretch()
        self.cancel_button = QtWidgets.QPushButton("Cancel", self)
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.cancel)
        buttons.addWidget(self.cancel_button)
        self.stop_button = QtWidgets.QPushButton("Stop", self)
        self.stop_button.setAutoDefault(False)
        self.stop_button.setToolTip("Finish saving the current item, then stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        buttons.addWidget(self.stop_button)
        self.pause_button = QtWidgets.QPushButton("Pause", self)
        self.pause_button.setAutoDefault(False)
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self.pause)
        buttons.addWidget(self.pause_button)
        self.start_button = QtWidgets.QPushButton("Start", self)
        self.start_button.setAutoDefault(False)
        self.start_button.clicked.connect(self.start)
        buttons.addWidget(self.start_button)
        layout.addLayout(buttons)
        self.clock = QtCore.QElapsedTimer()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_runtime)
        if self.dialog_settings.contains("geometry"):
            self.restoreGeometry(self.dialog_settings.value("geometry"))

    def update_runtime(self):
        hours, remainder = divmod(self.clock.elapsed() // 1000, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.runtime_label.setText(f"Runtime: {hours:02}:{minutes:02}:{seconds:02}")

    def start(self):
        self.is_paused = False
        self.stop_button.setEnabled(True)
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.control_loop.quit()

    def pause(self):
        self.is_paused = True
        self.pause_button.setEnabled(False)
        self.start_button.setEnabled(True)

    def stop(self):
        self.stop_after_completion_checkbox.setChecked(True)
        self.stop_after_completion_checkbox.setEnabled(False)
        self.is_paused = False
        self.control_loop.quit()
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)

    def process_events(self):
        QtWidgets.QApplication.processEvents()
        if self.is_paused and not self.cancel_requested:
            status = self.status_label.text()
            self.status_label.setText("Paused. Press Start to continue.")
            self.control_loop.exec()
            if not self.cancel_requested:
                self.status_label.setText(status)

    def cancel(self):
        if self.is_finished:
            self.accept()
            return
        self.cancel_requested = True
        self.stop_button.setEnabled(False)
        self.control_loop.quit()
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.remove_completed_checkbox.setEnabled(False)
        self.stop_after_completion_checkbox.setEnabled(False)
        self.stop_after_processing_row.setEnabled(False)
        self.status_label.setText("Cancelling job creation…")

    def reject(self):
        if self.is_finished:
            super().reject()
        else:
            self.cancel()

    def closeEvent(self, event):
        if self.is_finished:
            event.accept()
        else:
            event.ignore()
            self.cancel()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.WindowStateChange:
            was_minimized = bool(event.oldState() & QtCore.Qt.WindowMinimized)
            if was_minimized != self.isMinimized():
                self.minimizedChanged.emit(self.isMinimized())

    def run(self):
        from app.ui.widgets.actions import job_manager_actions

        saved_jobs = {}
        self.show()
        self.control_loop.exec()
        self.clock.start()
        self.timer.start(1000)
        self.status_label.setText("Preparing job configuration…")
        if not self.cancel_requested and self.media_items:
            workspace = job_manager_actions._serialize_job_data(
                self.parentWidget(), assigned_embeddings_only=True
            )
            workspace["use_job_name_for_output"] = True
            workspace["output_file_name"] = None
            workspace["restore_selected_face"] = self.parentWidget().control["ClusterOutputBySourceToggle"]
            jobs_dir = job_manager_actions.get_jobs_dir(self.parentWidget())
            self.process_events()
            for media in self.media_items:
                if self.cancel_requested:
                    break
                self.started_count += 1
                self.report_labels["Not started:"].setText(str(len(self.media_items) - self.started_count))
                self.status_label.setText(
                    f"Creating job {self.started_count}/{len(self.media_items)}: {media.media_path}"
                )
                self.process_events()
                if self.cancel_requested:
                    break
                job_name = Path(media.media_path).stem.strip()
                job_path = jobs_dir / f"{job_name}.json"
                suffix = 1
                while job_path.exists():
                    job_path = jobs_dir / f"{job_name}_{suffix}.json"
                    suffix += 1
                workspace["target_medias_data"] = [
                    {"media_id": media.media_id, "media_path": media.media_path}
                ]
                workspace["selected_media_id"] = media.media_id
                target = workspace["target_medias_data"][0]
                if get_file_type(target["media_path"]) == "image":
                    target["frame_count"] = 1
                    target["fps"] = 0.0
                else:
                    capture = cv2.VideoCapture()
                    capture.setExceptionMode(True)
                    capture.open(target["media_path"])
                    target["frame_count"] = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
                    target["fps"] = capture.get(cv2.CAP_PROP_FPS)
                    capture.release()
                # Only completed JSON files become visible to the job queue.
                pending_path = job_path.with_suffix(".json.part")
                checkpoint = QtCore.QElapsedTimer()
                checkpoint.start()
                with pending_path.open("w", encoding="utf-8") as output:
                    for chunk in json.JSONEncoder(indent=4).iterencode(workspace):
                        output.write(chunk)
                        if checkpoint.elapsed() >= 20:
                            self.process_events()
                            checkpoint.restart()
                            if self.cancel_requested:
                                break
                self.process_events()
                if self.cancel_requested:
                    pending_path.unlink()
                    break
                pending_path.rename(job_path)
                self.saved_names.append(job_path.stem)
                self.report_labels["Saved:"].setText(str(len(self.saved_names)))
                self.details.appendPlainText(job_path.stem)
                saved_jobs[job_path.stem] = workspace.copy()
                if self.remove_completed_checkbox.isChecked():
                    main_window = self.parentWidget()
                    if main_window.selected_video_button is media:
                        main_window.selected_video_button = None
                    main_window.targetVideosList.takeItem(media.get_item_position())
                    main_window.target_videos.pop(media.media_id)
                    media.deleteLater()
                    if not main_window.target_videos:
                        main_window.placeholder_update_signal.emit(
                            main_window.targetVideosList, False
                        )
                self.progress_bar.setValue(len(self.saved_names))
                self.process_events()
                if self.cancel_requested or self.stop_after_completion_checkbox.isChecked():
                    break
                if (
                    self.stop_after_processing_checkbox.isChecked()
                    and len(self.saved_names) >= self.stop_after_processing_spinbox.value()
                ):
                    break
        self.status_label.setText("Updating job list…")
        self.stop_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.remove_completed_checkbox.setEnabled(False)
        self.stop_after_completion_checkbox.setEnabled(False)
        self.stop_after_processing_row.setEnabled(False)
        self.status_label.repaint()
        if self.saved_names:
            job_manager_actions.refresh_new_jobs(
                self.parentWidget(), selected_job_name=self.saved_names[-1],
                saved_jobs=saved_jobs,
            )
        self.timer.stop()
        self.update_runtime()
        self.is_finished = True
        self.report_labels["Cancelled:"].setText(str(self.started_count - len(self.saved_names)))
        if self.cancel_requested:
            self.status_label.setText("Cancelled.")
        elif len(self.saved_names) < len(self.media_items):
            self.status_label.setText("Stopped.")
        else:
            self.status_label.setText("Done.")
            if not self.media_items:
                self.progress_bar.setRange(0, 1)
                self.progress_bar.setValue(1)
                self.progress_bar.setFormat("100% - 0 / 0 jobs saved")
        self.cancel_button.setText("Done")
        self.cancel_button.setEnabled(True)
        self.control_loop.exec()
        self.dialog_settings.setValue("geometry", self.saveGeometry())
