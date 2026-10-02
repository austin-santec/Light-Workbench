"""Persistent, serialized ownership of application hardware connections."""

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Iterable

from PyQt5.QtCore import QObject, pyqtSignal

from domain.hardware_connection import (
    HardwareBusyError,
    HardwareCapability,
    HardwareConnectionSnapshot,
    HardwareNotReadyError,
    disconnected_device_info,
)
from domain.models import ConnectionState, DeviceCategory, DeviceInfo
from hardware.device_identity import device_info_for
from hardware.factory import HardwareFactory
from domain.support_events import SupportEventCategory, SupportLogLevel


class HardwareConnectionManager(QObject):
    """Own real devices and serialize every native call on one worker thread.

    Existing workflow workers receive managed proxies. Their blocking calls are
    forwarded to this manager's single executor, so the DLL and VISA sessions
    are opened and used on the same long-lived thread.
    """

    device_status_changed = pyqtSignal(object)
    snapshot_changed = pyqtSignal(object)
    operation_finished = pyqtSignal(str, object)

    def __init__(self, hardware_factory: HardwareFactory, parent=None, support_logger=None):
        super().__init__(parent)
        self.hardware_factory = hardware_factory
        self.support_logger = support_logger
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="light-workbench-hardware",
        )
        self._executor_thread_id = None
        self._lock = threading.RLock()
        self._devices = {}
        self._owners = {}
        self._owner_labels = {}
        self._infos = {
            capability: disconnected_device_info(capability)
            for capability in HardwareCapability
        }
        self._shutdown = False

    @property
    def has_separate_laser(self) -> bool:
        return self.hardware_factory.laser_source_factory is not None

    def required_measurement_capabilities(self) -> tuple[HardwareCapability, ...]:
        capabilities = [HardwareCapability.MEASUREMENT]
        if self.has_separate_laser:
            capabilities.append(HardwareCapability.LASER_SOURCE)
        return tuple(capabilities)

    def required_run_capabilities(self) -> tuple[HardwareCapability, ...]:
        return self.required_measurement_capabilities() + (
            HardwareCapability.OPTICAL_SWITCH,
        )

    def snapshot(self, capability: HardwareCapability) -> HardwareConnectionSnapshot:
        with self._lock:
            return HardwareConnectionSnapshot(
                capability=capability,
                device_info=self._infos[capability],
                owner=self._owner_labels.get(capability, ""),
            )

    @property
    def measurement_ready(self) -> bool:
        return all(
            self.snapshot(capability).available
            for capability in self.required_measurement_capabilities()
        )

    @property
    def switch_ready(self) -> bool:
        return self.snapshot(HardwareCapability.OPTICAL_SWITCH).available

    @property
    def run_ready(self) -> bool:
        return all(
            self.snapshot(capability).available
            for capability in self.required_run_capabilities()
        )

    def connect_all(self) -> Future:
        return self._connect_capabilities(
            "Connect all hardware",
            self.required_run_capabilities(),
        )

    def connect_measurement_hardware(self) -> Future:
        return self._connect_capabilities(
            "Connect measurement hardware",
            self.required_measurement_capabilities(),
        )

    def connect_switch(self) -> Future:
        return self._connect_capabilities(
            "Connect optical switch",
            (HardwareCapability.OPTICAL_SWITCH,),
        )

    def disconnect_all(self) -> Future:
        return self._disconnect_capabilities(
            "Disconnect all hardware",
            reversed(self.required_run_capabilities()),
        )

    def disconnect_measurement_hardware(self) -> Future:
        return self._disconnect_capabilities(
            "Disconnect measurement hardware",
            reversed(self.required_measurement_capabilities()),
        )

    def disconnect_switch(self) -> Future:
        return self._disconnect_capabilities(
            "Disconnect optical switch",
            (HardwareCapability.OPTICAL_SWITCH,),
        )

    def _connect_capabilities(
        self,
        operation_name: str,
        capabilities: Iterable[HardwareCapability],
    ) -> Future:
        selected = tuple(capabilities)
        return self._submit(self._connect_many, operation_name, selected)

    def _disconnect_capabilities(
        self,
        operation_name: str,
        capabilities: Iterable[HardwareCapability],
    ) -> Future:
        selected = tuple(capabilities)
        return self._submit(self._disconnect_many, operation_name, selected)

    def _submit(self, function, *args) -> Future:
        with self._lock:
            if self._shutdown:
                future = Future()
                future.set_exception(RuntimeError("Hardware manager is shut down."))
                return future
        return self._executor.submit(self._run_on_owner, function, *args)

    def _run_on_owner(self, function, *args):
        self._executor_thread_id = threading.get_ident()
        return function(*args)

    def _connect_many(self, operation_name, capabilities):
        self._record(
            SupportEventCategory.CONNECTION,
            "connection.requested",
            operation=operation_name,
            details=", ".join(item.value for item in capabilities),
        )
        results = {}
        for capability in capabilities:
            try:
                self._ensure_connected(capability)
                results[capability] = ""
            except Exception as error:
                results[capability] = str(error)
        self.operation_finished.emit(operation_name, results)
        self._record(
            SupportEventCategory.CONNECTION,
            "connection.operation_completed",
            level=(SupportLogLevel.WARNING if any(results.values()) else SupportLogLevel.INFO),
            operation=operation_name,
            status="partial" if any(results.values()) else "success",
            partial_success=bool(any(results.values()) and not all(results.values())),
            details="; ".join(
                "%s: %s" % (capability.value, message or "connected")
                for capability, message in results.items()
            ),
        )
        return results

    def _disconnect_many(self, operation_name, capabilities):
        self._record(
            SupportEventCategory.CONNECTION,
            "connection.disconnect_requested",
            operation=operation_name,
        )
        results = {}
        for capability in capabilities:
            try:
                self._disconnect(capability)
                results[capability] = ""
            except Exception as error:
                results[capability] = str(error)
        self.operation_finished.emit(operation_name, results)
        self._record(
            SupportEventCategory.CONNECTION,
            "connection.disconnect_completed",
            level=(SupportLogLevel.WARNING if any(results.values()) else SupportLogLevel.INFO),
            operation=operation_name,
            status="partial" if any(results.values()) else "success",
            details="; ".join(
                "%s: %s" % (capability.value, message or "disconnected")
                for capability, message in results.items()
            ),
        )
        return results

    def _device_factory(self, capability: HardwareCapability):
        if capability == HardwareCapability.MEASUREMENT:
            return self.hardware_factory.create_power_meter()
        if capability == HardwareCapability.LASER_SOURCE:
            return self.hardware_factory.create_laser_source()
        return self.hardware_factory.create_switch()

    def _ensure_connected(self, capability: HardwareCapability):
        with self._lock:
            if capability in self._devices:
                return self._devices[capability]
            self._set_info_locked(
                capability,
                self._infos[capability].with_state(ConnectionState.CONNECTING),
            )

        device = self._device_factory(capability)
        self._attach_hardware_trace(device)
        try:
            device.connect()
            if capability == HardwareCapability.LASER_SOURCE:
                device.set_output(False)
            info = device_info_for(
                device,
                self._category_for(capability),
                state=ConnectionState.CONNECTED,
            )
        except Exception as error:
            try:
                device.close()
            except Exception:
                pass
            info = device_info_for(
                device,
                self._category_for(capability),
                state=ConnectionState.ERROR,
                error=str(error),
            )
            with self._lock:
                self._devices.pop(capability, None)
                self._set_info_locked(capability, info)
            self._record(
                SupportEventCategory.CONNECTION,
                "connection.failed",
                level=SupportLogLevel.ERROR,
                capability=capability.value,
                error_type=type(error).__name__,
                error_message=str(error),
                status="error",
            )
            raise

        with self._lock:
            self._devices[capability] = device
            self._set_info_locked(capability, info)
        self._record_device("connection.connected", capability, info)
        return device

    def _disconnect(self, capability: HardwareCapability) -> None:
        with self._lock:
            owner = self._owner_labels.get(capability)
            if owner:
                raise HardwareBusyError(
                    "%s is currently being used by %s. Stop or close that "
                    "workflow before disconnecting."
                    % (self._capability_label(capability), owner)
                )
            device = self._devices.get(capability)
            previous = self._infos[capability]
        if device is None:
            return

        try:
            if capability == HardwareCapability.LASER_SOURCE:
                device.set_output(False)
            device.close()
        except Exception as error:
            with self._lock:
                self._devices.pop(capability, None)
                self._set_info_locked(
                    capability,
                    previous.with_state(ConnectionState.ERROR, str(error)),
                )
            raise
        with self._lock:
            self._devices.pop(capability, None)
            self._set_info_locked(
                capability,
                previous.with_state(ConnectionState.DISCONNECTED),
            )
        self._record(
            SupportEventCategory.CONNECTION,
            "connection.disconnected",
            capability=capability.value,
            status="success",
        )

    def acquire(
        self,
        capability: HardwareCapability,
        owner_token: object,
        owner_label: str,
        *,
        connect_if_needed: bool,
    ) -> None:
        self._call_owner(
            self._acquire,
            capability,
            owner_token,
            owner_label,
            connect_if_needed,
        )

    def _acquire(
        self,
        capability,
        owner_token,
        owner_label,
        connect_if_needed,
    ):
        if connect_if_needed:
            self._ensure_connected(capability)
        with self._lock:
            if capability not in self._devices:
                raise HardwareNotReadyError(
                    "%s is not connected. Use Connect Hardware before continuing."
                    % self._capability_label(capability)
                )
            current_owner = self._owners.get(capability)
            if current_owner is not None and current_owner is not owner_token:
                self._record(
                    SupportEventCategory.CONNECTION,
                    "connection.lease_rejected",
                    level=SupportLogLevel.WARNING,
                    capability=capability.value,
                    lease_owner=self._owner_labels.get(capability, "another workflow"),
                    status="busy",
                )
                raise HardwareBusyError(
                    "%s is currently being used by %s. Stop or close that "
                    "workflow before continuing."
                    % (
                        self._capability_label(capability),
                        self._owner_labels.get(capability, "another workflow"),
                    )
                )
            self._owners[capability] = owner_token
            self._owner_labels[capability] = owner_label
            self._set_info_locked(
                capability,
                self._infos[capability].with_state(ConnectionState.IN_USE),
            )
        self._record(
            SupportEventCategory.CONNECTION,
            "connection.lease_acquired",
            capability=capability.value,
            lease_owner=owner_label,
            connection_state=ConnectionState.IN_USE.value,
        )

    def release(self, capability: HardwareCapability, owner_token: object) -> None:
        self._call_owner(self._release, capability, owner_token)

    def _release(self, capability, owner_token):
        with self._lock:
            if self._owners.get(capability) is not owner_token:
                return
            self._owners.pop(capability, None)
            self._owner_labels.pop(capability, None)
            state = (
                ConnectionState.CONNECTED
                if capability in self._devices
                else ConnectionState.DISCONNECTED
            )
            self._set_info_locked(capability, self._infos[capability].with_state(state))
        self._record(
            SupportEventCategory.CONNECTION,
            "connection.lease_released",
            capability=capability.value,
            connection_state=state.value,
        )

    def invoke(
        self,
        capability: HardwareCapability,
        owner_token: object,
        method_name: str,
        *args,
        **kwargs,
    ):
        return self._call_owner(
            self._invoke,
            capability,
            owner_token,
            method_name,
            args,
            kwargs,
        )

    def invoke_optional(
        self,
        capability: HardwareCapability,
        owner_token: object,
        method_name: str,
        *args,
        **kwargs,
    ):
        return self._call_owner(
            self._invoke_optional,
            capability,
            owner_token,
            method_name,
            args,
            kwargs,
        )

    def _invoke_optional(self, capability, owner_token, method_name, args, kwargs):
        with self._lock:
            if self._owners.get(capability) is not owner_token:
                raise HardwareBusyError(
                    "%s is not leased to this workflow."
                    % self._capability_label(capability)
                )
            device = self._devices.get(capability)
        if device is None:
            raise HardwareNotReadyError(
                "%s is no longer connected." % self._capability_label(capability)
            )
        method = getattr(device, method_name, None)
        if method is None:
            return None
        try:
            return method(*args, **kwargs)
        except Exception as error:
            self._mark_failed(capability, device, error)
            raise

    def _invoke(self, capability, owner_token, method_name, args, kwargs):
        with self._lock:
            if self._owners.get(capability) is not owner_token:
                raise HardwareBusyError(
                    "%s is not leased to this workflow."
                    % self._capability_label(capability)
                )
            device = self._devices.get(capability)
        if device is None:
            raise HardwareNotReadyError(
                "%s is no longer connected." % self._capability_label(capability)
            )
        try:
            method = getattr(device, method_name)
            return method(*args, **kwargs)
        except Exception as error:
            self._mark_failed(capability, device, error)
            raise

    def _mark_failed(self, capability, device, error):
        try:
            if capability == HardwareCapability.LASER_SOURCE:
                device.set_output(False)
            device.close()
        except Exception:
            pass
        info = device_info_for(
            device,
            self._category_for(capability),
            state=ConnectionState.ERROR,
            error=str(error),
        )
        with self._lock:
            self._devices.pop(capability, None)
            self._owners.pop(capability, None)
            self._owner_labels.pop(capability, None)
            self._set_info_locked(capability, info)
        self._record_device(
            "connection.communication_failed",
            capability,
            info,
            level=SupportLogLevel.ERROR,
        )

    def _call_owner(self, function, *args):
        if threading.get_ident() == self._executor_thread_id:
            return function(*args)
        return self._submit(function, *args).result()

    def create_power_meter_proxy(
        self,
        owner_token: object,
        owner_label: str,
        *,
        connect_if_needed: bool,
    ):
        return ManagedPowerMeter(
            self,
            owner_token,
            owner_label,
            connect_if_needed=connect_if_needed,
        )

    def create_switch_proxy(
        self,
        owner_token: object,
        owner_label: str,
        *,
        connect_if_needed: bool,
    ):
        return ManagedOpticalSwitch(
            self,
            owner_token,
            owner_label,
            connect_if_needed=connect_if_needed,
        )

    def create_laser_source_proxy(
        self,
        owner_token: object,
        owner_label: str,
        *,
        connect_if_needed: bool,
    ):
        return ManagedLaserSource(
            self,
            owner_token,
            owner_label,
            connect_if_needed=connect_if_needed,
        )

    def close_all(self, timeout: float = 5.0) -> None:
        """Synchronously release all unleased hardware during app shutdown."""
        with self._lock:
            if self._shutdown:
                return
            busy = sorted(set(self._owner_labels.values()))
        if busy:
            raise HardwareBusyError(
                "Hardware is still being used by %s." % ", ".join(busy)
            )
        future = self.disconnect_all()
        results = future.result(timeout=timeout)
        errors = [message for message in results.values() if message]
        if errors:
            raise RuntimeError("; ".join(errors))
        with self._lock:
            self._shutdown = True
        self._executor.shutdown(wait=True)
        self._record(
            SupportEventCategory.CONNECTION,
            "connection.application_cleanup_completed",
            status="success",
        )

    def _attach_hardware_trace(self, device):
        if self.support_logger is None:
            return
        callback = self.support_logger.trace_fanout
        setter = getattr(device, "add_trace_callback", None)
        if setter is not None:
            try:
                setter(callback)
            except Exception:
                pass

    def _record(self, category, event, *, level=SupportLogLevel.INFO, **fields):
        if self.support_logger is None:
            return
        try:
            self.support_logger.record(category, event, level=level, **fields)
        except Exception:
            pass

    def _record_device(self, event, capability, info, *, level=SupportLogLevel.INFO):
        self._record(
            SupportEventCategory.CONNECTION,
            event,
            level=level,
            capability=capability.value,
            device_category=info.category.value,
            manufacturer=info.manufacturer,
            model=info.model,
            device_serial=info.serial_number,
            firmware=info.firmware_version,
            resource_address=info.resource_address,
            configured_channel_count=info.configured_channel_count,
            discovery_method=info.discovery_method,
            connection_state=info.state.value,
            error_message=info.error,
        )

    def _set_info_locked(self, capability, info):
        self._infos[capability] = info
        snapshot = HardwareConnectionSnapshot(
            capability=capability,
            device_info=info,
            owner=self._owner_labels.get(capability, ""),
        )
        self.device_status_changed.emit(info)
        self.snapshot_changed.emit(snapshot)

    @staticmethod
    def _category_for(capability):
        return {
            HardwareCapability.MEASUREMENT: DeviceCategory.POWER_METER,
            HardwareCapability.LASER_SOURCE: DeviceCategory.LASER_SOURCE,
            HardwareCapability.OPTICAL_SWITCH: DeviceCategory.OPTICAL_SWITCH,
        }[capability]

    @staticmethod
    def _capability_label(capability):
        return {
            HardwareCapability.MEASUREMENT: "Measurement hardware",
            HardwareCapability.LASER_SOURCE: "Laser source",
            HardwareCapability.OPTICAL_SWITCH: "Optical switch",
        }[capability]


class _ManagedDevice:
    capability: HardwareCapability
    persistent_connection = True

    def __init__(
        self,
        manager: HardwareConnectionManager,
        owner_token: object,
        owner_label: str,
        *,
        connect_if_needed: bool,
    ):
        self.manager = manager
        self.owner_token = owner_token
        self.owner_label = owner_label
        self.connect_if_needed = connect_if_needed
        self._acquired = False

    def connect(self) -> None:
        if self._acquired:
            return
        self.manager.acquire(
            self.capability,
            self.owner_token,
            self.owner_label,
            connect_if_needed=self.connect_if_needed,
        )
        self._acquired = True

    def close(self) -> None:
        if not self._acquired:
            return
        self.manager.release(self.capability, self.owner_token)
        self._acquired = False

    def get_device_info(self, state=ConnectionState.CONNECTED, error=""):
        info = self.manager.snapshot(self.capability).device_info
        # The manager is authoritative for persistent state. Workflow workers
        # may report their temporary session as disconnected after releasing a
        # lease, but the underlying device intentionally remains connected.
        if error and info.state == ConnectionState.ERROR:
            return info.with_state(ConnectionState.ERROR, error)
        return info

    def _invoke(self, method_name, *args, **kwargs):
        if not self._acquired:
            raise HardwareNotReadyError(
                "%s has not acquired its managed hardware." % self.owner_label
            )
        return self.manager.invoke(
            self.capability,
            self.owner_token,
            method_name,
            *args,
            **kwargs,
        )


class ManagedPowerMeter(_ManagedDevice):
    """PowerMeter proxy that never exposes the manager's native device."""

    capability = HardwareCapability.MEASUREMENT

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._deferred_calls = []

    @property
    def description(self):
        info = self.manager.snapshot(self.capability).device_info
        return " ".join(part for part in (info.manufacturer, info.model) if part)

    @property
    def usb_serial(self):
        return self.manager.snapshot(self.capability).device_info.serial_number

    def connect(self) -> None:
        super().connect()
        deferred, self._deferred_calls = self._deferred_calls, []
        for method_name, args, kwargs in deferred:
            self._invoke_optional(method_name, *args, **kwargs)

    def find_devices(self):
        return [self.description] if self.manager.snapshot(self.capability).connected else []

    def measure_both_wavelengths(self):
        return self._invoke("measure_both_wavelengths")

    def measure_reference_wavelengths(self):
        return self._invoke("measure_reference_wavelengths")

    def _configure_optional(self, method_name, *args, **kwargs):
        if not self._acquired:
            self._deferred_calls.append((method_name, args, kwargs))
            return
        self._invoke_optional(method_name, *args, **kwargs)

    def _invoke_optional(self, method_name, *args, **kwargs):
        return self.manager.invoke_optional(
            self.capability,
            self.owner_token,
            method_name,
            *args,
            **kwargs,
        )

    def set_trace_callback(self, callback):
        self._configure_optional("set_trace_callback", callback)

    def add_trace_callback(self, callback):
        self._configure_optional("add_trace_callback", callback)

    def remove_trace_callback(self, callback):
        self._configure_optional("remove_trace_callback", callback)

    def set_trace_context(self, **context):
        self._configure_optional("set_trace_context", **context)

    def set_trace_metadata(self, **metadata):
        self._configure_optional("set_trace_metadata", **metadata)

    def set_diagnostic_verification(self, enabled):
        self._configure_optional("set_diagnostic_verification", enabled)


class ManagedOpticalSwitch(_ManagedDevice):
    """OpticalSwitch proxy backed by the persistent connection manager."""

    capability = HardwareCapability.OPTICAL_SWITCH

    def configured_channel_count(self):
        return self._invoke("configured_channel_count")

    def set_channel(self, channel):
        return self._invoke("set_channel", channel)

    def set_trace_metadata(self, **metadata):
        if not self._acquired:
            # Switch proxies normally receive metadata before acquiring their
            # persistent lease. Apply it immediately after connect.
            self._trace_metadata = dict(metadata)
            return
        self.manager.invoke_optional(
            self.capability,
            self.owner_token,
            "set_trace_metadata",
            **metadata,
        )

    def connect(self):
        super().connect()
        metadata = getattr(self, "_trace_metadata", None)
        if metadata:
            self.manager.invoke_optional(
                self.capability,
                self.owner_token,
                "set_trace_metadata",
                **metadata,
            )


class ManagedLaserSource(_ManagedDevice):
    """LaserSource proxy for future separate-source configurations."""

    capability = HardwareCapability.LASER_SOURCE

    @property
    def description(self):
        info = self.manager.snapshot(self.capability).device_info
        return " ".join(part for part in (info.manufacturer, info.model) if part)

    @property
    def serial_number(self):
        return self.manager.snapshot(self.capability).device_info.serial_number

    def set_wavelength(self, wavelength_nm):
        return self._invoke("set_wavelength", wavelength_nm)

    def set_output(self, enabled):
        return self._invoke("set_output", enabled)


__all__ = [
    "HardwareConnectionManager",
    "ManagedOpticalSwitch",
    "ManagedLaserSource",
    "ManagedPowerMeter",
]
