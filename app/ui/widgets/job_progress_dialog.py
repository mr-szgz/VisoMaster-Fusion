from PySide6 import QtCore, QtGui, QtWidgets

from app.ui.widgets.job_list_widgets import JobDataRole


class JobProgressDialog(QtWidgets.QDialog):
    """Progress for a saved-job queue, independent of media batch processing."""

    minimizedChanged = QtCore.Signal(bool)
    progressChanged = QtCore.Signal(int, int)
    stopRequested = QtCore.Signal()

    def __init__(self, parent, job_items):
        super().__init__(parent)
        self.job_items = job_items
        self.total_jobs = len(job_items)
        self.completed_job_names = set()
        self.started_job_names = set()
        self.job_errors = {}
        self.current_index = 0
        self.setWindowTitle("Job Processing")
        self.setWindowIcon(QtGui.QIcon(":/media/media/visomaster_small.png"))
        self.setWindowFlag(QtCore.Qt.WindowMinimizeButtonHint, True)
        self.setMinimumWidth(540)

        layout = QtWidgets.QVBoxLayout(self)
        self.status_label = QtWidgets.QLabel("Preparing saved jobs…", self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        report = QtWidgets.QGridLayout()
        report.setColumnStretch(1, 1)
        self.report_labels = {}
        for row, field in enumerate((
            "Job:", "Target media:", "Embedding:", "Frames:", "Frame rate:",
            "Length:", "Output file name:", "Cluster output by source:",
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
        self.progress_bar = QtWidgets.QProgressBar(self)
        self.progress_bar.setRange(0, self.total_jobs)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m jobs completed")
        layout.addWidget(self.progress_bar)
        self.skipped_label = QtWidgets.QLabel(self)
        layout.addWidget(self.skipped_label)
        buttons = QtWidgets.QHBoxLayout()
        self.runtime_label = QtWidgets.QLabel("Runtime: 00:00:00", self)
        buttons.addWidget(self.runtime_label)
        buttons.addStretch()
        self.minimize_button = QtWidgets.QPushButton("Minimize", self)
        self.minimize_button.clicked.connect(self.minimize)
        buttons.addWidget(self.minimize_button)
        self.stop_button = QtWidgets.QPushButton("Stop Processing", self)
        self.stop_button.setAutoDefault(False)
        self.stop_button.clicked.connect(self.stopRequested.emit)
        buttons.addWidget(self.stop_button)
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
        self.skipped_label.setText(f"Skipped jobs: {skipped}")
        self.progressChanged.emit(0, total)

    @QtCore.Slot(str, int)
    def job_started(self, job_name, index):
        item = self.job_items[job_name]
        self.started_job_names.add(job_name)
        self.current_index = index
        frames = item.data(JobDataRole.FrameCountRole)
        fps = item.data(JobDataRole.FrameRateRole)
        values = {
            "Job:": job_name,
            "Target media:": item.data(JobDataRole.TargetMediaPathRole),
            "Embedding:": ", ".join(item.data(JobDataRole.EmbeddingNamesRole)),
            "Frames:": f"{frames:,}",
            "Output file name:": job_name if item.data(JobDataRole.UseJobNameForOutputRole)
            else item.data(JobDataRole.OutputFileNameRole),
            "Cluster output by source:": "Yes" if item.data(JobDataRole.RestoreSelectedFaceRole) else "No",
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
        self.status_label.setText(f"Loading job {index}/{self.total_jobs}…")
        self.progressChanged.emit(index, self.total_jobs)

    @QtCore.Slot()
    def processing_started(self):
        self.status_label.setText(f"Processing job {self.current_index}/{self.total_jobs}…")

    @QtCore.Slot(str)
    def job_completed(self, job_name):
        self.completed_job_names.add(job_name)
        completed = len(self.completed_job_names)
        self.progress_bar.setValue(completed)
        self.status_label.setText(f"Completed {completed}/{self.total_jobs} jobs")

    @QtCore.Slot(str, str)
    def job_failed(self, job_name, error):
        self.job_errors[job_name] = error

    def stopping(self):
        self.stop_button.setEnabled(False)
        self.status_label.setText("Stopping job processing…")

    def update_runtime(self):
        hours, remainder = divmod(self.runtime_clock.elapsed() // 1000, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.runtime_label.setText(f"Runtime: {hours:02}:{minutes:02}:{seconds:02}")

    def minimize(self):
        self.hide()
        self.minimizedChanged.emit(True)

    def showEvent(self, event):
        super().showEvent(event)
        self.minimizedChanged.emit(False)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.WindowStateChange and self.isMinimized():
            self.setWindowState(QtCore.Qt.WindowNoState)
            self.minimize()

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
        unfinished = self.started_job_names - self.completed_job_names
        failed = unfinished.intersection(self.job_errors) if processor.batch_cancelled else unfinished
        interrupted = unfinished - failed
        stopped = len(interrupted) if processor.batch_cancelled else 0
        not_started = len(processor.jobs) - len(self.started_job_names) - len(processor.skipped_jobs)
        if processor.batch_cancelled:
            title = "Job Processing Stopped"
        elif processor.batch_succeeded:
            title = "Job Processing Complete"
        else:
            title = "Job Processing Failed"
        report = QtWidgets.QMessageBox(self.parentWidget())
        report.setWindowTitle(title)
        report.setTextFormat(QtCore.Qt.PlainText)
        report.setIcon(
            QtWidgets.QMessageBox.Warning if not processor.batch_succeeded and not processor.batch_cancelled
            else QtWidgets.QMessageBox.Information
        )
        report.setText(
            f"{command}\n\n"
            f"Queued: {len(processor.jobs)}\n"
            f"Completed: {len(self.completed_job_names)}\n"
            f"Failed: {len(failed)}\n"
            f"Skipped: {len(processor.skipped_jobs)}\n"
            f"Stopped: {stopped}\n"
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
        report.setDetailedText("\n".join(details))
        for button in report.findChildren(QtWidgets.QPushButton):
            button.setMinimumWidth(button.fontMetrics().horizontalAdvance(button.text()) + 48)
        report.exec()
        report.deleteLater()
