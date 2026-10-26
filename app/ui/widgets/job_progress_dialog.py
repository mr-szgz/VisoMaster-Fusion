from PySide6 import QtCore, QtGui, QtWidgets
from functools import partial
from math import ceil

from app.settings import settings_group
from app.ui.widgets.job_list_widgets import JobDataRole


class JobProgressDialog(QtWidgets.QDialog):
    """Progress for a saved-job queue, independent of media batch processing."""

    progressChanged = QtCore.Signal(int, int)
    stopRequested = QtCore.Signal()
    renderLimitReached = QtCore.Signal(bool)
    cancelRequested = QtCore.Signal()
    skipRequested = QtCore.Signal(bool)
    skipAndUpdateRequested = QtCore.Signal(bool)
    stopAndUpdateRequested = QtCore.Signal(bool)

    def __init__(self, parent, job_items):
        super().__init__(parent)
        self.job_items = job_items
        self.is_finished = False
        self.parameter_overrides = {}
        self.total_jobs = len(job_items)
        self.completed_job_names = set()
        self.skipped_job_names = set()
        self.started_job_names = set()
        self.job_errors = {}
        self.current_index = 0
        self.current_job_name = ""
        self.processing_rate_clock = QtCore.QElapsedTimer()
        self.processed_frames_since_update = 0
        self.completed_frames = 0
        self.total_frames = 0
        self.total_render_seconds = 0.0
        self.item_render_seconds = 0.0
        self.render_frame_rate = 0.0
        self.setWindowTitle("Job Processing")
        self.setObjectName("jobProgressDialog")
        self.setWindowIcon(QtGui.QIcon(":/media/media/visomaster_small.png"))
        self.setWindowFlag(QtCore.Qt.WindowMinimizeButtonHint, True)
        self.setMinimumWidth(540)

        layout = QtWidgets.QVBoxLayout(self)
        self.progress_bar = QtWidgets.QProgressBar(self)
        self.progress_bar.setRange(0, self.total_jobs)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m jobs")
        self.status_label = QtWidgets.QLabel("Preparing saved jobs…", self)
        self.status_label.setTextFormat(QtCore.Qt.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        report = QtWidgets.QGridLayout()
        report.setColumnStretch(1, 1)
        self.report_labels = {}
        for row, field in enumerate((
            "Embedding:", "Frames:", "Frame rate:",
            "Length:", "frame/s:", "Item progress:",
        )):
            label = QtWidgets.QLabel(field, self)
            value = QtWidgets.QLabel(self)
            value.setWordWrap(True)
            value.setTextFormat(QtCore.Qt.PlainText)
            value.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            report.addWidget(label, row, 0)
            report.addWidget(value, row, 1)
            self.report_labels[field] = (label, value)
        self.report_labels["frame/s:"][1].setText("0.00")
        self.report_labels["Item progress:"][1].setText("0.0%")
        self.eta_label = QtWidgets.QLabel("ETA: --:--:--", self)
        report.addWidget(self.eta_label, row, 2)
        layout.addLayout(report)
        metrics = QtWidgets.QFormLayout()
        for field in ("Completed:", "Failed:", "Skipped:"):
            label = QtWidgets.QLabel(field, self)
            value = QtWidgets.QLabel("0", self)
            value.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            metrics.addRow(label, value)
            self.report_labels[field] = (label, value)
        layout.addLayout(metrics)
        self.detail_text = QtWidgets.QPlainTextEdit(self)
        self.detail_text.setReadOnly(True)
        self.detail_text.hide()
        layout.addWidget(self.detail_text)
        self.details_button = QtWidgets.QPushButton("Show Details…", self)
        self.details_button.setAutoDefault(False)
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self.detail_text.setVisible)
        self.details_button.toggled.connect(
            lambda checked: self.details_button.setText("Hide Details…" if checked else "Show Details…")
        )
        self.details_button.hide()
        layout.addWidget(self.details_button)
        properties_separator = QtWidgets.QFrame(self)
        properties_separator.setFrameShape(QtWidgets.QFrame.HLine)
        properties_separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(properties_separator)
        self.lock_parameters_checkbox = QtWidgets.QCheckBox("Lock Parameters", self)
        self.lock_parameters_checkbox.setToolTip(
            "Carry subsequent edits in Swap strength and likeness, Masks, Textures and colors, "
            "Blend Adjustments, and Hair Matting (MODNet) to all faces and markers in following jobs. "
            "Each job keeps its swapper model. Uncheck to clear carried edits; "
            "current settings stay unchanged. Applies only to this queue run."
        )
        self.lock_parameters_checkbox.toggled.connect(lambda: self.parameter_overrides.clear())
        layout.addWidget(self.lock_parameters_checkbox)
        self.stop_after_completion_checkbox = QtWidgets.QCheckBox("Stop after current item", self)
        self.stop_after_completion_checkbox.setToolTip(
            "Finish and save the current job, then stop before loading the next job"
        )
        layout.addWidget(self.stop_after_completion_checkbox)
        self.stop_on_job_errors_checkbox = QtWidgets.QCheckBox("Stop on job errors", self)
        self.stop_on_job_errors_checkbox.setToolTip(
            "Stop the queue when a job fails. When unchecked, skip failed jobs and continue."
        )
        layout.addWidget(self.stop_on_job_errors_checkbox)
        self.save_partial_on_skip_checkbox = QtWidgets.QCheckBox("Save partial videos", self)
        self.save_partial_on_skip_checkbox.setToolTip(
            "Save the recorded portion before skipping or stopping and updating the job"
        )
        layout.addWidget(self.save_partial_on_skip_checkbox)
        self.stop_after_processing_row = QtWidgets.QWidget(self)
        self.stop_after_processing_row.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed
        )
        stop_limit_layout = QtWidgets.QHBoxLayout(self.stop_after_processing_row)
        stop_limit_layout.setContentsMargins(0, 0, 0, 0)
        self.stop_after_processing_checkbox = QtWidgets.QCheckBox("Stop after processing", self.stop_after_processing_row)
        self.stop_after_processing_checkbox.setToolTip("Stop the queue once the completed job count reaches the limit")
        self.stop_after_processing_spinbox = QtWidgets.QSpinBox(self.stop_after_processing_row)
        self.stop_after_processing_spinbox.setRange(1, 2147483647)
        self.stop_after_processing_spinbox.setValue(100)
        self.stop_after_processing_spinbox.setSuffix(" items")
        stop_limit_layout.addWidget(self.stop_after_processing_checkbox)
        stop_limit_layout.addWidget(self.stop_after_processing_spinbox)
        stop_limit_layout.addStretch()
        layout.addWidget(self.stop_after_processing_row)
        self.stop_after_rendering_row = QtWidgets.QWidget(self)
        self.stop_after_rendering_row.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed
        )
        render_limit_layout = QtWidgets.QHBoxLayout(self.stop_after_rendering_row)
        render_limit_layout.setContentsMargins(0, 0, 0, 0)
        self.stop_after_rendering_checkbox = QtWidgets.QCheckBox("Stop after rendering", self.stop_after_rendering_row)
        self.stop_after_rendering_checkbox.setToolTip(
            "Finish and save the current job, then stop when Total Render reaches the selected length"
        )
        self.stop_after_rendering_timeedit = QtWidgets.QTimeEdit(self.stop_after_rendering_row)
        self.stop_after_rendering_timeedit.setDisplayFormat("HH:mm:ss")
        self.stop_after_rendering_timeedit.setTime(QtCore.QTime(1, 0, 0))
        render_limit_layout.addWidget(self.stop_after_rendering_checkbox)
        render_limit_layout.addWidget(self.stop_after_rendering_timeedit)
        render_limit_layout.addStretch()
        layout.addWidget(self.stop_after_rendering_row)
        self.suppress_notifications_checkbox = QtWidgets.QCheckBox("Suppress notifications", self)
        self.suppress_notifications_checkbox.setObjectName("suppressBatchNotificationsCheckbox")
        self.suppress_notifications_checkbox.setToolTip("Mute job message alerts and toast notifications")
        layout.addWidget(self.suppress_notifications_checkbox)
        self.update_partial_jobs_checkbox = QtWidgets.QCheckBox("Update partial jobs", self)
        self.update_partial_jobs_checkbox.setToolTip(
            "Show Skip and update job and Stop and update job in place of Skip and Stop"
        )
        layout.addWidget(self.update_partial_jobs_checkbox)
        self.dialog_settings = settings_group("Dialogs/JobProcessing", self)
        self.dialog_settings.remove("stop_after_completion_checkbox")
        for name in (
            "save_partial_on_skip_checkbox", "stop_after_processing_checkbox",
            "suppress_notifications_checkbox", "update_partial_jobs_checkbox",
            "stop_on_job_errors_checkbox",
            "stop_after_rendering_checkbox",
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
        if self.dialog_settings.contains("stop_after_rendering"):
            self.stop_after_rendering_timeedit.setTime(
                self.dialog_settings.value("stop_after_rendering", type=QtCore.QTime)
            )
        self.stop_after_rendering_timeedit.timeChanged.connect(
            partial(self.dialog_settings.setValue, "stop_after_rendering")
        )
        self.stop_after_rendering_timeedit.setEnabled(self.stop_after_rendering_checkbox.isChecked())
        self.stop_after_rendering_checkbox.toggled.connect(self.stop_after_rendering_timeedit.setEnabled)
        self.stop_after_rendering_checkbox.toggled.connect(self.update_render_limit)
        self.stop_after_rendering_timeedit.timeChanged.connect(self.update_render_limit)
        buttons_separator = QtWidgets.QFrame(self)
        buttons_separator.setFrameShape(QtWidgets.QFrame.HLine)
        buttons_separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(buttons_separator)
        render_metrics = QtWidgets.QFormLayout()
        for field in ("Total Render:", "Render/m:"):
            label = QtWidgets.QLabel(field, self)
            value = QtWidgets.QLabel("00:00:00", self)
            value.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            render_metrics.addRow(label, value)
            self.report_labels[field] = (label, value)
        layout.addLayout(render_metrics)
        buttons = QtWidgets.QHBoxLayout()
        self.runtime_label = QtWidgets.QLabel("Runtime: 00:00:00", self)
        buttons.addWidget(self.runtime_label)
        buttons.addStretch()
        self.skip_update_button = QtWidgets.QPushButton("Skip and update job", self)
        self.skip_update_button.setAutoDefault(False)
        self.skip_update_button.setEnabled(False)
        self.skip_update_button.setToolTip(
            "Skip this job and keep it in the queue, starting from the currently rendered frame next time"
        )
        self.skip_update_button.clicked.connect(self.skip_and_update_current_job)
        buttons.addWidget(self.skip_update_button)
        self.skip_button = QtWidgets.QPushButton("Skip", self)
        self.skip_button.setAutoDefault(False)
        self.skip_button.setEnabled(False)
        self.skip_button.setToolTip("Skip the current job and continue to the next")
        self.skip_button.clicked.connect(self.skip_current_job)
        buttons.addWidget(self.skip_button)
        self.stop_update_button = QtWidgets.QPushButton("Stop and update job", self)
        self.stop_update_button.setAutoDefault(False)
        self.stop_update_button.setEnabled(False)
        self.stop_update_button.setToolTip(
            "Stop the queue and keep this job, starting from the currently rendered frame next time"
        )
        self.stop_update_button.clicked.connect(self.stop_and_update_current_job)
        buttons.addWidget(self.stop_update_button)
        self.stop_button = QtWidgets.QPushButton("Stop", self)
        self.stop_button.setAutoDefault(False)
        self.stop_button.setToolTip("Save the current output and stop the job queue")
        self.stop_button.clicked.connect(self.stopRequested.emit)
        buttons.addWidget(self.stop_button)
        self.update_partial_jobs_checkbox.toggled.connect(self.show_update_job_buttons)
        self.show_update_job_buttons(self.update_partial_jobs_checkbox.isChecked())
        self.cancel_button = QtWidgets.QPushButton("Cancel", self)
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.setToolTip("Interrupt the current job without saving its output")
        self.cancel_button.clicked.connect(self.cancelRequested.emit)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        self.runtime_clock = QtCore.QElapsedTimer()
        self.runtime_clock.start()
        self.runtime_timer = QtCore.QTimer(self)
        self.runtime_timer.timeout.connect(self.update_runtime)
        self.runtime_timer.start(1000)
        if self.dialog_settings.contains("geometry"):
            self.restoreGeometry(self.dialog_settings.value("geometry"))

    def record_parameter_edit(self, name, value):
        if self.lock_parameters_checkbox.isChecked():
            from app.ui.widgets.swapper_layout_data import SWAPPER_LAYOUT_DATA

            if any(name in SWAPPER_LAYOUT_DATA[section] for section in (
                "Swap strength and likeness", "Masks",
                "Textures and colors", "Blend Adjustments",
                "Hair Matting (MODNet)",
            )):
                self.parameter_overrides[name] = value

    def apply_parameter_overrides(self):
        """Overlay only loaded runtime state, using the loader's normalized schema."""
        if not self.parameter_overrides:
            return
        from app.ui.widgets.actions import common_actions

        main_window = self.parentWidget()
        for parameters in main_window.parameters.values():
            parameters.update(self.parameter_overrides)
        for marker in main_window.markers.values():
            for parameters in marker["parameters"].values():
                parameters.update(self.parameter_overrides)
        main_window.current_widget_parameters.update(self.parameter_overrides)
        # Refresh only edited widgets; other controls retain the normal loader's state.
        for name, value in self.parameter_overrides.items():
            common_actions._set_single_widget_value(main_window.parameter_widgets[name], value)

    def show_update_job_buttons(self, checked):
        self.skip_update_button.setVisible(checked)
        self.stop_update_button.setVisible(checked)
        self.skip_button.setVisible(not checked)
        self.stop_button.setVisible(not checked)

    @QtCore.Slot(int, int)
    def queue_ready(self, total, skipped):
        self.total_jobs = total
        self.report_labels["Skipped:"][1].setText(str(skipped))
        self.progress_bar.setRange(0, total)
        self.progressChanged.emit(0, total)

    @QtCore.Slot(str, int)
    def job_started(self, job_name, index):
        item = self.job_items[job_name]
        self.started_job_names.add(job_name)
        self.current_index = index
        self.current_job_name = job_name
        self.skip_update_button.setEnabled(False)
        self.stop_update_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        frames = item.data(JobDataRole.FrameCountRole)
        self.total_frames = frames
        self.completed_frames = 0
        self.report_labels["Item progress:"][1].setText("0.0%")
        self.eta_label.setText("ETA: --:--:--")
        fps = item.data(JobDataRole.FrameRateRole)
        self.total_render_seconds += self.item_render_seconds
        self.item_render_seconds = 0.0
        self.render_frame_rate = 0.0
        values = {
            "Embedding:": ", ".join(item.data(JobDataRole.EmbeddingNamesRole)),
            "Frames:": f"{frames:,}" if frames is not None else "",
        }
        for field, value in values.items():
            self.report_labels[field][1].setText(value)
        for field, visible in (("Frames:", frames is not None),
                               ("Frame rate:", fps is not None and fps > 0),
                               ("Length:", frames is not None and fps is not None and fps > 0)):
            for label in self.report_labels[field]:
                label.setVisible(visible)
        if fps is not None and fps > 0:
            self.render_frame_rate = fps
            self.report_labels["Frame rate:"][1].setText(f"{fps:g} fps")
        if frames is not None and fps is not None and fps > 0:
            hours, remainder = divmod(int(frames / fps), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.report_labels["Length:"][1].setText(f"{hours:02}:{minutes:02}:{seconds:02}")
        self.status_label.setText(f"Loading job {index}/{self.total_jobs}: {job_name}")
        self.progressChanged.emit(index, self.total_jobs)

    @QtCore.Slot()
    def processing_started(self):
        processor = self.parentWidget().video_processor
        if processor.is_processing_segments:
            self.total_frames = sum(end - start + 1 for start, end in processor.segments_to_process)
        else:
            self.total_frames = processor.max_frame_number - processor.next_frame_to_display + 1
        self.completed_frames = 0
        self.processed_frames_since_update = 0
        self.processing_rate_clock.start()
        self.eta_label.setText("ETA: --:--:--")
        self.report_labels["frame/s:"][1].setText("0.00")
        self.skip_update_button.setEnabled(False)
        self.stop_update_button.setEnabled(False)
        self.skip_button.setEnabled(True)
        self.status_label.setText(
            f"Processing job ({self.current_index}/{self.total_jobs}): {self.current_job_name}"
        )

    @QtCore.Slot()
    def frame_processed(self):
        if self.processing_rate_clock.isValid():
            self.processed_frames_since_update += 1

    @QtCore.Slot()
    def processing_stopped(self):
        self.skip_button.setEnabled(False)
        self.skip_update_button.setEnabled(False)
        self.stop_update_button.setEnabled(False)
        self.update_runtime()
        self.processing_rate_clock.invalidate()
        if self.completed_frames != self.total_frames:
            self.eta_label.setText("ETA: --:--:--")
        self.processed_frames_since_update = 0
        self.report_labels["frame/s:"][1].setText("0.00")

    @QtCore.Slot(str)
    def job_completed(self, job_name):
        self.completed_job_names.add(job_name)
        self.report_labels["Completed:"][1].setText(str(len(self.completed_job_names)))
        self.completed_frames = self.total_frames
        self.report_labels["Item progress:"][1].setText("100.0%")
        self.eta_label.setText("ETA: 00:00:00")
        self.skip_update_button.setEnabled(False)
        self.stop_update_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.progress_bar.setValue(self.current_index)
        self.status_label.setText(f"Completed job {self.current_index}/{self.total_jobs}: {job_name}")

    def skip_current_job(self):
        self.skip_update_button.setEnabled(False)
        self.stop_update_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.skipRequested.emit(self.save_partial_on_skip_checkbox.isChecked())

    def skip_and_update_current_job(self):
        self.skip_update_button.setEnabled(False)
        self.stop_update_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.skipAndUpdateRequested.emit(self.save_partial_on_skip_checkbox.isChecked())

    def stop_and_update_current_job(self):
        self.stopping()
        self.stopAndUpdateRequested.emit(self.save_partial_on_skip_checkbox.isChecked())

    @QtCore.Slot(str)
    def job_skipped(self, job_name):
        self.skipped_job_names.add(job_name)
        self.report_labels["Skipped:"][1].setText(
            str(len(self.job_items) - self.total_jobs + len(self.skipped_job_names))
        )
        self.progress_bar.setValue(self.current_index)

    @QtCore.Slot(str, str)
    def job_failed(self, job_name, error):
        self.job_errors[job_name] = error
        self.report_labels["Failed:"][1].setText(str(len(self.started_job_names.intersection(self.job_errors))))

    def stopping(self):
        self.stop_on_job_errors_checkbox.setEnabled(False)
        self.update_partial_jobs_checkbox.setEnabled(False)
        self.stop_after_completion_checkbox.setEnabled(False)
        self.stop_after_processing_row.setEnabled(False)
        self.stop_after_rendering_row.setEnabled(False)
        self.skip_update_button.setEnabled(False)
        self.stop_update_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.status_label.setText("Stopping job processing…")

    def update_render_limit(self):
        limit = QtCore.QTime(0, 0, 0).secsTo(self.stop_after_rendering_timeedit.time())
        self.renderLimitReached.emit(
            self.stop_after_rendering_checkbox.isChecked()
            and self.total_render_seconds + self.item_render_seconds >= limit
        )

    def update_runtime(self):
        hours, remainder = divmod(self.runtime_clock.elapsed() // 1000, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.runtime_label.setText(f"Runtime: {hours:02}:{minutes:02}:{seconds:02}")
        if self.processing_rate_clock.isValid():
            self.completed_frames = self.parentWidget().video_processor.media_pipeline.absolute_frames_processed
            if self.render_frame_rate > 0:
                self.item_render_seconds = self.completed_frames / self.render_frame_rate
            hours, remainder = divmod(int(self.total_render_seconds + self.item_render_seconds), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.report_labels["Total Render:"][1].setText(f"{hours:02}:{minutes:02}:{seconds:02}")
            self.update_render_limit()
            processor = self.parentWidget().video_processor
            self.skip_update_button.setEnabled(
                self.skip_button.isEnabled()
                and 0 < self.completed_frames < self.total_frames
                and processor.last_displayed_frame is not None
            )
            self.stop_update_button.setEnabled(self.skip_update_button.isEnabled())
            self.report_labels["Item progress:"][1].setText(
                f"{self.completed_frames / self.total_frames:.1%}"
            )
            elapsed_seconds = self.processing_rate_clock.nsecsElapsed() / 1_000_000_000
            rate = self.processed_frames_since_update / elapsed_seconds
            self.report_labels["frame/s:"][1].setText(f"{rate:.2f}")
            if self.completed_frames == self.total_frames:
                self.eta_label.setText("ETA: 00:00:00")
            elif rate > 0:
                remaining_frames = self.total_frames - self.completed_frames
                hours, remainder = divmod(ceil(remaining_frames / rate), 3600)
                minutes, seconds = divmod(remainder, 60)
                self.eta_label.setText(f"ETA: {hours:02}:{minutes:02}:{seconds:02}")
            else:
                self.eta_label.setText("ETA: --:--:--")
            self.processed_frames_since_update = 0
            self.processing_rate_clock.restart()
        rendered_per_minute = (
            (self.total_render_seconds + self.item_render_seconds)
            * 60_000_000_000 / self.runtime_clock.nsecsElapsed()
        )
        hours, remainder = divmod(int(rendered_per_minute), 3600)
        minutes, seconds = divmod(remainder, 60)
        self.report_labels["Render/m:"][1].setText(f"{hours:02}:{minutes:02}:{seconds:02}")

    def minimize(self):
        self.hide()

    def reject(self):
        if self.is_finished:
            super().reject()
        else:
            self.minimize()

    def closeEvent(self, event):
        if self.is_finished:
            super().closeEvent(event)
        else:
            event.ignore()
            self.minimize()

    def finish(self):
        self.lock_parameters_checkbox.setChecked(False)
        self.lock_parameters_checkbox.setEnabled(False)
        self.setObjectName("")
        self.dialog_settings.setValue("geometry", self.saveGeometry())
        self.runtime_timer.stop()
        self.update_runtime()
        self.processing_rate_clock.invalidate()
        self.stopping()
        self.save_partial_on_skip_checkbox.setEnabled(False)
        self.suppress_notifications_checkbox.setEnabled(False)
        self.status_label.setText("Job processing finished. Restoring workspace…")

    def show_result(self, processor, command):
        unfinished = self.started_job_names - self.completed_job_names - self.skipped_job_names
        ended_early = processor.batch_cancelled or processor.batch_stopped
        failed = unfinished.intersection(self.job_errors) if ended_early else unfinished
        failed |= self.started_job_names.intersection(self.job_errors) - self.completed_job_names
        not_started = (len(processor.jobs) - len(self.started_job_names)
                       - len(processor.skipped_jobs) + len(self.skipped_job_names))
        if processor.batch_cancelled:
            title = "Job Processing Cancelled"
        elif processor.batch_stopped:
            title = "Job Processing Stopped"
        elif processor.batch_succeeded:
            title = "Job Processing Complete"
        else:
            title = "Job Processing Failed"
        self.setWindowTitle(title)
        restoration = (
            "Workspace restoration skipped after processing timeout."
            if processor.processing_timed_out else "Workspace restoration finished."
        )
        self.status_label.setText(f"{command}: {title}. {restoration}")
        values = {
            "Completed:": len(self.completed_job_names),
            "Failed:": len(failed),
            "Skipped:": len(processor.skipped_jobs),
        }
        for field, value in values.items():
            self.report_labels[field][1].setText(str(value))
        self.progress_bar.setRange(0, len(processor.jobs))
        self.progress_bar.setValue(len(processor.jobs) - not_started)
        details = ["Queued jobs:", *processor.jobs]
        if self.completed_job_names:
            details.extend(["", "Completed jobs:", *sorted(self.completed_job_names),
                            f"Completed job files: {processor.completed_dir}"])
        if self.job_errors:
            details.extend(["", "Errors:", *(
                f"{name}: {error}" for name, error in self.job_errors.items()
            )])
        if processor.skipped_jobs:
            details.extend(["", "Skipped jobs:", *processor.skipped_jobs])
        self.detail_text.setPlainText("\n".join(details))
        self.details_button.show()
        self.is_finished = True
        self.cancel_button.clicked.disconnect(self.cancelRequested.emit)
        self.cancel_button.clicked.connect(self.accept)
        self.cancel_button.setText("Close")
        self.cancel_button.setToolTip("Close the job processing report")
        self.cancel_button.setEnabled(True)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.showNormal()
        self.raise_()
        self.activateWindow()
