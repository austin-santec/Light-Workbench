"""Qt dialogs for session authorization and limit-profile administration."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from domain.limit_profiles import LimitProfile, default_limit_profiles, profile_key
from domain.extra_ports import (
    ExtraPortSettings,
    MAXIMUM_MAXIMUM_PHYSICAL_PORT_PROBE,
    MINIMUM_MAXIMUM_PHYSICAL_PORT_PROBE,
)


class AdminPasswordDialog(QDialog):
    """Ask for the session-only administrator password."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Admin Mode")
        layout = QFormLayout(self)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setObjectName("admin_password_edit")
        layout.addRow("Password:", self.password_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    @property
    def password(self):
        return self.password_edit.text()


class AdminConfigDialog(QDialog):
    """Edit both model profiles while keeping persistence outside the dialog."""

    def __init__(
        self,
        profiles,
        repository,
        parent=None,
        *,
        extra_port_settings=None,
        extra_port_repository=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Admin Config")
        self.setMinimumWidth(430)
        self.repository = repository
        self.profiles = dict(profiles)
        self.extra_port_repository = extra_port_repository
        self.extra_port_settings = extra_port_settings or ExtraPortSettings()
        self._dirty = False
        self._loading = False
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.model_combo = QComboBox()
        self.model_combo.addItems(["OSX-100", "OSX-150"])
        self.model_combo.currentTextChanged.connect(self._load_current_profile)
        form.addRow("Switch model:", self.model_combo)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("SM (1310/1550)", "SM")
        self.mode_combo.addItem("MM (850/1300)", "MM")
        self.mode_combo.currentIndexChanged.connect(self._load_current_profile)
        form.addRow("Wavelength mode:", self.mode_combo)
        self.profile_name_edit = QLineEdit()
        self.profile_name_edit.textChanged.connect(self._mark_dirty)
        form.addRow("Profile name:", self.profile_name_edit)
        self.revision_edit = QLineEdit()
        self.revision_edit.textChanged.connect(self._mark_dirty)
        form.addRow("Revision:", self.revision_edit)
        self.too_good_spin = self._spin()
        self.too_good_spin.valueChanged.connect(self._mark_dirty)
        form.addRow("Too-good below:", self.too_good_spin)
        self.warning_spin = self._spin()
        self.warning_spin.valueChanged.connect(self._mark_dirty)
        form.addRow("Optimization warning above:", self.warning_spin)
        self.fail_spin = self._spin()
        self.fail_spin.valueChanged.connect(self._mark_dirty)
        form.addRow("Fail above:", self.fail_spin)
        self.minimum_improvement_spin = self._minimum_improvement_spin()
        self.minimum_improvement_spin.valueChanged.connect(self._mark_dirty)
        self.minimum_improvement_spin.setToolTip(
            "A spare must improve the target channel's worse wavelength by at least this amount."
        )
        form.addRow("Minimum replacement improvement:", self.minimum_improvement_spin)
        self.warning_note = QLabel("Not applicable for OSX-100")
        self.warning_note.setWordWrap(True)
        form.addRow("", self.warning_note)
        self.maximum_physical_port_probe_spin = QSpinBox()
        self.maximum_physical_port_probe_spin.setRange(
            MINIMUM_MAXIMUM_PHYSICAL_PORT_PROBE,
            MAXIMUM_MAXIMUM_PHYSICAL_PORT_PROBE,
        )
        self.maximum_physical_port_probe_spin.setValue(
            self.extra_port_settings.maximum_physical_port_probe
        )
        self.maximum_physical_port_probe_spin.setToolTip(
            "Safety ceiling only; it does not assert that every port exists."
        )
        self.maximum_physical_port_probe_spin.valueChanged.connect(self._mark_dirty)
        form.addRow(
            "Maximum physical-port probe:",
            self.maximum_physical_port_probe_spin,
        )
        layout.addLayout(form)
        buttons = QHBoxLayout()
        save = QPushButton("Save Changes")
        save.clicked.connect(self._save_selected)
        reload_button = QPushButton("Reload")
        reload_button.clicked.connect(self._reload)
        defaults = QPushButton("Restore Defaults")
        defaults.clicked.connect(self._restore_defaults)
        buttons.addWidget(save)
        buttons.addWidget(reload_button)
        buttons.addWidget(defaults)
        layout.addLayout(buttons)
        dialog_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        dialog_buttons.rejected.connect(self.reject)
        dialog_buttons.accepted.connect(self.accept)
        layout.addWidget(dialog_buttons)
        self._load_current_profile()

    @staticmethod
    def _spin():
        spin = QDoubleSpinBox()
        spin.setRange(-100, 100)
        spin.setDecimals(4)
        spin.setSingleStep(0.05)
        spin.setSuffix(" dB")
        return spin

    @staticmethod
    def _minimum_improvement_spin():
        spin = QDoubleSpinBox()
        spin.setRange(0, 100)
        spin.setDecimals(4)
        spin.setSingleStep(0.05)
        spin.setSuffix(" dB")
        return spin

    def _selected_key(self):
        return profile_key(self.model_combo.currentText(), self.mode_combo.currentData())

    def _load_current_profile(self, *_args):
        self._loading = True
        profile = self.profiles[self._selected_key()]
        self.profile_name_edit.setText(profile.profile_name)
        self.revision_edit.setText(profile.revision)
        self.too_good_spin.setValue(profile.too_good_below_db)
        self.warning_spin.setValue(profile.warning_above_db or 0.0)
        self.fail_spin.setValue(profile.fail_above_db)
        self.minimum_improvement_spin.setValue(
            profile.minimum_replacement_improvement_db
        )
        is_150 = self.model_combo.currentText() == "OSX-150"
        self.warning_spin.setEnabled(is_150)
        self.warning_note.setVisible(not is_150)
        self._loading = False

    def _mark_dirty(self, *_args):
        if not self._loading:
            self._dirty = True

    def closeEvent(self, event):
        if not self._dirty:
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            "Unsaved admin changes",
            "Discard unsaved administrator changes?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()

    def _profile_from_form(self):
        model = self.model_combo.currentText()
        mode = self.mode_combo.currentData()
        return LimitProfile(
            model=model,
            profile_name=self.profile_name_edit.text().strip(),
            revision=self.revision_edit.text().strip(),
            too_good_below_db=self.too_good_spin.value(),
            warning_enabled=model == "OSX-150",
            warning_above_db=(
                self.warning_spin.value() if model == "OSX-150" else None
            ),
            fail_above_db=self.fail_spin.value(),
            wavelength_mode=mode,
            minimum_replacement_improvement_db=(
                self.minimum_improvement_spin.value()
            ),
        ).validate()

    def _save_selected(self):
        try:
            self.profiles[self._selected_key()] = self._profile_from_form()
            self.repository.save_profiles(self.profiles)
            self.extra_port_settings = ExtraPortSettings(
                self.maximum_physical_port_probe_spin.value()
            ).validate()
            if self.extra_port_repository is not None:
                self.extra_port_repository.save(self.extra_port_settings)
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "Could not save admin config", str(error))
            return
        self._dirty = False
        self.setWindowTitle("Admin Config")
        self.accept()

    def _reload(self):
        try:
            self.profiles = self.repository.load_profiles()
            if self.extra_port_repository is not None:
                self.extra_port_settings = self.extra_port_repository.load()
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "Could not reload admin config", str(error))
            return
        self._load_current_profile()
        self.maximum_physical_port_probe_spin.setValue(
            self.extra_port_settings.maximum_physical_port_probe
        )

    def _restore_defaults(self):
        self.profiles = default_limit_profiles()
        self.extra_port_settings = ExtraPortSettings()
        self.maximum_physical_port_probe_spin.setValue(
            self.extra_port_settings.maximum_physical_port_probe
        )
        self._load_current_profile()
        self._dirty = True


__all__ = ["AdminConfigDialog", "AdminPasswordDialog"]
