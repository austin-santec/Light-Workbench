"""Presentation dialog for reading a connected optical switch LAN address."""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class SwitchIpAddressDialog(QDialog):
    """Show one validated address and provide an explicit clipboard action."""

    copied = pyqtSignal()

    def __init__(self, address, model="", serial_number="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Optical Switch IP Address")
        self.setMinimumWidth(430)

        layout = QVBoxLayout(self)
        identity = " ".join(
            part for part in (str(model or "").strip(), str(serial_number or "").strip())
            if part
        )
        layout.addWidget(QLabel("Connected switch: %s" % (identity or "Unknown")))
        layout.addWidget(QLabel("LAN IP address:"))

        self.address_edit = QLineEdit(str(address))
        self.address_edit.setReadOnly(True)
        self.address_edit.selectAll()
        layout.addWidget(self.address_edit)

        buttons = QHBoxLayout()
        self.copy_button = QPushButton("Copy to Clipboard")
        self.copy_button.clicked.connect(self._copy_address)
        buttons.addWidget(self.copy_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def _copy_address(self):
        from PyQt5.QtWidgets import QApplication

        QApplication.clipboard().setText(self.address_edit.text())
        self.copied.emit()


__all__ = ["SwitchIpAddressDialog"]
