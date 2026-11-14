"""Read-only unit-directory lookup and explicit File Explorer launch."""

from pathlib import Path

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QVBoxLayout,
)

from application.part_number_lookup import UnitFolderLookupController
from config.app_config import DEFAULT_PART_LOOKUP_PARENT
from infrastructure.coc_export import normalise_serial


class UnitFolderLookupDialog(QDialog):
    """Search without blocking Qt; open only a returned directory path."""

    def __init__(
        self, lookup_function, *, connected_serial="", connected_model=None,
        lookup_parent=DEFAULT_PART_LOOKUP_PARENT, parent=None, controller=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Lookup Unit Folder")
        self.resize(620, 230)
        self._connected_serial = normalise_serial(connected_serial)
        self._connected_model = connected_model
        self._lookup_parent = Path(lookup_parent)
        self._active_request = None
        self._closed = False
        self.controller = controller or UnitFolderLookupController(lookup_function, self)
        self.controller.succeeded.connect(self._lookup_succeeded)
        self.controller.failed.connect(self._lookup_failed)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Main board serial:"))
        self.serial_edit = QLineEdit(self._connected_serial)
        self.serial_edit.setPlaceholderText("For example, 18761 or SN18761")
        layout.addWidget(self.serial_edit)
        self.status_label = QLabel("Find the unit folder to view its files in File Explorer.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.matches_list = QListWidget()
        if getattr(parent, "dark_mode_enabled", False):
            self.matches_list.setStyleSheet(
                "QListWidget { background: #373a40; color: #e8eaed; "
                "border: 1px solid #5a6069; selection-background-color: #e60013; }"
            )
        self.matches_list.setVisible(False)
        layout.addWidget(self.matches_list)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.open_button = self.buttons.addButton("Open Folder", QDialogButtonBox.ActionRole)
        self.open_button.setDefault(True)
        self.open_button.clicked.connect(self.open_folder)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.serial_edit.textChanged.connect(self._serial_changed)
        self.serial_edit.returnPressed.connect(self.open_folder)
        self.matches_list.currentRowChanged.connect(self._selection_changed)
        self.serial_edit.selectAll()
        self.serial_edit.setFocus()

    def _serial_changed(self):
        self._active_request = None
        self.matches_list.clear()
        self.matches_list.hide()
        self.status_label.setText("Enter a serial and select Open Folder.")
        self.open_button.setEnabled(True)

    def _selection_changed(self):
        self.open_button.setEnabled(self.matches_list.currentRow() >= 0)

    def open_folder(self) -> None:
        if self._closed or self._active_request is not None:
            return
        item = self.matches_list.currentItem()
        if item is not None:
            self._open_path(item.data(Qt.UserRole))
            return
        # Duplicate matches require an explicit choice, never a fresh auto-open.
        if self.matches_list.count():
            return
        serial = normalise_serial(self.serial_edit.text())
        if not serial:
            self.status_label.setText("Enter a Main Board serial number first.")
            return
        model = (
            self._connected_model
            if serial.casefold() == self._connected_serial.casefold()
            else None
        )
        self.status_label.setText("Searching unit folders...")
        self.open_button.setEnabled(False)
        self._active_request = self.controller.start(
            serial, self._lookup_parent, switch_model=model
        )

    def _lookup_succeeded(self, request_id, serial, folders):
        if not self._is_current(request_id, serial):
            return
        self._active_request = None
        self.matches_list.clear()
        for folder in folders:
            path = Path(folder)
            item = QListWidgetItem("%s / %s" % (path.parent.name, path.name))
            item.setData(Qt.UserRole, path)
            item.setToolTip(str(path))
            self.matches_list.addItem(item)
        self.matches_list.show()
        if len(folders) == 1:
            self.matches_list.setCurrentRow(0)
            self._open_path(Path(folders[0]))
        else:
            self.matches_list.setCurrentRow(-1)
            self.open_button.setEnabled(False)
            self.status_label.setText("Several folders match. Select one, then Open Folder.")

    def _lookup_failed(self, request_id, serial, category, message):
        if not self._is_current(request_id, serial):
            return
        self._active_request = None
        self.open_button.setEnabled(True)
        self.status_label.setText(message)

    def _is_current(self, request_id, serial):
        return (
            not self._closed and request_id == self._active_request
            and normalise_serial(self.serial_edit.text()).casefold() == serial.casefold()
        )

    def _open_path(self, folder):
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self.accept()
        else:
            self.status_label.setText("Could not open this folder in File Explorer:\n%s" % folder)
            self.open_button.setEnabled(True)

    def done(self, result: int) -> None:
        self._closed = True
        self.controller.close()
        super().done(result)

    def closeEvent(self, event) -> None:
        self._closed = True
        self.controller.close()
        super().closeEvent(event)
