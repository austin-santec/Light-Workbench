"""Presentation widget for transient connected-hardware identity."""

from PyQt5.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QSizePolicy

from domain.models import ConnectionState, DeviceCategory, DeviceInfo


class HardwareStatusPanel(QGroupBox):
    """Display meter and switch connection state without vendor UI logic."""

    _STATE_COLORS = {
        ConnectionState.CONNECTED: "#22c55e",
        ConnectionState.CONNECTING: "#f59e0b",
        ConnectionState.ERROR: "#ef4444",
        ConnectionState.DISCONNECTED: "#9aa0a6",
    }

    def __init__(self, parent=None):
        super().__init__("Connected hardware", parent)
        self.setObjectName("connected_hardware_status")
        # Keep both device summaries on one compact row because this panel is
        # presented in the main header rather than in the run controls.
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)
        self.power_meter_status = QLabel()
        self.power_meter_status.setObjectName("power_meter_status")
        self.optical_switch_status = QLabel()
        self.optical_switch_status.setObjectName("optical_switch_status")
        for label in (self.power_meter_status, self.optical_switch_status):
            label.setWordWrap(True)
            label.setMinimumWidth(205)
            layout.addWidget(label)
        self.setMinimumWidth(440)
        self.setMaximumWidth(560)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.clear()

    def clear(self):
        """Reset both entries to the initial disconnected state."""
        self.set_device_status(
            DeviceInfo(
                category=DeviceCategory.POWER_METER,
                state=ConnectionState.DISCONNECTED,
            )
        )
        self.set_device_status(
            DeviceInfo(
                category=DeviceCategory.OPTICAL_SWITCH,
                state=ConnectionState.DISCONNECTED,
            )
        )

    def set_device_status(self, info: DeviceInfo):
        """Render one status update from the application controller."""
        label = {
            DeviceCategory.POWER_METER: self.power_meter_status,
            DeviceCategory.OPTICAL_SWITCH: self.optical_switch_status,
        }.get(info.category)
        if label is None:
            return

        state_text = {
            ConnectionState.CONNECTED: "Connected",
            ConnectionState.CONNECTING: "Connecting",
            ConnectionState.ERROR: "Error",
            ConnectionState.DISCONNECTED: "Disconnected",
        }.get(info.state, "Unknown")
        device_name = " ".join(
            part for part in (info.manufacturer.strip(), info.model.strip()) if part
        ) or "Unknown device"
        if info.state == ConnectionState.ERROR and info.error:
            details = info.error
        elif info.serial_number:
            details = "S/N %s" % info.serial_number
        elif info.state == ConnectionState.DISCONNECTED:
            details = "Not connected"
        elif info.state == ConnectionState.CONNECTING:
            details = "Detecting device..."
        else:
            details = "Identity unavailable"
        label.setText("%s: %s — %s (%s)" % (
            self._category_label(info.category),
            state_text,
            device_name,
            details,
        ))
        label.setToolTip(label.text())
        color = self._STATE_COLORS.get(
            info.state,
            self._STATE_COLORS[ConnectionState.DISCONNECTED],
        )
        # An unknown initial device is neutral gray.  A known device that has
        # just disconnected is red so the operator can distinguish an
        # equipment loss from a workstation that has never connected.
        if info.state == ConnectionState.DISCONNECTED and (
            info.model or info.serial_number or info.raw_identity
        ):
            color = self._STATE_COLORS[ConnectionState.ERROR]
        label.setStyleSheet("color: %s;" % color)

    @staticmethod
    def _category_label(category):
        return {
            DeviceCategory.POWER_METER: "ILM / Power meter",
            DeviceCategory.OPTICAL_SWITCH: "Optical switch",
        }.get(category, "Device")


__all__ = ["HardwareStatusPanel"]
