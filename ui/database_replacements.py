"""Database-aware replacement editor for append-only routing documentation."""

from __future__ import annotations

from PyQt5.QtCore import QSize, QSettings, QTimer, Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from application.replacement_persistence_workflow import (
    CORRECTION_REASONS,
    NORMAL_REPLACEMENT_REASONS,
    REPLACEMENT_REASON_PLACEHOLDER,
    ReplacementChangeRequest,
    ReplacementEditorModel,
)


REPLACEMENT_LIGHT_STYLESHEET = """
QDialog#database_replacement_dialog {
    background: #eceff1;
    color: #202124;
}
QDialog#database_replacement_dialog QLabel {
    color: #202124;
}
QDialog#database_replacement_dialog QGroupBox {
    border: 1px solid #c7cdd1;
    border-radius: 4px;
    margin-top: 8px;
    padding: 10px 6px 6px 6px;
    color: #202124;
}
QDialog#database_replacement_dialog QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}
QDialog#database_replacement_dialog QSplitter::handle {
    background: #c7cdd1;
}
QDialog#database_replacement_dialog QSplitter::handle:hover {
    background: #9aa4ad;
}
QTabWidget#database_replacement_tabs::pane {
    background: #f7f8f9;
    border: 1px solid #c7cdd1;
}
QWidget#database_replacement_tab_page {
    background: #f7f8f9;
    color: #202124;
}
QTabBar#database_replacement_tab_bar::tab {
    background: #e1e5e8;
    color: #3f464d;
    border: 1px solid #c7cdd1;
    padding: 6px 12px;
}
QTabBar#database_replacement_tab_bar::tab:selected {
    background: #ffffff;
    color: #202124;
}
QDialog#database_replacement_dialog QLineEdit,
QDialog#database_replacement_dialog QComboBox,
QDialog#database_replacement_dialog QSpinBox {
    background: #ffffff;
    color: #202124;
    border: 1px solid #c7cdd1;
    selection-background-color: #ffd9dd;
    selection-color: #202124;
}
QDialog#database_replacement_dialog QLineEdit:disabled,
QDialog#database_replacement_dialog QComboBox:disabled,
QDialog#database_replacement_dialog QSpinBox:disabled {
    background: #edf0f2;
    color: #626970;
}
QTableWidget#database_replacement_table {
    background: #ffffff;
    alternate-background-color: #f3f5f6;
    color: #202124;
    border: 1px solid #c7cdd1;
    gridline-color: #dbe1e4;
    selection-background-color: #ffd9dd;
    selection-color: #202124;
}
QTableWidget#database_replacement_table QHeaderView::section,
QTableWidget#database_replacement_table QTableCornerButton::section {
    background: #e4eeee;
    color: #202124;
    border: 1px solid #c7cdd1;
    padding: 6px;
    font-weight: 600;
}
"""


REPLACEMENT_DARK_STYLESHEET = """
QDialog#database_replacement_dialog {
    background: #202124;
    color: #e8eaed;
}
QDialog#database_replacement_dialog QLabel {
    color: #e8eaed;
}
QDialog#database_replacement_dialog QGroupBox {
    border: 1px solid #4a4f57;
    border-radius: 4px;
    margin-top: 8px;
    padding: 10px 6px 6px 6px;
    color: #e8eaed;
}
QDialog#database_replacement_dialog QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}
QDialog#database_replacement_dialog QSplitter::handle {
    background: #4a4f57;
}
QDialog#database_replacement_dialog QSplitter::handle:hover {
    background: #737b86;
}
QTabWidget#database_replacement_tabs::pane {
    background: #25272b;
    border: 1px solid #4a4f57;
}
QWidget#database_replacement_tab_page {
    background: #25272b;
    color: #e8eaed;
}
QTabBar#database_replacement_tab_bar::tab {
    background: #2b2e33;
    color: #b3bbc5;
    border: 1px solid #4a4f57;
    padding: 6px 12px;
}
QTabBar#database_replacement_tab_bar::tab:selected {
    background: #3a3e45;
    color: #ffffff;
}
QDialog#database_replacement_dialog QLineEdit,
QDialog#database_replacement_dialog QComboBox,
QDialog#database_replacement_dialog QSpinBox {
    background: #373a40;
    color: #e8eaed;
    border: 1px solid #5a6069;
    selection-background-color: #e60013;
    selection-color: #ffffff;
}
QDialog#database_replacement_dialog QLineEdit:disabled,
QDialog#database_replacement_dialog QComboBox:disabled,
QDialog#database_replacement_dialog QSpinBox:disabled {
    background: #2b2e33;
    color: #9299a3;
}
QDialog#database_replacement_dialog QComboBox QAbstractItemView {
    background: #373a40;
    color: #e8eaed;
    selection-background-color: #e60013;
    selection-color: #ffffff;
}
QTableWidget#database_replacement_table {
    background: #25272b;
    alternate-background-color: #2b2e33;
    color: #e8eaed;
    border: 1px solid #4a4f57;
    gridline-color: #454a52;
    selection-background-color: #8b000b;
    selection-color: #ffffff;
}
QTableWidget#database_replacement_table QHeaderView::section,
QTableWidget#database_replacement_table QTableCornerButton::section {
    background: #3a3e45;
    color: #f0f2f4;
    border: 1px solid #4a4f57;
    padding: 6px;
    font-weight: 600;
}
"""


class DatabaseReplacementDialog(QDialog):
    """Collect explicit operator approvals without touching switch hardware."""

    def __init__(self, model: ReplacementEditorModel, parent=None) -> None:
        super().__init__(parent)
        self.model = model
        self.replacement_requests: tuple[ReplacementChangeRequest, ...] = ()
        self.spares_to_designate: tuple[int, ...] = ()
        self.spares_to_undesignate: tuple[int, ...] = ()
        self.spare_operator = model.default_operator
        self._pending: list[ReplacementChangeRequest] = []
        self._selected_recommendation = None
        self._settings = QSettings("Light Workbench", "LightWorkbench")

        self.setWindowTitle("Manage Port Replacements")
        self.setObjectName("database_replacement_dialog")
        self.setMinimumSize(980, 720)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Physical rerouting is completed outside Light Workbench. "
                "This screen records operator-supplied documentation; it does not "
                "command or verify the switch mapping."
            )
        )
        layout.addWidget(
            QLabel(
                f"Unit: {model.unit_label or 'Not recorded'}    "
                f"Switch: {model.switch_label or 'Not recorded'}    "
                f"Assignment: {model.assignment_id}    Run: {model.related_run_id}"
            )
        )

        self.tabs = QTabWidget()
        self.tabs.setObjectName("database_replacement_tabs")
        self.tabs.tabBar().setObjectName("database_replacement_tab_bar")
        self.tabs.addTab(self._build_record_tab(), "Record Replacements")
        self.tabs.addTab(self._build_spares_tab(), "Designated Spares")
        self.tabs.addTab(self._build_history_tab(), "Audit History")
        layout.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept_changes)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.apply_theme(bool(getattr(parent, "dark_mode_enabled", False)))
        self._restore_ui_state()

    def _restore_ui_state(self) -> None:
        """Restore the replacement editor's size and splitter positions."""
        geometry = self._settings.value("database_replacement_dialog_geometry")
        if not geometry or not self.restoreGeometry(geometry):
            saved_size = self._settings.value("database_replacement_dialog_size")
            if isinstance(saved_size, QSize) and saved_size.isValid():
                self.resize(saved_size)
            else:
                screen = self.screen() or QApplication.primaryScreen()
                available = screen.availableGeometry() if screen else None
                if available:
                    width = min(1200, max(980, available.width() - 80))
                    height = min(820, max(720, available.height() - 80))
                    self.resize(width, height)
                else:
                    self.resize(1200, 820)
        splitter_states = (
            ("database_replacement_record_splitter_state", self.record_splitter),
            ("database_replacement_upper_splitter_state", self.record_upper_splitter),
            ("database_replacement_lower_splitter_state", self.record_lower_splitter),
        )
        saved_states = tuple(
            (splitter, self._settings.value(key)) for key, splitter in splitter_states
        )
        QTimer.singleShot(
            0,
            lambda: self._restore_splitter_states_or_apply_defaults(saved_states),
        )

    def _restore_splitter_states_or_apply_defaults(self, saved_states) -> None:
        """Apply splitter settings after Qt has assigned the dialog's size."""
        for splitter, state in saved_states:
            if state:
                splitter.restoreState(state)
        states_by_name = {
            splitter.objectName(): state for splitter, state in saved_states
        }
        if (
            not states_by_name.get("database_replacement_record_splitter")
            and self.record_splitter.height() > 0
        ):
            height = self.record_splitter.height()
            self.record_splitter.setSizes([round(height * 0.55), round(height * 0.45)])
        if (
            not states_by_name.get("database_replacement_upper_splitter")
            and self.record_upper_splitter.width() > 0
        ):
            width = self.record_upper_splitter.width()
            self.record_upper_splitter.setSizes([round(width * 0.65), round(width * 0.35)])
        if (
            not states_by_name.get("database_replacement_lower_splitter")
            and self.record_lower_splitter.width() > 0
        ):
            width = self.record_lower_splitter.width()
            self.record_lower_splitter.setSizes([round(width * 0.60), round(width * 0.40)])

    def _save_ui_state(self) -> None:
        """Persist only the replacement dialog's presentation state."""
        self._settings.setValue(
            "database_replacement_dialog_geometry", self.saveGeometry()
        )
        self._settings.setValue("database_replacement_dialog_size", self.size())
        for key, splitter in (
            ("database_replacement_record_splitter_state", self.record_splitter),
            ("database_replacement_upper_splitter_state", self.record_upper_splitter),
            ("database_replacement_lower_splitter_state", self.record_lower_splitter),
        ):
            self._settings.setValue(key, splitter.saveState())
        self._settings.sync()

    def closeEvent(self, event) -> None:
        self._save_ui_state()
        super().closeEvent(event)

    def _build_record_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("database_replacement_tab_page")
        layout = QVBoxLayout(page)

        self.record_splitter = QSplitter(Qt.Vertical)
        self.record_splitter.setObjectName("database_replacement_record_splitter")
        self.record_splitter.setChildrenCollapsible(False)

        upper_splitter = QSplitter(Qt.Horizontal)
        upper_splitter.setObjectName("database_replacement_upper_splitter")
        upper_splitter.setChildrenCollapsible(False)
        upper_splitter.addWidget(self._build_recommendation_panel())
        upper_splitter.addWidget(self._build_details_panel())
        upper_splitter.setStretchFactor(0, 13)
        upper_splitter.setStretchFactor(1, 7)
        upper_splitter.setSizes([650, 350])
        self.record_upper_splitter = upper_splitter

        lower_splitter = QSplitter(Qt.Horizontal)
        lower_splitter.setObjectName("database_replacement_lower_splitter")
        lower_splitter.setChildrenCollapsible(False)
        lower_splitter.addWidget(self._build_pending_panel())
        lower_splitter.addWidget(self._build_mapping_panel())
        lower_splitter.setStretchFactor(0, 3)
        lower_splitter.setStretchFactor(1, 2)
        lower_splitter.setSizes([600, 400])
        self.record_lower_splitter = lower_splitter

        self.record_splitter.addWidget(upper_splitter)
        self.record_splitter.addWidget(lower_splitter)
        self.record_splitter.setStretchFactor(0, 11)
        self.record_splitter.setStretchFactor(1, 9)
        self.record_splitter.setSizes([430, 350])
        layout.addWidget(self.record_splitter, 1)
        self.begin_manual_replacement()
        return page

    @staticmethod
    def _configure_table(table: QTableWidget, *, minimum_height: int = 180) -> None:
        """Apply shared table behavior without changing table contents."""
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setMinimumHeight(minimum_height)
        table.verticalHeader().setDefaultSectionSize(28)
        table.horizontalHeader().setMinimumSectionSize(55)

    @staticmethod
    def _candidate_il_text(recommendation) -> str:
        values = []
        for value in (
            recommendation.candidate_loss_1310_db,
            recommendation.candidate_loss_1550_db,
        ):
            if value is not None:
                values.append(f"{value:.4f}")
        return " / ".join(values) + (" dB" if values else "Not available")

    @classmethod
    def _candidate_il_tooltip(cls, recommendation) -> str:
        candidate_text = cls._candidate_il_text(recommendation)
        worst = recommendation.candidate_worst_loss_db
        worst_text = "Not available" if worst is None else f"{worst:.4f} dB"
        return (
            f"Candidate physical port: "
            f"{recommendation.proposed_replacement_physical_port}\n"
            f"1310 nm / 1550 nm: {candidate_text}\n"
            f"Worst case: {worst_text}\n\n"
            "This is the accepted measurement for the candidate port, "
            "not a guaranteed result after physical rerouting."
        )

    def _set_reason_mode(self, correction: bool) -> None:
        self._correction_mode = correction
        self.mode_label.setText(
            "Mode: Mapping correction" if correction else "Mode: Replacement"
        )
        reasons = CORRECTION_REASONS if correction else NORMAL_REPLACEMENT_REASONS
        self.reason_combo.blockSignals(True)
        self.reason_combo.clear()
        self.reason_combo.addItem(REPLACEMENT_REASON_PLACEHOLDER, None)
        for reason in reasons:
            self.reason_combo.addItem(reason, reason)
        self.reason_combo.setCurrentIndex(0)
        self.reason_combo.blockSignals(False)

    def _build_recommendation_panel(self) -> QGroupBox:
        panel = QGroupBox("Replacement recommendations (advisory)")
        panel.setObjectName("database_replacement_recommendations_panel")
        panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)

        self.recommendation_table = QTableWidget(0, 6)
        self.recommendation_table.setObjectName("database_replacement_table")
        self.recommendation_table.setHorizontalHeaderLabels(
            [
                "Logical",
                "Current Port",
                "Proposed Port",
                "Category",
                "Improvement",
                "Candidate IL",
            ]
        )
        self._configure_table(self.recommendation_table, minimum_height=220)
        for recommendation in self.model.recommendations:
            row = self.recommendation_table.rowCount()
            self.recommendation_table.insertRow(row)
            values = (
                recommendation.logical_channel,
                recommendation.current_effective_physical_port,
                recommendation.proposed_replacement_physical_port,
                recommendation.category.title(),
                (
                    ""
                    if recommendation.improvement_db is None
                    else f"{recommendation.improvement_db:.4f} dB"
                ),
                self._candidate_il_text(recommendation),
            )
            for column, value in enumerate(values):
                self.recommendation_table.setItem(row, column, QTableWidgetItem(str(value)))
            candidate_item = self.recommendation_table.item(row, 5)
            candidate_item.setToolTip(self._candidate_il_tooltip(recommendation))
        layout.addWidget(self.recommendation_table)
        header = self.recommendation_table.horizontalHeader()
        for column in range(5):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        header_item = self.recommendation_table.horizontalHeaderItem(5)
        header_item.setToolTip("Accepted candidate-port measurement at 1310 / 1550 nm.")

        action_row = QHBoxLayout()
        use_recommendation = QPushButton("Use Selected Recommendation")
        use_recommendation.clicked.connect(self.use_selected_recommendation)
        action_row.addWidget(use_recommendation)
        manual = QPushButton("Add Manual Replacement")
        manual.clicked.connect(self.begin_manual_replacement)
        action_row.addWidget(manual)
        action_row.addStretch()
        layout.addLayout(action_row)
        return panel

    def _build_details_panel(self) -> QGroupBox:
        panel = QGroupBox("Replacement details")
        panel.setObjectName("database_replacement_details_panel")
        panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)

        self.mode_label = QLabel()
        self.mode_label.setObjectName("database_replacement_mode_label")
        layout.addWidget(self.mode_label)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.logical_channel_combo = QComboBox()
        for route in self.model.channel_map:
            self.logical_channel_combo.addItem(str(route.logical_channel), route.logical_channel)
        self.logical_channel_combo.currentIndexChanged.connect(self._logical_channel_changed)
        self.current_port_edit = QLineEdit()
        self.current_port_edit.setReadOnly(True)
        self.proposed_port_spin = QSpinBox()
        self.proposed_port_spin.setRange(1, 4096)
        self.proposed_port_spin.valueChanged.connect(self._refresh_evidence)
        self.category_edit = QLabel()
        self.category_edit.setObjectName("database_replacement_category_value")
        self.improvement_edit = QLabel()
        self.improvement_edit.setObjectName("database_replacement_improvement_value")
        self.candidate_il_label = QLabel()
        self.candidate_il_label.setObjectName("database_replacement_candidate_il_value")
        self.candidate_il_label.setWordWrap(True)
        self.reason_combo = QComboBox()
        self.operator_edit = QLineEdit(self.model.default_operator)
        self.details_edit = QLineEdit()
        self.candidate_warning_label = QLabel()
        self.candidate_warning_label.setObjectName(
            "database_replacement_candidate_warning"
        )
        for widget, width in (
            (self.logical_channel_combo, 90),
            (self.current_port_edit, 90),
            (self.proposed_port_spin, 90),
            (self.operator_edit, 100),
        ):
            widget.setFixedWidth(width)
        form.addRow("Logical channel:", self.logical_channel_combo)
        form.addRow("Current port:", self.current_port_edit)
        form.addRow("Replacement port:", self.proposed_port_spin)
        form.addRow("Operator:", self.operator_edit)
        form.addRow("Category:", self.category_edit)
        form.addRow("Improvement:", self.improvement_edit)
        form.addRow("Candidate IL:", self.candidate_il_label)
        form.addRow("Reason:", self.reason_combo)
        form.addRow("Additional details:", self.details_edit)
        layout.addLayout(form, 1)

        layout.addWidget(self.candidate_warning_label)

        queue_button = QPushButton("Queue Replacement for Save")
        queue_button.clicked.connect(self.queue_replacement)
        layout.addWidget(queue_button)
        return panel

    def _build_pending_panel(self) -> QGroupBox:
        panel = QGroupBox("Queued replacements")
        panel.setObjectName("database_replacement_pending_panel")
        panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("Append-only records; nothing is saved until Save."))

        self.pending_table = QTableWidget(0, 7)
        self.pending_table.setObjectName("database_replacement_table")
        self.pending_table.setHorizontalHeaderLabels(
            ["Logical", "Current", "Proposed", "Category", "Improvement", "Reason", "Operator"]
        )
        self._configure_table(self.pending_table, minimum_height=180)
        pending_header = self.pending_table.horizontalHeader()
        for column in range(5):
            pending_header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        pending_header.setSectionResizeMode(5, QHeaderView.Stretch)
        pending_header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.pending_empty_label = QLabel("No replacements have been queued.")
        self.pending_empty_label.setAlignment(Qt.AlignCenter)
        self.pending_empty_label.setObjectName("database_replacement_empty_state")
        layout.addWidget(self.pending_empty_label, 1)
        layout.addWidget(self.pending_table, 1)
        self.pending_table.hide()

        remove_button = QPushButton("Remove Selected Queued Replacement")
        remove_button.clicked.connect(self.remove_queued_replacement)
        layout.addWidget(remove_button)
        return panel

    def _build_mapping_panel(self) -> QGroupBox:
        panel = QGroupBox("Current effective assignment mapping")
        panel.setObjectName("database_replacement_mapping_panel")
        panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)
        self.active_mapping_table = QTableWidget(0, 3)
        self.active_mapping_table.setObjectName("database_replacement_table")
        self.active_mapping_table.setHorizontalHeaderLabels(
            ["Logical Channel", "Initial Port", "Current Effective Port"]
        )
        self._configure_table(self.active_mapping_table, minimum_height=180)
        for route in self.model.channel_map:
            row = self.active_mapping_table.rowCount()
            self.active_mapping_table.insertRow(row)
            for column, value in enumerate(
                (route.logical_channel, route.initial_physical_port, route.effective_physical_port)
            ):
                self.active_mapping_table.setItem(row, column, QTableWidgetItem(str(value)))
        layout.addWidget(self.active_mapping_table)
        mapping_header = self.active_mapping_table.horizontalHeader()
        for column in range(3):
            mapping_header.setSectionResizeMode(column, QHeaderView.Stretch)
        correction = QPushButton("Correct Selected Mapping...")
        correction.clicked.connect(self.begin_correction)
        layout.addWidget(correction)
        return panel

    def _build_spares_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("database_replacement_tab_page")
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel(
                "Existing spares start selected. Analysis recommendations are preselected "
                "for review, but no spare event is recorded until Save."
            )
        )
        self.spare_table = QTableWidget(0, 3)
        self.spare_table.setObjectName("database_replacement_table")
        self.spare_table.setHorizontalHeaderLabels(["Keep/Designate", "Physical Port", "Source"])
        existing = set(self.model.existing_spares)
        recommended = set(self.model.recommended_spares)
        for port in sorted(existing.union(recommended)):
            row = self.spare_table.rowCount()
            self.spare_table.insertRow(row)
            checkbox = QTableWidgetItem()
            checkbox.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            checkbox.setCheckState(Qt.Checked)
            checkbox.setData(Qt.UserRole, port)
            if port in existing and port in recommended:
                source = "Existing; recommended"
            elif port in existing:
                source = "Existing designated spare"
            else:
                source = "New analysis recommendation"
            self.spare_table.setItem(row, 0, checkbox)
            self.spare_table.setItem(row, 1, QTableWidgetItem(str(port)))
            self.spare_table.setItem(row, 2, QTableWidgetItem(source))
        self.spare_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.spare_table)
        return page

    def _build_history_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("database_replacement_tab_page")
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel(
                "SQL replacement history is append-only. Corrections and reversals are "
                "recorded as new rows."
            )
        )
        self.history_table = QTableWidget(0, 9)
        self.history_table.setObjectName("database_replacement_table")
        self.history_table.setHorizontalHeaderLabels(
            [
                "ID", "Logical", "Previous", "Replacement", "Reason", "Operator",
                "Replaced (UTC)", "Related Run ID", "Notes",
            ]
        )
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for record in self.model.replacement_history:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            values = (
                record.replacement_id,
                record.logical_channel,
                record.previous_physical_port,
                record.replacement_physical_port,
                record.reason,
                record.replaced_by,
                record.replaced_at_utc.isoformat(),
                "" if record.related_run_id is None else record.related_run_id,
                record.notes or "",
            )
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.history_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.history_table)
        return page

    def apply_theme(self, dark_mode: bool) -> None:
        """Keep the independently rendered tab pages readable in either theme."""
        self.setStyleSheet(
            REPLACEMENT_DARK_STYLESHEET
            if dark_mode
            else REPLACEMENT_LIGHT_STYLESHEET
        )

    def begin_manual_replacement(self) -> None:
        self._selected_recommendation = None
        self._set_reason_mode(False)
        self.category_edit.clear()
        self.improvement_edit.clear()
        self.candidate_il_label.clear()
        self.candidate_warning_label.clear()
        self.details_edit.clear()
        self.operator_edit.setText(self.model.default_operator)
        self._logical_channel_changed()
        self._refresh_evidence()

    def use_selected_recommendation(self) -> None:
        row = self.recommendation_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Select a recommendation",
                "Select one recommendation first.",
            )
            return
        recommendation = self.model.recommendations[row]
        self._selected_recommendation = recommendation
        self._set_reason_mode(False)
        index = self.logical_channel_combo.findData(recommendation.logical_channel)
        self.logical_channel_combo.setCurrentIndex(index)
        self.current_port_edit.setText(str(recommendation.current_effective_physical_port))
        self.proposed_port_spin.setValue(recommendation.proposed_replacement_physical_port)
        self.category_edit.setText(recommendation.category.title())
        self.improvement_edit.setText(
            ""
            if recommendation.improvement_db is None
            else f"{recommendation.improvement_db:.4f} dB"
        )
        self.candidate_il_label.setText(self._candidate_il_text(recommendation))
        self.candidate_il_label.setToolTip(self._candidate_il_tooltip(recommendation))
        self.operator_edit.setText(self.model.default_operator)
        self.details_edit.clear()
        self._refresh_evidence()

    def begin_correction(self) -> None:
        row = self.active_mapping_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Select a mapping", "Select the logical channel to correct or replace again."
            )
            return
        logical_channel = int(self.active_mapping_table.item(row, 0).text())
        self._selected_recommendation = None
        self._set_reason_mode(True)
        self.category_edit.clear()
        self.improvement_edit.clear()
        self.candidate_il_label.clear()
        self.candidate_warning_label.clear()
        self.details_edit.clear()
        self.operator_edit.setText(self.model.default_operator)
        self.logical_channel_combo.setCurrentIndex(
            self.logical_channel_combo.findData(logical_channel)
        )
        self._refresh_evidence()

    def _logical_channel_changed(self, _index=None) -> None:
        logical_channel = self.logical_channel_combo.currentData()
        if logical_channel is None:
            self.current_port_edit.clear()
            return
        self.current_port_edit.setText(str(self.model.current_effective_port(logical_channel)))

    def _refresh_evidence(self, _value=None) -> None:
        port = self.proposed_port_spin.value()
        candidate = next(
            (
                recommendation
                for recommendation in self.model.recommendations
                if recommendation.proposed_replacement_physical_port == port
            ),
            None,
        )
        if candidate is not None:
            self.candidate_il_label.setText(self._candidate_il_text(candidate))
            self.candidate_il_label.setToolTip(self._candidate_il_tooltip(candidate))
        else:
            self.candidate_il_label.setText("Not available")
            self.candidate_il_label.setToolTip(
                "No accepted candidate-port measurement is available."
            )
        if port in set(self.model.measured_physical_ports):
            self.candidate_warning_label.clear()
            self.candidate_warning_label.setStyleSheet("")
        else:
            self.candidate_warning_label.setText(
                "Warning: no accepted measurement is available for this candidate port."
            )
            self.candidate_warning_label.setStyleSheet("color: #d98200;")

    def queue_replacement(self) -> None:
        logical_channel = int(self.logical_channel_combo.currentData())
        current_port = self.model.current_effective_port(logical_channel)
        proposed_port = self.proposed_port_spin.value()
        reason = self.reason_combo.currentData()
        if reason is not None:
            reason = str(reason).strip()
        operator = self.operator_edit.text().strip()
        if proposed_port == current_port:
            QMessageBox.warning(
                self,
                "Invalid replacement",
                "The proposed port must differ from the current effective port.",
            )
            return
        if not reason:
            QMessageBox.warning(
                self,
                "Reason required",
                "Select a reason before queueing the replacement.",
            )
            return
        if not operator:
            QMessageBox.warning(
                self,
                "Operator required",
                "Enter who performed or recorded the replacement.",
            )
            return
        request = ReplacementChangeRequest(
            logical_channel=logical_channel,
            replacement_physical_port=proposed_port,
            reason=reason,
            replaced_by=operator,
            notes=self.details_edit.text().strip() or None,
            source_recommendation_id=(
                self._selected_recommendation.recommendation_id
                if self._selected_recommendation is not None
                and self._selected_recommendation.logical_channel == logical_channel
                and self._selected_recommendation.proposed_replacement_physical_port
                == proposed_port
                else None
            ),
        )
        self._pending.append(request)
        category = self.category_edit.text().strip()
        improvement = self.improvement_edit.text().strip()
        row = self.pending_table.rowCount()
        self.pending_table.insertRow(row)
        for column, value in enumerate(
            (logical_channel, current_port, proposed_port, category, improvement, reason, operator)
        ):
            self.pending_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.pending_table.selectRow(row)
        self.pending_empty_label.hide()
        self.pending_table.show()
        self.begin_manual_replacement()

    def remove_queued_replacement(self) -> None:
        row = self.pending_table.currentRow()
        if row >= 0:
            self.pending_table.removeRow(row)
            self._pending.pop(row)
            if self.pending_table.rowCount() == 0:
                self.pending_table.hide()
                self.pending_empty_label.show()

    def _spare_changes(self) -> tuple[tuple[int, ...], tuple[int, ...]]:
        existing = set(self.model.existing_spares)
        selected = set()
        for row in range(self.spare_table.rowCount()):
            item = self.spare_table.item(row, 0)
            if item.checkState() == Qt.Checked:
                selected.add(int(item.data(Qt.UserRole)))
        return tuple(sorted(selected - existing)), tuple(sorted(existing - selected))

    def accept_changes(self) -> None:
        designate, undesignate = self._spare_changes()
        self.replacement_requests = tuple(self._pending)
        self.spares_to_designate = designate
        self.spares_to_undesignate = undesignate
        operators = [request.replaced_by for request in self._pending]
        self.spare_operator = (operators[0] if operators else self.model.default_operator).strip()
        if (designate or undesignate) and not self.spare_operator:
            QMessageBox.warning(
                self,
                "Operator required",
                "Enter Tested by before changing designated spares.",
            )
            return
        self.accept()


__all__ = ["DatabaseReplacementDialog"]
