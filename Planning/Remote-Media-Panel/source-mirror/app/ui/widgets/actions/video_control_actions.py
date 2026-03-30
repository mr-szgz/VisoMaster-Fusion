# Step: Include Import dock in theatre-mode dock visibility snapshot | Pattern: app/ui/widgets/actions/video_control_actions.py:2537-2544

def save_import_media_dock_state(main_window, states):
    # Step: Capture whether dock was visible before theatre mode | Pattern: app/ui/widgets/actions/video_control_actions.py:2538-2543
    states["import_Media_DockWidget"] = main_window.import_Media_DockWidget.isVisible()


# Step: Hide Import dock when entering theatre mode | Pattern: app/ui/widgets/actions/video_control_actions.py:2546-2551

def hide_import_media_dock_for_theatre(main_window):
    # Step: Hide dock to maximize viewport space | Pattern: app/ui/widgets/actions/video_control_actions.py:2546-2551
    main_window.import_Media_DockWidget.hide()


# Step: Restore Import dock visibility when exiting theatre mode | Pattern: app/ui/widgets/actions/video_control_actions.py:2679-2692

def restore_import_media_dock_state(main_window, states):
    # Step: Show dock only if it was visible before theatre mode | Pattern: app/ui/widgets/actions/video_control_actions.py:2681-2692
    if states.get("import_Media_DockWidget"):
        main_window.import_Media_DockWidget.show()
