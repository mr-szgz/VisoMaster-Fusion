import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6 import QtCore, QtGui, QtWidgets


@pytest.fixture
def thumbnail_track():
    source = Path("app/ui/widgets/actions/video_seek_actions.py")
    track_class = next(
        node for node in ast.parse(source.read_text(encoding="utf-8")).body
        if isinstance(node, ast.ClassDef) and node.name == "ThumbnailTrackWidget"
    )
    namespace = dict(QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets)
    exec(compile(ast.Module(body=[track_class], type_ignores=[]), str(source), "exec"), namespace)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    track = namespace["ThumbnailTrackWidget"]()
    track.main_window = SimpleNamespace(
        control={}, video_processor=SimpleNamespace(media_path="original.mp4")
    )
    yield track
    track.resize_timer.stop()
    track.close()
    app.processEvents()


class _ThumbnailSender(QtCore.QObject):
    thumbnail_ready = QtCore.Signal(int, QtGui.QImage)
    media_path = "original.mp4"


@pytest.mark.parametrize("transition", ["replacement_worker", "changed_media", "cleared_strip"])
def test_queued_thumbnail_is_rejected_after_transition(thumbnail_track, transition):
    track = thumbnail_track
    old_worker = _ThumbnailSender()
    track.worker = old_worker
    track.expected_intervals = [0]
    old_worker.thumbnail_ready.connect(
        track.on_thumbnail_ready, QtCore.Qt.ConnectionType.QueuedConnection
    )
    stale_image = QtGui.QImage(2, 2, QtGui.QImage.Format.Format_RGB32)
    stale_image.fill(QtGui.QColor("blue"))
    old_worker.thumbnail_ready.emit(0, stale_image)

    if transition == "replacement_worker":
        track.worker = _ThumbnailSender()
        track.worker.thumbnail_ready.connect(track.on_thumbnail_ready)
    elif transition == "changed_media":
        track.main_window.video_processor.media_path = "next.mp4"
    else:
        track.expected_intervals.clear()

    QtWidgets.QApplication.processEvents()
    assert track.thumbnail_cache == {}

    track.worker.media_path = track.main_window.video_processor.media_path
    track.expected_intervals = [0]
    current_image = QtGui.QImage(2, 2, QtGui.QImage.Format.Format_RGB32)
    current_image.fill(QtGui.QColor("red"))
    track.worker.thumbnail_ready.emit(0, current_image)
    QtWidgets.QApplication.processEvents()
    assert track.thumbnail_cache[0].toImage().pixelColor(0, 0) == QtGui.QColor("red")
