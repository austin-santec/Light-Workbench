"""Reusable presentation-only collapsible group box for the main window."""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class CollapsibleGroupBox(QGroupBox):
    """A titled group box whose content can be hidden without losing state."""

    expanded_changed = pyqtSignal(bool)

    def __init__(self, title, toggle_text="Collapse", parent=None):
        super().__init__(title, parent)
        self._toggle_text = str(toggle_text)
        self._expanded = True

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(2)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addStretch()
        self.toggle_button = QToolButton()
        self.toggle_button.setObjectName("collapse_toggle")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.setAutoRaise(True)
        self.toggle_button.clicked.connect(self._toggle_from_button)
        header_layout.addWidget(self.toggle_button)
        outer_layout.addLayout(header_layout)

        self.content_widget = QWidget()
        self.content_widget.setObjectName("collapsible_content")
        self.content_widget.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )
        outer_layout.addWidget(self.content_widget)
        self._update_toggle_text()

    @property
    def is_expanded(self):
        """Whether the content widget is currently visible."""
        return self._expanded

    def set_content_layout(self, layout):
        """Install the existing field layout inside the collapsible content."""
        self.content_widget.setLayout(layout)

    def set_expanded(self, expanded):
        """Show or hide the content while preserving all child widget state."""
        expanded = bool(expanded)
        if expanded == self._expanded:
            self._update_toggle_text()
            return
        self._expanded = expanded
        self.content_widget.setVisible(expanded)
        self.toggle_button.setChecked(expanded)
        self._update_toggle_text()
        self.expanded_changed.emit(expanded)

    def _toggle_from_button(self, checked):
        self.set_expanded(checked)

    def _update_toggle_text(self):
        action = self._toggle_text if self._expanded else "Expand"
        self.toggle_button.setArrowType(Qt.UpArrow if self._expanded else Qt.DownArrow)
        self.toggle_button.setText(action)
        self.toggle_button.setToolTip(
            "%s the %s fields" % (action, self.title())
        )
        self.toggle_button.setAccessibleName("%s %s" % (action, self.title()))
