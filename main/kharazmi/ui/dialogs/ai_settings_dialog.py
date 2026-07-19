"""
AISettingsDialog — configure the z.ai API key and model.

Lets the user:
  - View/change the API key
  - Pick the model (defaults to glm-4.5-flash, the free flash model)
  - Set temperature and max_tokens
  - Test the connection

The settings are persisted to ~/.rask/ai_settings.json.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QComboBox, QSpinBox, QDoubleSpinBox, QMessageBox,
    QGroupBox,
)

from ...ai import (
    AIService, load_ai_settings, save_ai_settings,
    DEFAULT_API_KEY, DEFAULT_MODEL, API_URL,
)
from ..theme import Palette


# Available free / cheap models on z.ai
KNOWN_MODELS = [
    ("glm-4.5-flash", "GLM-4.5 Flash (free, fast)"),
    ("glm-4.5-air", "GLM-4.5 Air (cheap)"),
    ("glm-4.5", "GLM-4.5 (full)"),
    ("glm-4-plus", "GLM-4 Plus"),
    ("glm-4-flash", "GLM-4 Flash (legacy)"),
]


class AISettingsDialog(QDialog):
    """Modal dialog for AI configuration."""

    def __init__(self, ai_service: AIService, parent=None) -> None:
        super().__init__(parent)
        self.ai = ai_service
        self.setWindowTitle("AI Settings")
        self.setMinimumWidth(560)
        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        title = QLabel("AI CONFIGURATION")
        title.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 11px; "
            f"font-weight: bold; letter-spacing: 2px;"
        )
        layout.addWidget(title)

        # Connection group
        conn_group = QGroupBox("Connection")
        conn_form = QFormLayout(conn_group)
        conn_form.setSpacing(6)

        self._api_key_edit = QLineEdit(ai_service.settings.get("api_key", ""))
        self._api_key_edit.setEchoMode(QLineEdit.Password)
        self._api_key_edit.setStyleSheet(self._input_style())
        # Show/hide toggle
        key_row = QHBoxLayout()
        key_row.addWidget(self._api_key_edit, stretch=1)
        self._show_key_btn = QPushButton("Show")
        self._show_key_btn.setCheckable(True)
        self._show_key_btn.setStyleSheet(self._button_style())
        self._show_key_btn.toggled.connect(self._on_show_key_toggled)
        key_row.addWidget(self._show_key_btn)
        conn_form.addRow("API key", key_row)

        # Base URL (informational, but editable)
        self._url_edit = QLineEdit(ai_service.settings.get("base_url", API_URL))
        self._url_edit.setStyleSheet(self._input_style())
        conn_form.addRow("Base URL", self._url_edit)

        # Model selector
        self._model_combo = QComboBox()
        current_model = ai_service.settings.get("model", DEFAULT_MODEL)
        for code, name in KNOWN_MODELS:
            self._model_combo.addItem(f"{name}  ({code})", code)
            if code == current_model:
                self._model_combo.setCurrentIndex(self._model_combo.count() - 1)
        # If current model isn't in the known list, add it
        if self._model_combo.currentData() != current_model:
            self._model_combo.addItem(f"Custom ({current_model})", current_model)
            self._model_combo.setCurrentIndex(self._model_combo.count() - 1)
        self._model_combo.setStyleSheet(self._input_style())
        conn_form.addRow("Model", self._model_combo)

        # Test connection button
        self._test_btn = QPushButton("Test Connection")
        self._test_btn.setProperty("variant", "primary")
        self._test_btn.clicked.connect(self._on_test_connection)
        self._test_status = QLabel("")
        self._test_status.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px;"
        )
        test_row = QHBoxLayout()
        test_row.addWidget(self._test_btn)
        test_row.addWidget(self._test_status, stretch=1)
        conn_form.addRow("", test_row)

        layout.addWidget(conn_group)

        # Generation params
        gen_group = QGroupBox("Generation Parameters")
        gen_form = QFormLayout(gen_group)

        self._temp_spin = QDoubleSpinBox()
        self._temp_spin.setRange(0.0, 2.0)
        self._temp_spin.setSingleStep(0.1)
        self._temp_spin.setDecimals(2)
        self._temp_spin.setValue(float(ai_service.settings.get("temperature", 0.7)))
        gen_form.addRow("Temperature (0=deterministic, 2=creative)", self._temp_spin)

        self._max_tokens_spin = QSpinBox()
        self._max_tokens_spin.setRange(256, 32768)
        self._max_tokens_spin.setSingleStep(256)
        self._max_tokens_spin.setValue(int(ai_service.settings.get("max_tokens", 4096)))
        gen_form.addRow("Max tokens per response", self._max_tokens_spin)

        layout.addWidget(gen_group)

        # Help text
        help_text = QLabel(
            "<b>Where to get an API key:</b><br>"
            "Visit <a href='https://z.ai'>https://z.ai</a>, sign up, and generate a key.<br>"
            "The free <code>glm-4.5-flash</code> model is sufficient for route planning.<br>"
            "Your key is stored locally at <code>~/.rask/ai_settings.json</code>."
        )
        help_text.setStyleSheet(
            f"color: {Palette.TEXT_SECONDARY}; font-size: 11px; padding: 8px;"
        )
        help_text.setWordWrap(True)
        help_text.setTextFormat(Qt.RichText)
        help_text.setOpenExternalLinks(True)
        layout.addWidget(help_text)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setProperty("variant", "primary")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _input_style(self) -> str:
        return f"""
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border: 1px solid {Palette.GOLD_PRIMARY};
            }}
        """

    def _button_style(self) -> str:
        return f"""
            QPushButton {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_SECONDARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                border: 1px solid {Palette.GOLD_PRIMARY};
                color: {Palette.GOLD_BRIGHT};
            }}
            QPushButton:checked {{
                background-color: {Palette.BG_SELECTED};
                color: {Palette.GOLD_BRIGHT};
            }}
        """

    def _on_show_key_toggled(self, checked: bool) -> None:
        self._api_key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        self._show_key_btn.setText("Hide" if checked else "Show")

    def _on_test_connection(self) -> None:
        # Save current values to the service temporarily
        self._apply_to_service()
        self._test_btn.setEnabled(False)
        self._test_status.setText("⏳ Testing...")
        self._test_status.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px;"
        )

        def _cb(success, result):
            self._test_btn.setEnabled(True)
            if success:
                self._test_status.setText(f"✓ {result}")
                self._test_status.setStyleSheet(
                    f"color: {Palette.GOLD_BRIGHT}; font-size: 11px;"
                )
            else:
                self._test_status.setText(f"✗ {result}")
                self._test_status.setStyleSheet(
                    f"color: {Palette.STATUS_BLOCKED}; font-size: 11px;"
                )

        self.ai.test_connection(_cb)

    def _apply_to_service(self) -> None:
        self.ai.update_settings(
            api_key=self._api_key_edit.text().strip(),
            base_url=self._url_edit.text().strip() or API_URL,
            model=self._model_combo.currentData() or DEFAULT_MODEL,
            temperature=self._temp_spin.value(),
            max_tokens=self._max_tokens_spin.value(),
        )

    def _on_save(self) -> None:
        self._apply_to_service()
        self.accept()
