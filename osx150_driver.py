"""Compatibility facade for the OSX-150 hardware adapter."""

from hardware.optical_switch import (
    MIN_SWITCH_CHANNEL,
    OSX150,
    SantecOpticalSwitch,
    SANTEC_USB_PRODUCT_ID,
    SANTEC_USB_RESOURCE_QUERY,
    SANTEC_USB_VENDOR_ID,
    SWITCH_SETTLING_TIME_SECONDS,
    SwitchConnectionDiagnostics,
    SwitchConnectionError,
    SwitchConnectionStage,
    SwitchDiscoveryMethod,
    SwitchModelDetection,
    resolve_santec_switch_profile,
)

__all__ = [
    "MIN_SWITCH_CHANNEL",
    "OSX150",
    "SantecOpticalSwitch",
    "SANTEC_USB_PRODUCT_ID",
    "SANTEC_USB_RESOURCE_QUERY",
    "SANTEC_USB_VENDOR_ID",
    "SWITCH_SETTLING_TIME_SECONDS",
    "SwitchConnectionDiagnostics",
    "SwitchConnectionError",
    "SwitchConnectionStage",
    "SwitchDiscoveryMethod",
    "SwitchModelDetection",
    "resolve_santec_switch_profile",
]
