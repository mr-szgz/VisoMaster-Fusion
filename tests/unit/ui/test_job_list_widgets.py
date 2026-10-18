"""Run real Qt item checks outside the action tests' global Qt import stubs."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_job_list_widgets_with_real_qt(tmp_path):
    script = textwrap.dedent('''
        import copy
        import json
        from pathlib import Path
        import sys
        from unittest.mock import MagicMock, patch

        from PySide6 import QtCore, QtWidgets
        from app.ui.widgets import job_list_widgets as widgets

        app = QtWidgets.QApplication([])
        root = Path(sys.argv[1])
        path = root / "Saved.job.json"
        job = {
            "selected_media_id": "target",
            "target_medias_data": [
                {"media_id": "other", "media_path": "other.mp4"},
                {"media_id": "target", "media_path": "photo.png"},
            ],
            "target_faces_data": {
                "one": {"assigned_merged_embeddings": ["b", "a"]},
                "two": {"assigned_merged_embeddings": ["a", "b"]},
            },
            "embeddings_data": {
                "a": {"embedding_name": "Alice"},
                "b": {"embedding_name": "Bob"},
                "unused": {"embedding_name": "Unused"},
            },
            "restore_selected_face": False,
            "use_job_name_for_output": False,
            "output_file_name": "saved-output",
            "control": {"ClusterOutputBySourceToggle": True, "OutputMediaFolder": "saved-folder"},
        }
        path.write_text(json.dumps(job), encoding="utf-8")
        queue = widgets.JobQueueListWidget()
        queue.setSortingEnabled(True)
        item = widgets.JobQueueListWidgetItem(QtCore.QFileInfo(str(path)))
        item.setData(widgets.JobDataRole.JobNameRole, "Saved.job")
        item.setData(QtCore.Qt.ItemDataRole.DisplayRole, "Saved.job")
        item.setData(QtCore.Qt.ItemDataRole.ToolTipRole, item.to_tooltip())
        queue.addItem(item)
        assert isinstance(item, widgets.JobQueueListWidgetItem)
        assert item.data(widgets.JobDataRole.JobNameRole) == "Saved.job"
        assert item.data(widgets.JobDataRole.FileInfoRole).filePath() == str(path).replace("\\\\", "/")
        assert item.data(widgets.JobDataRole.TargetMediaIdRole) == "target"
        assert item.data(widgets.JobDataRole.TargetMediaPathRole) == "photo.png"
        assert item.data(widgets.JobDataRole.EmbeddingNamesRole) == ["Bob", "Alice"]
        assert item.data(widgets.JobDataRole.FrameCountRole) == 1
        assert item.toolTip() == "Saved job image with `Bob`, `Alice` embed names"
        assert item.data(widgets.JobDataRole.EmbeddingNamesRole) == ["Bob", "Alice"]
        assert all(int(role) >= int(QtCore.Qt.ItemDataRole.UserRole) for role in widgets.JobDataRole)

        for clustering in (False, True):
            legacy = copy.deepcopy(job)
            del legacy["restore_selected_face"]
            legacy["control"]["ClusterOutputBySourceToggle"] = clustering
            path.write_text(json.dumps(legacy), encoding="utf-8")
            legacy_item = widgets.JobQueueListWidgetItem(QtCore.QFileInfo(str(path)))
            assert legacy_item.data(widgets.JobDataRole.RestoreSelectedFaceRole) is clustering
            assert json.loads(path.read_text()) == legacy
            legacy["restore_selected_face"] = not clustering
            path.write_text(json.dumps(legacy), encoding="utf-8")
            explicit_item = widgets.JobQueueListWidgetItem(QtCore.QFileInfo(str(path)))
            assert explicit_item.data(widgets.JobDataRole.RestoreSelectedFaceRole) is not clustering
        path.write_text(json.dumps(job), encoding="utf-8")

        # Setters and display methods work on the stored data without reading the file again.
        for names, tooltip_suffix in [
            (["Alice"], " with `Alice` embed name"),
            ([], " with no assigned embeddings"),
        ]:
            item.setData(widgets.JobDataRole.EmbeddingNamesRole, names)
            item.setData(QtCore.Qt.ItemDataRole.ToolTipRole, item.to_tooltip())
            assert item.data(widgets.JobDataRole.EmbeddingNamesRole) == names
            assert item.toolTip() == "Saved job image" + tooltip_suffix

        # Video length comes from the selected target, never the first media entry.
        for frames, fps, suffix in [
            (20100, 25, " (00:13:24)"),
            (90025, 25, " (01:00:01)"),
            (1800, 29.97, " (00:01:00)"),
            (0, 25, " (00:00:00)"),
            (2250000, 25, " (25:00:00)"),
            (20100, 0, ""),
        ]:
            video = copy.deepcopy(job)
            video["target_medias_data"][1]["media_path"] = "selected.mp4"
            path.write_text(json.dumps(video), encoding="utf-8")
            capture = MagicMock()
            capture.get.side_effect = [frames, fps]
            with patch.object(widgets.cv2, "VideoCapture", return_value=capture) as factory:
                video_item = widgets.JobQueueListWidgetItem(QtCore.QFileInfo(str(path)))
                video_item.setData(widgets.JobDataRole.JobNameRole, "Saved.job")
                video_item.setData(QtCore.Qt.ItemDataRole.ToolTipRole, video_item.to_tooltip())
                assert video_item.toolTip() == "Saved job video" + suffix + " with `Bob`, `Alice` embed names"
                factory.assert_called_once_with()
            capture.open.assert_called_once_with("selected.mp4")
            capture.setExceptionMode.assert_called_once_with(True)
            capture.release.assert_called_once_with()
            assert video_item.data(widgets.JobDataRole.FrameCountRole) == frames
            assert video_item.data(widgets.JobDataRole.FrameRateRole) == fps

        # Malformed jobs and media errors remain fail-fast.
        for contents, error in [("{", json.JSONDecodeError), ("{}", KeyError)]:
            path.write_text(contents, encoding="utf-8")
            try:
                widgets.JobQueueListWidgetItem(QtCore.QFileInfo(str(path)))
            except error:
                pass
            else:
                raise AssertionError("Invalid job did not fail")
        path.write_text(json.dumps(video), encoding="utf-8")
        capture = MagicMock()
        capture.open.side_effect = OSError("media unavailable")
        with patch.object(widgets.cv2, "VideoCapture", return_value=capture):
            try:
                widgets.JobQueueListWidgetItem(QtCore.QFileInfo(str(path)))
            except OSError:
                pass
            else:
                raise AssertionError("Media failure was suppressed")

        # Selection targets the filename, with Qt ensuring visibility after sorting.
        path.write_text(json.dumps(job), encoding="utf-8")
        for name in ("Z last", "A first"):
            other_path = root / f"{name}.json"
            other_path.write_text(json.dumps(job), encoding="utf-8")
            other_item = widgets.JobQueueListWidgetItem(QtCore.QFileInfo(str(other_path)))
            other_item.setData(widgets.JobDataRole.JobNameRole, name)
            other_item.setData(QtCore.Qt.ItemDataRole.DisplayRole, name)
            queue.addItem(other_item)
        queue.sortItems()
        assert [queue.item(i).data(widgets.JobDataRole.JobNameRole) for i in range(queue.count())] == ["A first", "Saved.job", "Z last"]
        model = queue.model()
        index = model.match(model.index(0, 0), widgets.JobDataRole.JobNameRole, "Saved.job", 1, QtCore.Qt.MatchFlag.MatchExactly)[0]
        queue.setCurrentIndex(index)
        queue.scrollTo(index, QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible)
        assert item.isSelected()
        item.setData(widgets.JobDataRole.JobNameRole, "Independent job name")
        assert item.data(widgets.JobDataRole.FileInfoRole).fileName() == "Saved.job.json"
        assert all(not isinstance(item.data(role), dict) for role in widgets.JobDataRole)

        # Exercise the real dialog without importing the GPU-heavy widget module.
        import ast
        from types import SimpleNamespace
        from PySide6 import QtGui
        source = Path("app/ui/widgets/widget_components.py")
        dialog_node = next(n for n in ast.parse(source.read_text(encoding="utf-8")).body
                           if isinstance(n, ast.ClassDef) and n.name == "SaveJobDialog")
        namespace = dict(QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets,
                         cv2=widgets.cv2, JobDataRole=widgets.JobDataRole,
                         misc_helpers=SimpleNamespace(get_file_type=widgets.get_file_type))
        exec(compile(ast.Module(body=[dialog_node], type_ignores=[]), str(source), "exec"), namespace)
        Dialog = namespace["SaveJobDialog"]
        parent = QtWidgets.QWidget()
        parent.jobQueueList = queue
        parent.control = {"ClusterOutputBySourceToggle": True}
        parent.selected_video_button = SimpleNamespace(media_path="current.png")
        item.setData(widgets.JobDataRole.FrameCountRole, 20100)
        item.setData(widgets.JobDataRole.FrameRateRole, 25.0)
        item.setData(widgets.JobDataRole.EmbeddingNamesRole, ["Bob", "Alice"])
        with patch.object(widgets.cv2, "VideoCapture", side_effect=AssertionError("Edit must use roles")):
            edit_dialog = Dialog(parent, job_item=item)
        assert edit_dialog.job_name == "Independent job name"
        assert edit_dialog.output_file_name == "saved-output"
        assert edit_dialog.use_job_name_for_output is False
        assert edit_dialog.restore_selected_face is False
        assert edit_dialog.media_report_layout.itemAtPosition(0, 0).widget().text() == "Embedding:"
        assert [edit_dialog.media_report_layout.itemAtPosition(r, 1).widget().text()
                for r in range(4)] == ["Bob, Alice", "20,100", "25 fps", "00:13:24"]
        for enabled in (True, False):
            parent.control["ClusterOutputBySourceToggle"] = enabled
            new_dialog = Dialog(parent, "New job")
            assert new_dialog.restore_selected_face is enabled
            assert new_dialog.use_job_name_for_output is True
        assert item.data(widgets.JobDataRole.RestoreSelectedFaceRole) is False

        # Save the real dialog, then edit through the real persistence function.
        source = Path("app/ui/widgets/actions/job_manager_actions.py")
        functions = [n for n in ast.parse(source.read_text(encoding="utf-8")).body
                     if isinstance(n, ast.FunctionDef) and n.name in ("save_job_workspace", "edit_job")]
        from typing import Optional
        namespace.update(
            json=json, Path=Path, Optional=Optional, Qt=QtCore.Qt,
            JobQueueListWidgetItem=widgets.JobQueueListWidgetItem,
            widget_components=SimpleNamespace(SaveJobDialog=Dialog, TargetMediaCardButton=object),
            _serialize_job_data=lambda mw: copy.deepcopy(job), refresh_job_list=MagicMock(),
            common_widget_actions=MagicMock(),
        )
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)
        new_dialog.restore_selected_face_checkbox.setChecked(True)
        new_dialog.set_output_name_checkbox.setChecked(False)
        new_dialog.output_name_edit.setText("new-output")
        namespace["save_job_workspace"](parent, str(root / "Created"), dialog=new_dialog)
        created = json.loads((root / "Created.json").read_text())
        assert created["restore_selected_face"] is True
        assert created["output_file_name"] == "new-output"
        assert created["control"] == job["control"]
        def accept_edit(dialog):
            assert dialog.job_name == "Independent job name"
            dialog.job_name_edit.setText("Renamed")
            dialog.restore_selected_face_checkbox.setChecked(True)
            dialog.output_name_edit.setText("edited-output")
            dialog.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).click()
            return QtWidgets.QDialog.Accepted
        namespace["refresh_job_list"].side_effect = lambda mw: item.setData(
            widgets.JobDataRole.JobNameRole, "Renamed")
        with patch.object(Dialog, "exec", accept_edit):
            namespace["edit_job"](parent, item)
        updated = json.loads((root / "Renamed.json").read_text())
        assert updated == {**job, "restore_selected_face": True, "output_file_name": "edited-output"}
        assert not path.exists()
        namespace["refresh_job_list"].assert_called_once_with(parent)
        assert queue.currentItem() is item

        # The regenerated Designer form actually uses the promoted widget.
        from app.ui.core.main_window import Ui_MainWindow
        window = QtWidgets.QMainWindow()
        ui = Ui_MainWindow()
        ui.setupUi(window)
        assert isinstance(ui.jobQueueList, widgets.JobQueueListWidget)
        assert ui.gridLayout_2.itemAtPosition(1, 1).widget() is ui.targetFacesList
        assert ui.gridLayout_2.itemAtPosition(1, 2).widget() is ui.inputEmbeddingsList
        print("Job roles, display, media, failures, selection, sorting, and promoted UI passed.")
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_main_window_job_save_and_edit(tmp_path):
    script = textwrap.dedent('''
        import json
        import sys
        from pathlib import Path
        from unittest.mock import patch
        import faulthandler
        faulthandler.enable()
        import torch
        import cv2
        import numpy as np
        from PySide6 import QtCore, QtWidgets
        from app.ui.main_ui import MainWindow
        from app.ui.widgets import widget_components
        from app.ui.widgets.actions import job_manager_actions as actions
        from app.ui.widgets.job_list_widgets import JobDataRole

        torch.set_grad_enabled(False)
        from app.ui.core.proxy_style import ProxyStyle
        import qdarktheme
        app = QtWidgets.QApplication([])
        app.setStyle(ProxyStyle())
        app.setStyleSheet(qdarktheme.load_stylesheet(theme="dark", custom_colors={"primary": "#4090a3"})
                         + "\\n" + Path("app/ui/styles/true_dark_styles.qss").read_text())
        root = Path(sys.argv[1])
        jobs = root / "jobs"
        jobs.mkdir()
        media = root / "target.avi"
        writer = cv2.VideoWriter(str(media), cv2.VideoWriter_fourcc(*"MJPG"), 25, (64, 64))
        assert writer.isOpened()
        for _ in range(50):
            writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
        writer.release()

        # Isolate persisted user data; initialize all actual application widgets.
        with patch.object(actions, "get_jobs_dir", return_value=jobs), \
                patch.object(MainWindow, "load_last_workspace", lambda self: None):
            window = MainWindow(gpu_id=0)
            window.show()
            app.processEvents()
            assert window.gridLayout_2.itemAtPosition(1, 2).widget() is window.embeddingTabs.parentWidget()
            card = widget_components.TargetMediaCardButton(
                str(media), "video", "test-media", main_window=window)
            window.target_videos[card.media_id] = card
            window.selected_video_button = card
            window.control["ClusterOutputBySourceToggle"] = True
            dialog = widget_components.SaveJobDialog(window, "Created")
            assert dialog.restore_selected_face is True
            assert [dialog.media_report_layout.itemAtPosition(r, 1).widget().text()
                    for r in range(3)] == ["50", "25 fps", "00:00:02"]
            dialog.restore_selected_face_checkbox.setChecked(False)
            actions.save_job(window, dialog)
            actions.refresh_job_list(window, selected_job_name="Created")
            item = window.jobQueueList.currentItem()
            assert item.isSelected()
            assert item.data(JobDataRole.JobNameRole) == "Created"
            saved = json.loads((jobs / "Created.json").read_text())
            assert saved["restore_selected_face"] is False
            assert saved["control"]["ClusterOutputBySourceToggle"] is True
            assert "00:00:02" in item.text()
            assert "00:00:02" in item.toolTip()
            # An older job can be edited using its saved clustering setting.
            del saved["restore_selected_face"]
            saved["control"]["ClusterOutputBySourceToggle"] = False
            (jobs / "Created.json").write_text(json.dumps(saved))
            actions.refresh_job_list(window, selected_job_name="Created")
            item = window.jobQueueList.currentItem()
            assert json.loads((jobs / "Created.json").read_text()) == saved
            original_exec = widget_components.SaveJobDialog.exec
            def edit_dialog_exec(dialog):
                assert dialog.job_name == "Created"
                assert dialog.restore_selected_face is False
                dialog.job_name_edit.setText("Renamed")
                dialog.set_output_name_checkbox.setChecked(False)
                dialog.output_name_edit.setText("custom-output")
                dialog.restore_selected_face_checkbox.setChecked(True)
                save_button = dialog.buttonBox.button(QtWidgets.QDialogButtonBox.Ok)
                original_refresh = actions.refresh_job_list
                def refresh_while_visible(main_window):
                    assert dialog.isVisible()
                    assert not save_button.isEnabled()
                    assert save_button.text() == "Saving…"
                    assert (jobs / "Renamed.json").is_file()
                    original_refresh(main_window)
                    assert dialog.isVisible()
                QtCore.QTimer.singleShot(0, save_button.click)
                with patch.object(actions, "refresh_job_list", refresh_while_visible):
                    return original_exec(dialog)
            with patch.object(widget_components.SaveJobDialog, "exec", edit_dialog_exec):
                actions.edit_job(window, item)
            updated = json.loads((jobs / "Renamed.json").read_text())
            assert updated == {**saved, "use_job_name_for_output": False,
                               "output_file_name": "custom-output", "restore_selected_face": True}
            assert not (jobs / "Created.json").exists()
            item = window.jobQueueList.currentItem()
            assert item.data(JobDataRole.JobNameRole) == "Renamed"
            assert item.isSelected()
            reopened = widget_components.SaveJobDialog(window, job_item=item)
            assert reopened.output_file_name == "custom-output"
            assert reopened.restore_selected_face is True
            app.processEvents()
            window.quit_without_saving = True
            window.close()
            app.processEvents()
            print("PASS actual MainWindow startup, save, edit, refresh, selection, shutdown")
    ''')
    result = subprocess.run(
        [sys.executable, "-u", "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS actual MainWindow" in result.stdout
    assert "Traceback" not in result.stderr, result.stderr
