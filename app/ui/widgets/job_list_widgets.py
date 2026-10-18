import enum
import json
import re

import cv2
from PySide6 import QtCore, QtWidgets

from app.helpers.miscellaneous import get_file_type

class JobDataRole(enum.IntEnum):
    JobNameRole = 0x180
    FileInfoRole = 0x181
    TargetMediaIdRole = 0x182
    TargetMediaPathRole = 0x183
    MediaTypeRole = 0x184
    EmbeddingNamesRole = 0x185
    FrameCountRole = 0x186
    FrameRateRole = 0x187
    UseJobNameForOutputRole = 0x188
    OutputFileNameRole = 0x189
    RestoreSelectedFaceRole = 0x18A


class JobQueueListWidget(QtWidgets.QListWidget):
    """Promoted job queue list."""


class JobQueueListWidgetItem(QtWidgets.QListWidgetItem):
    def __init__(self, file_info: QtCore.QFileInfo):
        super().__init__()
        self.setData(JobDataRole.FileInfoRole, file_info)
        with open(file_info.filePath(), "r", encoding="utf-8") as job_file:
            job_data = json.load(job_file)
        self.setData(JobDataRole.UseJobNameForOutputRole, job_data["use_job_name_for_output"])
        self.setData(JobDataRole.OutputFileNameRole, job_data["output_file_name"])
        self.setData(
            JobDataRole.RestoreSelectedFaceRole,
            job_data["restore_selected_face"] if "restore_selected_face" in job_data
            else job_data["control"]["ClusterOutputBySourceToggle"],
        )
        target = next(
            media for media in job_data["target_medias_data"]
            if media["media_id"] == job_data["selected_media_id"]
        )
        self.setData(JobDataRole.TargetMediaIdRole, target["media_id"])
        self.setData(JobDataRole.TargetMediaPathRole, target["media_path"])
        self.setData(JobDataRole.MediaTypeRole, get_file_type(target["media_path"]))
        embedding_ids = dict.fromkeys(
            embedding_id
            for face in job_data["target_faces_data"].values()
            for embedding_id in face["assigned_merged_embeddings"]
        )
        self.setData(JobDataRole.EmbeddingNamesRole, [
            job_data["embeddings_data"][embedding_id]["embedding_name"]
            for embedding_id in embedding_ids
        ])
        if self.data(JobDataRole.MediaTypeRole) == "image":
            self.setData(JobDataRole.FrameCountRole, 1)
            self.setData(JobDataRole.FrameRateRole, 0.0)
        else:
            capture = cv2.VideoCapture()
            capture.setExceptionMode(True)
            capture.open(self.data(JobDataRole.TargetMediaPathRole))
            self.setData(JobDataRole.FrameCountRole, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
            self.setData(JobDataRole.FrameRateRole, capture.get(cv2.CAP_PROP_FPS))
            capture.release()

    def to_label(self, label_tpl: str) -> str:
        job_name = self.data(JobDataRole.JobNameRole)
        embedding_names = ', '.join(self.data(JobDataRole.EmbeddingNamesRole))
        label_out = label_tpl.format(
            job_name=job_name,
            embedding_names=embedding_names,
            duration_text=self.durationText(),
            frames_length=f"{self.data(JobDataRole.FrameCountRole):,}",
        ).strip()

        # remove empty parentheticals like "()"
        label_out = re.sub(r'\( *\)', '', label_out)

        # remove empty parentheticals tags "[]"
        label_out = re.sub(r'\[ *\]', '', label_out)

        # replace 2 or more spaces with single space
        label_out = re.sub(r' {2,}', ' ', label_out).strip()

        return label_out

    def to_tooltip(self) -> str:
        tooltip = f"Saved job {self.data(JobDataRole.MediaTypeRole)}{self.durationText()}"
        names = self.data(JobDataRole.EmbeddingNamesRole)
        if names:
            name_label = "embed name" if len(names) == 1 else "embed names"
            tooltip += f" with {', '.join(f'`{name}`' for name in names)} {name_label}"
        else:
            tooltip += " with no assigned embeddings"
        return tooltip

    def durationText(self) -> str:
        frame_rate = self.data(JobDataRole.FrameRateRole)
        if self.data(JobDataRole.MediaTypeRole) != "video" or frame_rate <= 0:
            return ""
        hours, remainder = divmod(int(self.data(JobDataRole.FrameCountRole) / frame_rate), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}" or ""
