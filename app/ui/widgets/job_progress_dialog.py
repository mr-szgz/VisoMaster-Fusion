from PySide6 import QtCore, QtGui, QtWidgets

from app.ui.widgets.job_list_widgets import JobDataRole


class JobProgressDialog(QtWidgets.QDialog):
    """Progress for a saved-job queue, independent of media batch processing."""

    progressChanged = QtCore.Signal(int, int)
    stopRequested = QtCore.Signal()
    cancelRequested = QtCore.Signal()
    skipRequested = QtCore.Signal()

    def __init__(self, parent, job_items):
        super().__init__(parent)
        self.job_items = job_items
        self.total_jobs = len(job_items)
        self.completed_job_names = set()
        self.skipped_job_names = set()
        self.started_job_names = set()
        self.job_errors = {}
        self.current_index = 0
        self.current_job_name = ""
        self.setWindowTitle("Job Processing")
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
            "Length:",
        )):
            label = QtWidgets.QLabel(field, self)
            value = QtWidgets.QLabel(self)
            value.setWordWrap(True)
            value.setTextFormat(QtCore.Qt.PlainText)
            value.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            report.addWidget(label, row, 0)
            report.addWidget(value, row, 1)
            self.report_labels[field] = (label, value)
        layout.addLayout(report)
        properties_separator = QtWidgets.QFrame(self)
        properties_separator.setFrameShape(QtWidgets.QFrame.HLine)
        properties_separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(properties_separator)
        self.stop_after_completion_checkbox = QtWidgets.QCheckBox("Stop after current item", self)
        self.stop_after_completion_checkbox.setToolTip(
            "Finish and save the current job, then stop before loading the next job"
        )
        layout.addWidget(self.stop_after_completion_checkbox)
        buttons_separator = QtWidgets.QFrame(self)
        buttons_separator.setFrameShape(QtWidgets.QFrame.HLine)
        buttons_separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(buttons_separator)
        buttons = QtWidgets.QHBoxLayout()
        self.runtime_label = QtWidgets.QLabel("Runtime: 00:00:00", self)
        buttons.addWidget(self.runtime_label)
        buttons.addStretch()
        self.skip_button = QtWidgets.QPushButton("Skip", self)
        self.skip_button.setAutoDefault(False)
        self.skip_button.setEnabled(False)
        self.skip_button.setToolTip("Skip the current job and continue to the next")
        self.skip_button.clicked.connect(self.skip_current_job)
        buttons.addWidget(self.skip_button)
        self.stop_button = QtWidgets.QPushButton("Stop", self)
        self.stop_button.setAutoDefault(False)
        self.stop_button.setToolTip("Save the current output and stop the job queue")
        self.stop_button.clicked.connect(self.stopRequested.emit)
        buttons.addWidget(self.stop_button)
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

    @QtCore.Slot(int, int)
    def queue_ready(self, total, skipped):
        self.total_jobs = total
        self.progress_bar.setRange(0, total)
        self.progressChanged.emit(0, total)

    @QtCore.Slot(str, int)
    def job_started(self, job_name, index):
        item = self.job_items[job_name]
        self.started_job_names.add(job_name)
        self.current_index = index
        self.current_job_name = job_name
        self.skip_button.setEnabled(False)
        frames = item.data(JobDataRole.FrameCountRole)
        fps = item.data(JobDataRole.FrameRateRole)
        values = {
            "Embedding:": ", ".join(item.data(JobDataRole.EmbeddingNamesRole)),
            "Frames:": f"{frames:,}",
        }
        for field, value in values.items():
            self.report_labels[field][1].setText(value)
        for field in ("Frame rate:", "Length:"):
            for label in self.report_labels[field]:
                label.setVisible(fps > 0)
        if fps > 0:
            hours, remainder = divmod(int(frames / fps), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.report_labels["Frame rate:"][1].setText(f"{fps:g} fps")
            self.report_labels["Length:"][1].setText(f"{hours:02}:{minutes:02}:{seconds:02}")
        self.status_label.setText(f"Loading job {index}/{self.total_jobs}: {job_name}")
        self.progressChanged.emit(index, self.total_jobs)

    @QtCore.Slot()
    def processing_started(self):
        self.skip_button.setEnabled(True)
        self.status_label.setText(
            f"Processing job ({self.current_index}/{self.total_jobs}): {self.current_job_name}"
        )

    @QtCore.Slot(str)
    def job_completed(self, job_name):
        self.completed_job_names.add(job_name)
        self.skip_button.setEnabled(False)
        self.progress_bar.setValue(self.current_index)
        self.status_label.setText(f"Completed job {self.current_index}/{self.total_jobs}: {job_name}")

    def skip_current_job(self):
        self.skip_button.setEnabled(False)
        self.skipRequested.emit()

    @QtCore.Slot(str)
    def job_skipped(self, job_name):
        self.skipped_job_names.add(job_name)
        self.progress_bar.setValue(self.current_index)

    @QtCore.Slot(str, str)
    def job_failed(self, job_name, error):
        self.job_errors[job_name] = error

    def stopping(self):
        self.stop_after_completion_checkbox.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.status_label.setText("Stopping job processing…")

    def update_runtime(self):
        hours, remainder = divmod(self.runtime_clock.elapsed() // 1000, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.runtime_label.setText(f"Runtime: {hours:02}:{minutes:02}:{seconds:02}")

    def minimize(self):
        self.hide()

    def reject(self):
        self.minimize()

    def closeEvent(self, event):
        event.ignore()
        self.minimize()

    def finish(self):
        self.runtime_timer.stop()
        self.update_runtime()
        self.hide()

    def show_result(self, processor, command):
        unfinished = self.started_job_names - self.completed_job_names - self.skipped_job_names
        ended_early = processor.batch_cancelled or processor.batch_stopped
        failed = unfinished.intersection(self.job_errors) if ended_early else unfinished
        interrupted = unfinished - failed
        stopped = len(interrupted) if processor.batch_stopped else 0
        cancelled = len(interrupted) if processor.batch_cancelled else 0
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
        report = QtWidgets.QDialog(self.parentWidget())
        report.setWindowTitle(title)
        report.setSizeGripEnabled(True)
        layout = QtWidgets.QVBoxLayout(report)
        summary = QtWidgets.QLabel(report)
        summary.setTextFormat(QtCore.Qt.PlainText)
        summary.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        summary.setText(
            f"{command}\n\n"
            f"Queued: {len(processor.jobs)}\n"
            f"Completed: {len(self.completed_job_names)}\n"
            f"Failed: {len(failed)}\n"
            f"Skipped: {len(processor.skipped_jobs)}\n"
            f"Stopped: {stopped}\n"
            f"Cancelled: {cancelled}\n"
            f"Not started: {not_started}\n\n"
            f"{self.runtime_label.text()}"
        )
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
        if stopped:
            details.extend(["", "Stopped jobs:", *sorted(interrupted)])
        if cancelled:
            details.extend(["", "Cancelled jobs:", *sorted(interrupted)])
        layout.addWidget(summary)
        detail_text = QtWidgets.QPlainTextEdit(report)
        detail_text.setReadOnly(True)
        detail_text.setPlainText("\n".join(details))
        detail_text.hide()
        layout.addWidget(detail_text, 1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok, report)
        buttons.accepted.connect(report.accept)
        details_button = buttons.addButton("Show Details…", QtWidgets.QDialogButtonBox.ActionRole)
        details_button.setCheckable(True)
        details_button.toggled.connect(detail_text.setVisible)
        details_button.toggled.connect(
            lambda checked: details_button.setText("Hide Details…" if checked else "Show Details…")
        )
        layout.addWidget(buttons)
        for button in report.findChildren(QtWidgets.QPushButton):
            button.setMinimumWidth(button.fontMetrics().horizontalAdvance(button.text()) + 48)
        report.resize(report.sizeHint().width() * 2, report.sizeHint().height())
        report.exec()
        report.deleteLater()
