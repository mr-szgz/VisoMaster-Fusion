"""Application-owned storage for namespaced preferences."""

from PySide6.QtCore import QObject, QSettings


def settings_group(namespace: str, parent: QObject) -> QSettings:
    settings = QSettings("VisoMaster", "VisoMaster-Fusion", parent)
    settings.setFallbacksEnabled(False)
    settings.beginGroup(namespace)
    return settings
