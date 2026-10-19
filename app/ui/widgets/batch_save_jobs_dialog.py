import json
from functools import partial
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from app.settings import settings_group


class BatchSaveJobsDialog(QtWidgets.QDialog):
    """Create job files with cooperative cancellation during JSON writing."""

    minimizedChanged = QtCore.Signal(bool)

    def __init__(self, parent, media_items):
        super().__init__(parent)
        self.media_items = media_items
        self.saved_names = []
        self.started_count = 0
        self.cancel_requested = False
        self.is_finished = False
        self.setWindowTitle("Saving Batch Jobs")
        self.setWindowIcon(QtGui.QIcon(":/media/media/visomaster_small.png"))
        self.setWindowFlag(QtCore.Qt.WindowMinimizeButtonHint, True)
        self.setMinimumWidth(540)
        layout = QtWidgets.QVBoxLayout(self)
        self.status_label = QtWidgets.QLabel("Preparing job configuration…", self)
        self.status_label.setTextFormat(QtCore.Qt.PlainText)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.progress_bar = QtWidgets.QProgressBar(self)
        self.progress_bar.setRange(0, len(media_items))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m jobs saved")
        layout.addWidget(self.progress_bar)
        self.remove_completed_checkbox = QtWidgets.QCheckBox("Clear target media", self)
        self.remove_completed_checkbox.setToolTip(
            "Remove items from the target list after their jobs have been saved"
        )
        layout.addWidget(self.remove_completed_checkbox)
        self.stop_after_completion_checkbox = QtWidgets.QCheckBox("Stop after current item", self)
        layout.addWidget(self.stop_after_completion_checkbox)
        self.stop_after_processing_row = QtWidgets.QWidget(self)
        stop_limit_layout = QtWidgets.QHBoxLayout(self.stop_after_processing_row)
        stop_limit_layout.setContentsMargins(0, 0, 0, 0)
        self.stop_after_processing_checkbox = QtWidgets.QCheckBox("Stop after processing", self.stop_after_processing_row)
        self.stop_after_processing_checkbox.setToolTip("Stop the batch once the saved job count reaches the limit")
        self.stop_after_processing_spinbox = QtWidgets.QSpinBox(self.stop_after_processing_row)
        self.stop_after_processing_spinbox.setRange(1, 2147483647)
        self.stop_after_processing_spinbox.setValue(100)
        self.stop_after_processing_spinbox.setSuffix(" items")
        stop_limit_layout.addWidget(self.stop_after_processing_checkbox)
        stop_limit_layout.addWidget(self.stop_after_processing_spinbox)
        stop_limit_layout.addStretch()
        layout.addWidget(self.stop_after_processing_row)
        self.suppress_notifications_checkbox = QtWidgets.QCheckBox("Suppress notifications", self)
        self.suppress_notifications_checkbox.setToolTip("Suppress the batch job saving result popup")
        layout.addWidget(self.suppress_notifications_checkbox)
        self.dialog_settings = settings_group("Dialogs/BatchSaveJobs", self)
        self.dialog_settings.remove("stop_after_completion_checkbox")
        for name in (
            "remove_completed_checkbox",
            "stop_after_processing_checkbox", "suppress_notifications_checkbox",
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
        layout.addLayout(buttons)
        self.clock = QtCore.QElapsedTimer()
        self.clock.start()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_runtime)
        self.timer.start(1000)
        if self.dialog_settings.contains("geometry"):
            self.restoreGeometry(self.dialog_settings.value("geometry"))

    def update_runtime(self):
        hours, remainder = divmod(self.clock.elapsed() // 1000, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.runtime_label.setText(f"Runtime: {hours:02}:{minutes:02}:{seconds:02}")

    def cancel(self):
        self.cancel_requested = True
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
        QtWidgets.QApplication.processEvents()
        if not self.cancel_requested and self.media_items:
            workspace = job_manager_actions._serialize_job_data(self.parentWidget())
            workspace["use_job_name_for_output"] = True
            workspace["output_file_name"] = None
            workspace["restore_selected_face"] = self.parentWidget().control["ClusterOutputBySourceToggle"]
            jobs_dir = job_manager_actions.get_jobs_dir(self.parentWidget())
            QtWidgets.QApplication.processEvents()
            for media in self.media_items:
                if self.cancel_requested:
                    break
                self.started_count += 1
                self.status_label.setText(
                    f"Creating job {self.started_count}/{len(self.media_items)}: {media.media_path}"
                )
                QtWidgets.QApplication.processEvents()
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
                # Only completed JSON files become visible to the job queue.
                pending_path = job_path.with_suffix(".json.part")
                checkpoint = QtCore.QElapsedTimer()
                checkpoint.start()
                with pending_path.open("w", encoding="utf-8") as output:
                    for chunk in json.JSONEncoder(indent=4).iterencode(workspace):
                        output.write(chunk)
                        if checkpoint.elapsed() >= 20:
                            QtWidgets.QApplication.processEvents()
                            checkpoint.restart()
                            if self.cancel_requested:
                                break
                QtWidgets.QApplication.processEvents()
                if self.cancel_requested:
                    pending_path.unlink()
                    break
                pending_path.rename(job_path)
                self.saved_names.append(job_path.stem)
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
                QtWidgets.QApplication.processEvents()
                if self.cancel_requested or self.stop_after_completion_checkbox.isChecked():
                    break
                if (
                    self.stop_after_processing_checkbox.isChecked()
                    and len(self.saved_names) >= self.stop_after_processing_spinbox.value()
                ):
                    break
        self.status_label.setText("Updating job list…")
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
        self.dialog_settings.setValue("geometry", self.saveGeometry())
        self.hide()
        if not self.suppress_notifications_checkbox.isChecked():
            self.show_result()

    def show_result(self):
        if self.cancel_requested:
            title = "Batch Job Saving Cancelled"
        elif len(self.saved_names) < len(self.media_items):
            title = "Batch Job Saving Stopped"
        else:
            title = "Batch Job Saving Complete"
        report = QtWidgets.QDialog(self.parentWidget())
        report.setWindowTitle(title)
        report.setMinimumWidth(540)
        report.setSizeGripEnabled(True)
        layout = QtWidgets.QVBoxLayout(report)
        summary = QtWidgets.QLabel(report)
        summary.setTextFormat(QtCore.Qt.PlainText)
        summary.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        summary.setText(
            f"Queued: {len(self.media_items)}\n"
            f"Saved: {len(self.saved_names)}\n"
            f"Cancelled: {self.started_count - len(self.saved_names)}\n"
            f"Not started: {len(self.media_items) - self.started_count}\n\n"
            f"{self.runtime_label.text()}"
        )
        layout.addWidget(summary)
        details = QtWidgets.QPlainTextEdit(report)
        details.setReadOnly(True)
        details.setPlainText("\n".join(["Saved jobs:", *self.saved_names]))
        details.hide()
        layout.addWidget(details)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok, report)
        buttons.accepted.connect(report.accept)
        toggle = buttons.addButton("Show Details…", QtWidgets.QDialogButtonBox.ActionRole)
        toggle.setCheckable(True)
        toggle.toggled.connect(details.setVisible)
        toggle.toggled.connect(lambda checked: toggle.setText("Hide Details…" if checked else "Show Details…"))
        layout.addWidget(buttons)
        report.exec()
        report.deleteLater()
