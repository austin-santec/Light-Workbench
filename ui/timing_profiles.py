"""Administrator dialog for production measurement timing profiles."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from domain.measurement_timing import (
    DEFAULT_LIVE_UPDATE_PAUSE_MS,
    DEFAULT_SOURCE_SETTLING_MS,
    DEFAULT_WAVELENGTH_SETTLING_MS,
    MAX_TIMING_MS,
    MeasurementTimingProfile,
    default_measurement_timing_profiles,
)


class TimingProfilesDialog(QDialog):
    """Create and edit timing profiles after Admin Mode authorization."""

    def __init__(self, profiles, repository, active_profile_id="standard", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Timing Profiles")
        self.setMinimumWidth(500)
        self.repository = repository
        self.profiles = {
            str(profile_id): profile.validate()
            for profile_id, profile in dict(profiles).items()
        }
        self.active_profile_id = str(active_profile_id or "standard").strip().lower()
        if self.active_profile_id not in self.profiles:
            self.active_profile_id = "standard"
        self._loading = False
        self._dirty = False

        layout = QVBoxLayout(self)
        intro = QLabel(
            "These settings affect future normal measurements only. Reference "
            "calculation and source-off safety timing remain unchanged."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.currentIndexChanged.connect(self._load_selected)
        form.addRow("Profile:", self.profile_combo)

        self.profile_id_edit = QLineEdit()
        self.profile_id_edit.setReadOnly(True)
        form.addRow("Profile ID:", self.profile_id_edit)

        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._mark_dirty)
        form.addRow("Name:", self.name_edit)

        self.revision_spin = QSpinBox()
        self.revision_spin.setRange(1, 999999)
        self.revision_spin.valueChanged.connect(self._mark_dirty)
        form.addRow("Revision:", self.revision_spin)

        self.wavelength_spin = self._timing_spin()
        self.wavelength_spin.valueChanged.connect(self._mark_dirty)
        self.wavelength_spin.setToolTip(
            "Delay after SetWavelength before confirming the OPM wavelength."
        )
        form.addRow("OPM wavelength settling:", self.wavelength_spin)

        self.source_spin = self._timing_spin()
        self.source_spin.valueChanged.connect(self._mark_dirty)
        self.source_spin.setToolTip(
            "Delay after enabling the laser source before ReadPower."
        )
        form.addRow("Laser source settling:", self.source_spin)

        self.live_pause_spin = self._timing_spin()
        self.live_pause_spin.valueChanged.connect(self._mark_dirty)
        self.live_pause_spin.setToolTip(
            "Delay between completed automatic live readings."
        )
        form.addRow("Live update pause:", self.live_pause_spin)
        layout.addLayout(form)

        profile_buttons = QHBoxLayout()
        new_button = QPushButton("New")
        new_button.clicked.connect(self._new_profile)
        duplicate_button = QPushButton("Duplicate")
        duplicate_button.clicked.connect(self._duplicate_profile)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self._delete_profile)
        profile_buttons.addWidget(new_button)
        profile_buttons.addWidget(duplicate_button)
        profile_buttons.addWidget(delete_button)
        profile_buttons.addStretch()
        layout.addLayout(profile_buttons)

        save_button = QPushButton("Save Changes")
        save_button.clicked.connect(self._save)
        reload_button = QPushButton("Reload")
        reload_button.clicked.connect(self._reload)
        defaults_button = QPushButton("Restore Defaults")
        defaults_button.clicked.connect(self._restore_defaults)
        action_buttons = QHBoxLayout()
        action_buttons.addWidget(save_button)
        action_buttons.addWidget(reload_button)
        action_buttons.addWidget(defaults_button)
        layout.addLayout(action_buttons)

        dialog_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        dialog_buttons.rejected.connect(self.reject)
        layout.addWidget(dialog_buttons)
        self._refresh_combo()

    @staticmethod
    def _timing_spin():
        spin = QSpinBox()
        spin.setRange(0, MAX_TIMING_MS)
        spin.setSingleStep(10)
        spin.setSuffix(" ms")
        return spin

    def _refresh_combo(self):
        self._loading = True
        self.profile_combo.clear()
        for profile_id, profile in sorted(self.profiles.items()):
            self.profile_combo.addItem(profile.name, profile_id)
        index = self.profile_combo.findData(self.active_profile_id)
        self.profile_combo.setCurrentIndex(max(0, index))
        self._loading = False
        self._load_selected()

    def _selected_id(self):
        return str(self.profile_combo.currentData() or "standard")

    def _load_selected(self, *_args):
        profile = self.profiles.get(self._selected_id())
        if profile is None:
            return
        self._loading = True
        self.profile_id_edit.setText(profile.profile_id)
        self.name_edit.setText(profile.name)
        self.revision_spin.setValue(profile.revision)
        self.wavelength_spin.setValue(profile.wavelength_settling_ms)
        self.source_spin.setValue(profile.source_settling_ms)
        self.live_pause_spin.setValue(profile.live_update_pause_ms)
        self._loading = False

    def _mark_dirty(self, *_args):
        if not self._loading:
            self._dirty = True

    def _profile_from_form(self):
        return MeasurementTimingProfile(
            profile_id=self._selected_id(),
            name=self.name_edit.text(),
            revision=self.revision_spin.value(),
            wavelength_settling_ms=self.wavelength_spin.value(),
            source_settling_ms=self.source_spin.value(),
            live_update_pause_ms=self.live_pause_spin.value(),
        ).validate()

    def _confirm_fast_values(self, profile):
        below_standard = (
            profile.wavelength_settling_ms < DEFAULT_WAVELENGTH_SETTLING_MS
            or profile.source_settling_ms < DEFAULT_SOURCE_SETTLING_MS
            or profile.live_update_pause_ms < DEFAULT_LIVE_UPDATE_PAUSE_MS
        )
        if not below_standard:
            return True
        answer = QMessageBox.warning(
            self,
            "Experimental timing values",
            "One or more timing values are below the validated Standard profile. "
            "Readings may become unstable or inaccurate. Save anyway?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    def _save(self):
        try:
            profile = self._profile_from_form()
            if not self._confirm_fast_values(profile):
                return
            self.profiles[profile.profile_id] = profile
            self.active_profile_id = self._selected_id()
            self.repository.save(self.profiles, self.active_profile_id)
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "Could not save timing profiles", str(error))
            return
        self._dirty = False
        self.accept()

    def _reload(self):
        try:
            self.profiles, self.active_profile_id = self.repository.load()
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "Could not reload timing profiles", str(error))
            return
        self._dirty = False
        self._refresh_combo()

    def _restore_defaults(self):
        self.profiles = default_measurement_timing_profiles()
        self.active_profile_id = "standard"
        self._dirty = True
        self._refresh_combo()

    def _new_profile(self):
        name, accepted = QInputDialog.getText(self, "New Timing Profile", "Profile name:")
        if not accepted or not name.strip():
            return
        profile_id = name.strip().lower().replace(" ", "_")
        if profile_id in self.profiles:
            QMessageBox.warning(self, "Profile already exists", "Choose a different name.")
            return
        self.profiles[profile_id] = MeasurementTimingProfile(
            profile_id=profile_id,
            name=name.strip(),
        ).validate()
        self.active_profile_id = profile_id
        self._dirty = True
        self._refresh_combo()

    def _duplicate_profile(self):
        source = self.profiles.get(self._selected_id())
        if source is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Duplicate Timing Profile", "New profile name:",
            text=source.name + " Copy",
        )
        if not accepted or not name.strip():
            return
        profile_id = name.strip().lower().replace(" ", "_")
        if profile_id in self.profiles:
            QMessageBox.warning(self, "Profile already exists", "Choose a different name.")
            return
        self.profiles[profile_id] = MeasurementTimingProfile(
            profile_id=profile_id,
            name=name.strip(),
            revision=1,
            wavelength_settling_ms=source.wavelength_settling_ms,
            source_settling_ms=source.source_settling_ms,
            live_update_pause_ms=source.live_update_pause_ms,
        ).validate()
        self.active_profile_id = profile_id
        self._dirty = True
        self._refresh_combo()

    def _delete_profile(self):
        profile_id = self._selected_id()
        if profile_id == "standard":
            QMessageBox.information(self, "Profile required", "The Standard profile cannot be deleted.")
            return
        if profile_id not in self.profiles:
            return
        answer = QMessageBox.question(
            self,
            "Delete Timing Profile",
            "Delete the selected timing profile?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        del self.profiles[profile_id]
        self.active_profile_id = "standard"
        self._dirty = True
        self._refresh_combo()

    def closeEvent(self, event):
        if not self._dirty:
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            "Unsaved timing changes",
            "Discard unsaved timing-profile changes?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()


__all__ = ["TimingProfilesDialog"]
