"""Dialog for manually checking switch channels with a visible red-light source."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from application.red_light_controller import RedLightTestController
from hardware.factory import HardwareFactory


class RedLightTestDialog(QDialog):
    """Connect to the switch only after the operator starts the test.

    This is deliberately independent of the IL measurement worker. It only
    changes the selected switch channel and displays which channel was
    selected; no readings or run data are created.
    """

    def __init__(self, parent=None, switch_factory=None):
        super().__init__(parent)
        self.hardware_factory = HardwareFactory()
        self.switch_factory = (
            switch_factory
            if switch_factory is not None
            else self.hardware_factory.create_switch
        )
        self.switch = None
        self.red_controller = RedLightTestController(self)
        self.red_controller.connected.connect(self._switch_connected)
        self.red_controller.channel_selected.connect(self._channel_selected)
        self.red_controller.failed.connect(self._switch_failed)
        self.red_controller.thread_finished.connect(self._controller_finished)
        self.channel_count = 0
        self.started = False
        self._last_routed_channel = None
        self._last_requested_channel = None

        self.setWindowTitle("Red Light Test")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        instructions = QLabel(
            "Connect the VFL and observe the output while selecting channels. "
            "This test does not record IL readings."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        control_box = QGroupBox("Channel selection")
        form = QFormLayout(control_box)
        self.channel_spin = QSpinBox()
        self.channel_spin.setRange(1, 1)
        self.channel_spin.setKeyboardTracking(False)
        self.channel_spin.setEnabled(False)
        self.channel_spin.setToolTip(
            "Type a channel number, or use the Up and Down arrow keys."
        )
        self.channel_spin.valueChanged.connect(self.select_channel)
        self.channel_spin.lineEdit().editingFinished.connect(self.select_channel)
        form.addRow("Channel:", self.channel_spin)

        navigation = QHBoxLayout()
        self.previous_button = QPushButton("Previous")
        self.previous_button.clicked.connect(self.previous_channel)
        self.previous_button.setEnabled(False)
        navigation.addWidget(self.previous_button)
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.next_channel)
        self.next_button.setEnabled(False)
        navigation.addWidget(self.next_button)
        navigation.addStretch()
        form.addRow("Navigate:", navigation)
        layout.addWidget(control_box)

        self.selected_channel_label = QLabel("Selected channel: -")
        self.selected_channel_label.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #164e6b;"
        )
        layout.addWidget(self.selected_channel_label)
        self.status_label = QLabel("Not started. Click Start Red Light Test to connect.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("Start Red Light Test")
        self.start_button.setObjectName("primary_action")
        self.start_button.clicked.connect(self.start_test)
        buttons.addWidget(self.start_button)
        self.stop_button = QPushButton("Stop Test")
        self.stop_button.clicked.connect(self.stop_test)
        self.stop_button.setEnabled(False)
        buttons.addWidget(self.stop_button)
        buttons.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def start_test(self):
        """Connect and route the switch to channel 1."""
        parent = self.parent()
        if parent is not None and getattr(parent, "hardware_thread", None) is not None:
            QMessageBox.warning(
                self,
                "Hardware run active",
                "Stop the current hardware run before starting a Red Light Test.",
            )
            return

        self.start_button.setEnabled(False)
        self.status_label.setText("Connecting to the OSX-150...")
        try:
            self.red_controller.start(self.switch_factory)
            self.switch = self.red_controller.switch
        except Exception as exc:
            self._close_switch()
            self.start_button.setEnabled(True)
            self.status_label.setText("Unable to start the Red Light Test.")
            QMessageBox.critical(self, "Red Light Test", "Could not connect to the switch:\n%s" % exc)

    def _switch_connected(self, channel_count):
        self.channel_count = channel_count
        self.channel_spin.setRange(1, self.channel_count)
        self.channel_spin.setEnabled(True)
        self.previous_button.setEnabled(True)
        self.next_button.setEnabled(True)
        self.started = True
        self._last_routed_channel = None
        self._last_requested_channel = None
        self.channel_spin.setValue(1)
        self.select_channel(1)
        self.stop_button.setEnabled(True)

    def _channel_selected(self, channel, physical_port):
        self._last_routed_channel = channel
        self.selected_channel_label.setText(
            "Selected channel: %d of %d" % (channel, self.channel_count)
        )
        self.status_label.setText(
            "Physical port %s selected. Observe the VFL output, then choose "
            "another channel." % physical_port
        )

    def _switch_failed(self, message):
        if not self.started:
            self.status_label.setText("Unable to start the Red Light Test.")
            self.start_button.setEnabled(True)
            QMessageBox.critical(
                self,
                "Red Light Test",
                "Could not connect to the switch:\n%s" % message,
            )
            return
        self.status_label.setText(message)

    def _controller_finished(self):
        self.switch = None

    def select_channel(self, channel=None):
        """Route the selected channel and report the physical port returned."""
        if not self.started or self.red_controller.worker is None:
            return
        channel = self.channel_spin.value() if channel is None else int(channel)
        if channel == self._last_requested_channel:
            return
        self._last_requested_channel = channel
        self.red_controller.select_channel(channel)

    def previous_channel(self):
        if self.started and self.channel_spin.value() > 1:
            self.channel_spin.setValue(self.channel_spin.value() - 1)

    def next_channel(self):
        if self.started and self.channel_spin.value() < self.channel_count:
            self.channel_spin.setValue(self.channel_spin.value() + 1)

    def stop_test(self):
        if self.red_controller.worker is None:
            return
        self._close_switch()
        self.started = False
        self._last_routed_channel = None
        self.channel_spin.setEnabled(False)
        self.previous_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.start_button.setEnabled(True)
        self.selected_channel_label.setText("Selected channel: -")
        self.status_label.setText("Disconnected. Click Start Red Light Test to reconnect.")

    def _close_switch(self):
        if self.red_controller.worker is not None:
            self.red_controller.stop_and_wait()
        self.switch = None

    def closeEvent(self, event):
        self._close_switch()
        self.started = False
        event.accept()
