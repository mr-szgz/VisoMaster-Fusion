# Step: Restore Import panel visibility from workspace state | Pattern: app/ui/widgets/actions/save_load_actions.py:540-547

def restore_import_media_window_state(main_window, window_state):
    # Step: Apply saved checkbox state on load | Pattern: app/ui/widgets/actions/save_load_actions.py:540-542
    main_window.ImportMediaCheckBox.setChecked(
        window_state.get("ImportMediaCheckBox", True)
    )


# Step: Persist Import panel visibility into workspace state | Pattern: app/ui/widgets/actions/save_load_actions.py:600-617

def save_import_media_window_state(main_window, window_state_data):
    # Step: Save checkbox state for workspace restore | Pattern: app/ui/widgets/actions/save_load_actions.py:607-610
    window_state_data["ImportMediaCheckBox"] = main_window.ImportMediaCheckBox.isChecked()


# Step: Persist Import settings controls in main control map | Pattern: app/ui/widgets/actions/save_load_actions.py:620-625 and control usage throughout file

def save_import_media_controls(main_window):
    # Step: Save selected provider id | Pattern: app/ui/widgets/actions/save_load_actions.py:620-625 (control map persistence)
    main_window.control["RemoteImportProvider"] = (
        main_window.remoteImportProviderComboBox.currentData()
    )
    # Step: Save provider endpoint/location | Pattern: app/ui/widgets/actions/save_load_actions.py:620-625 (control map persistence)
    main_window.control["RemoteImportEndpoint"] = (
        main_window.remoteImportEndpointLineEdit.text().strip()
    )
    # Step: Save video query/config text | Pattern: app/ui/widgets/actions/save_load_actions.py:620-625 (control map persistence)
    main_window.control["RemoteImportVideoQuery"] = (
        main_window.remoteImportVideoQueryPlainText.toPlainText()
    )
    # Step: Save image query/config text | Pattern: app/ui/widgets/actions/save_load_actions.py:620-625 (control map persistence)
    main_window.control["RemoteImportImageQuery"] = (
        main_window.remoteImportImageQueryPlainText.toPlainText()
    )
    # Step: Save saved-search query/config text | Pattern: app/ui/widgets/actions/save_load_actions.py:620-625 (control map persistence)
    main_window.control["RemoteImportSavedSearchesQuery"] = (
        main_window.remoteImportSavedSearchesQueryPlainText.toPlainText()
    )
