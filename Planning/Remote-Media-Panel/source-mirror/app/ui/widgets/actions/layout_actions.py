# Step: Toggle Import panel dock visibility from top checkbox | Pattern: app/ui/widgets/actions/layout_actions.py:535-540

def show_hide_import_media_panel(main_window, checked):
    # Step: Show dock when checkbox is enabled | Pattern: app/ui/widgets/actions/layout_actions.py:536-537
    if checked:
        main_window.import_Media_DockWidget.show()
    # Step: Hide dock when checkbox is disabled | Pattern: app/ui/widgets/actions/layout_actions.py:538-539
    else:
        main_window.import_Media_DockWidget.hide()
    # Step: Refit preview/image viewport after layout change | Pattern: app/ui/widgets/actions/layout_actions.py:540
    fit_image_to_view_onchange(main_window)


# Step: Capture panel checkbox states for theatre-mode transition | Pattern: app/ui/widgets/actions/layout_actions.py:569-576

def collect_theatre_panel_states(main_window):
    # Step: Return current top-bar panel toggle states | Pattern: app/ui/widgets/actions/layout_actions.py:571-575
    return {
        "TargetMediaCheckBox": main_window.TargetMediaCheckBox.isChecked(),
        "ImportMediaCheckBox": main_window.ImportMediaCheckBox.isChecked(),
        "facesPanelCheckBox": main_window.facesPanelCheckBox.isChecked(),
        "parametersPanelCheckBox": main_window.parametersPanelCheckBox.isChecked(),
        "InputFacesCheckBox": main_window.InputFacesCheckBox.isChecked(),
        "JobsCheckBox": main_window.JobsCheckBox.isChecked(),
    }


# Step: Reapply panel checkbox states when entering/exiting theatre mode | Pattern: app/ui/widgets/actions/layout_actions.py:579-593

def apply_theatre_panel_states(main_window, states):
    # Step: Restore target media panel state | Pattern: app/ui/widgets/actions/layout_actions.py:580-582
    main_window.TargetMediaCheckBox.setChecked(states.get("TargetMediaCheckBox", True))
    # Step: Restore import media panel state | Pattern: app/ui/widgets/actions/layout_actions.py:580-582 (same checkbox pattern)
    main_window.ImportMediaCheckBox.setChecked(states.get("ImportMediaCheckBox", True))
    # Step: Restore faces panel state | Pattern: app/ui/widgets/actions/layout_actions.py:583-585
    main_window.facesPanelCheckBox.setChecked(states.get("facesPanelCheckBox", True))
    # Step: Restore parameters panel state | Pattern: app/ui/widgets/actions/layout_actions.py:586-588
    main_window.parametersPanelCheckBox.setChecked(
        states.get("parametersPanelCheckBox", True)
    )
    # Step: Restore input faces panel state | Pattern: app/ui/widgets/actions/layout_actions.py:589-591
    main_window.InputFacesCheckBox.setChecked(states.get("InputFacesCheckBox", True))
    # Step: Restore jobs panel state | Pattern: app/ui/widgets/actions/layout_actions.py:592
    main_window.JobsCheckBox.setChecked(states.get("JobsCheckBox", True))
