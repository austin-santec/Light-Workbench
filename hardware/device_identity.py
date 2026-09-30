"""Helpers for reporting hardware identity without vendor coupling in the UI."""

from domain.models import ConnectionState, DeviceCategory, DeviceInfo


def device_info_for(
    device,
    category: DeviceCategory,
    state: ConnectionState = ConnectionState.DISCONNECTED,
    error: str = "",
) -> DeviceInfo:
    """Return adapter identity, using a safe fallback for older test doubles.

    Existing hardware fakes and compatibility adapters do not need to
    implement the optional identity method immediately.  This fallback keeps
    the lifecycle reporting useful while the hardware boundary is migrated.
    """

    provider = getattr(device, "get_device_info", None)
    if provider is not None:
        return provider(state=state, error=error)

    description = str(getattr(device, "description", "") or "").strip()
    serial = str(
        getattr(device, "usb_serial", None)
        or getattr(device, "serial_number", None)
        or ""
    ).strip()
    manufacturer = "Santec" if description or serial else ""
    fallback_model = description or {
        DeviceCategory.POWER_METER: "OP815",
        DeviceCategory.OPTICAL_SWITCH: "Optical switch",
        DeviceCategory.LASER_SOURCE: "Laser source",
    }.get(category, "Unknown device")
    return DeviceInfo(
        category=category,
        manufacturer=manufacturer,
        model=fallback_model,
        serial_number=serial,
        state=state,
        error=error,
    )


__all__ = ["device_info_for"]
