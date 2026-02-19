from __future__ import annotations

import json
import types
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal, Union, get_args, get_origin

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QWidget,
)

from .model_utils import MISSING, build_model, iter_model_fields, model_to_dict


@dataclass
class _EditorBinding:
    getter: Callable[[], Any]
    setter: Callable[[Any], None]
    resetter: Callable[[], None]
    default: Any


class PathPickerWidget(QWidget):
    def __init__(self, pick_directory: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pick_directory = pick_directory

        self.line_edit = QLineEdit(self)
        self.browse_button = QPushButton("Browse", self)
        self.browse_button.clicked.connect(self._browse)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.line_edit)
        layout.addWidget(self.browse_button)

    def _browse(self) -> None:
        if self._pick_directory:
            selected = QFileDialog.getExistingDirectory(self, "Select directory")
            if selected:
                self.line_edit.setText(selected)
            return

        selected, _ = QFileDialog.getOpenFileName(self, "Select file")
        if selected:
            self.line_edit.setText(selected)


class FlowOptionsEditor(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.mode_combo = QComboBox(self)
        self.mode_combo.addItem("Inline JSON", userData="inline")
        self.mode_combo.addItem("JSON file path", userData="file")

        self.inline_editor = QPlainTextEdit(self)
        self.inline_editor.setPlaceholderText('{"levels": 3}')

        self.file_picker = PathPickerWidget(pick_directory=False, parent=self)

        self.stacked = QStackedWidget(self)
        self.stacked.addWidget(self.inline_editor)
        self.stacked.addWidget(self.file_picker)

        self.validate_button = QPushButton("Validate JSON", self)
        self.validate_button.clicked.connect(self._validate_json)

        layout = QFormLayout(self)
        layout.addRow("Mode", self.mode_combo)
        layout.addRow("Value", self.stacked)
        layout.addRow("", self.validate_button)

        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._on_mode_changed(0)

    def _on_mode_changed(self, _index: int) -> None:
        mode = self.mode_combo.currentData()
        self.stacked.setCurrentIndex(0 if mode == "inline" else 1)

    def _validate_json(self) -> None:
        text = self.inline_editor.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "JSON", "Inline JSON is empty.")
            return
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            QMessageBox.critical(self, "JSON Error", str(exc))
            return
        QMessageBox.information(self, "JSON", "JSON is valid.")

    def get_value(self) -> dict[str, Any] | str:
        mode = self.mode_combo.currentData()
        if mode == "inline":
            text = self.inline_editor.toPlainText().strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid flow_options JSON: {exc}") from exc
            if not isinstance(parsed, dict):
                raise ValueError("Inline flow_options JSON must be an object.")
            return parsed

        return self.file_picker.line_edit.text().strip()

    def set_value(self, value: Any) -> None:
        if isinstance(value, dict):
            self.mode_combo.setCurrentIndex(0)
            self.inline_editor.setPlainText(json.dumps(value, indent=2))
            return

        if value is None:
            self.mode_combo.setCurrentIndex(0)
            self.inline_editor.setPlainText("{}")
            return

        self.mode_combo.setCurrentIndex(1)
        self.file_picker.line_edit.setText(str(value))

    def reset(self) -> None:
        self.mode_combo.setCurrentIndex(0)
        self.inline_editor.setPlainText("{}")
        self.file_picker.line_edit.clear()


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return args[0], True
    return annotation, False


def _annotation_has_type(annotation: Any, target: type[Any]) -> bool:
    base, _ = _unwrap_optional(annotation)
    if base is target:
        return True
    origin = get_origin(base)
    if origin in (Union, types.UnionType):
        return any(_annotation_has_type(arg, target) for arg in get_args(base))
    return False


class SessionConfigForm(QWidget):
    def __init__(self, session_config_cls: type[Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session_config_cls = session_config_cls
        self._bindings: dict[str, _EditorBinding] = {}

        form_layout = QFormLayout(self)
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        for field_spec in iter_model_fields(session_config_cls):
            binding, widget = self._create_editor(
                field_spec.name, field_spec.annotation, field_spec.default
            )
            self._bindings[field_spec.name] = binding
            form_layout.addRow(field_spec.name, widget)

    def _create_editor(
        self, field_name: str, annotation: Any, default: Any
    ) -> tuple[_EditorBinding, QWidget]:
        base_annotation, optional = _unwrap_optional(annotation)

        if field_name == "flow_options":
            editor = FlowOptionsEditor(self)
            binding = _EditorBinding(
                getter=editor.get_value,
                setter=editor.set_value,
                resetter=editor.reset,
                default=default,
            )
            if default is not MISSING:
                binding.setter(default)
            else:
                binding.resetter()
            return binding, editor

        if field_name in {"root", "output_root", "final_results", "center"}:
            editor = PathPickerWidget(pick_directory=field_name != "center", parent=self)

            def getter() -> Any:
                text = editor.line_edit.text().strip()
                if optional and not text:
                    return None
                return text

            def setter(value: Any) -> None:
                editor.line_edit.setText("" if value is None else str(value))

            def resetter() -> None:
                editor.line_edit.clear()

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            return binding, editor

        if base_annotation is bool:
            editor = QCheckBox(self)

            def getter() -> bool:
                return editor.isChecked()

            def setter(value: Any) -> None:
                editor.setChecked(bool(value))

            def resetter() -> None:
                editor.setChecked(False)

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            return binding, editor

        if base_annotation is int:
            editor = QSpinBox(self)
            editor.setRange(-1_000_000_000, 1_000_000_000)

            def getter() -> int:
                return int(editor.value())

            def setter(value: Any) -> None:
                editor.setValue(int(value))

            def resetter() -> None:
                editor.setValue(0)

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            return binding, editor

        if base_annotation is float:
            editor = QDoubleSpinBox(self)
            editor.setRange(-1_000_000_000.0, 1_000_000_000.0)
            editor.setDecimals(6)

            def getter() -> float:
                return float(editor.value())

            def setter(value: Any) -> None:
                editor.setValue(float(value))

            def resetter() -> None:
                editor.setValue(0.0)

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            return binding, editor

        if get_origin(base_annotation) is Literal:
            options = list(get_args(base_annotation))
            editor = QComboBox(self)
            for option in options:
                editor.addItem(str(option), userData=option)

            def getter() -> Any:
                return editor.currentData()

            def setter(value: Any) -> None:
                for index in range(editor.count()):
                    if editor.itemData(index) == value:
                        editor.setCurrentIndex(index)
                        return

            def resetter() -> None:
                if editor.count() > 0:
                    editor.setCurrentIndex(0)

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            else:
                binding.resetter()
            return binding, editor

        if isinstance(base_annotation, type) and issubclass(base_annotation, Enum):
            enum_values = list(base_annotation)
            editor = QComboBox(self)
            for enum_value in enum_values:
                editor.addItem(str(enum_value.value), userData=enum_value)

            def getter() -> Any:
                return editor.currentData()

            def setter(value: Any) -> None:
                for index in range(editor.count()):
                    if editor.itemData(index) == value:
                        editor.setCurrentIndex(index)
                        return

            def resetter() -> None:
                if editor.count() > 0:
                    editor.setCurrentIndex(0)

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            else:
                binding.resetter()
            return binding, editor

        if base_annotation is dict or _annotation_has_type(base_annotation, dict):
            editor = QPlainTextEdit(self)
            editor.setPlaceholderText('{"key": "value"}')

            def getter() -> Any:
                text = editor.toPlainText().strip()
                if not text:
                    return {} if not optional else None
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON for '{field_name}': {exc}") from exc
                if not isinstance(parsed, dict):
                    raise ValueError(f"Field '{field_name}' expects a JSON object.")
                return parsed

            def setter(value: Any) -> None:
                if value is None:
                    editor.setPlainText("")
                else:
                    editor.setPlainText(json.dumps(value, indent=2))

            def resetter() -> None:
                editor.setPlainText("{}" if not optional else "")

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            else:
                binding.resetter()
            return binding, editor

        if base_annotation in {str, Path} or _annotation_has_type(base_annotation, Path):
            editor = QLineEdit(self)

            def getter() -> Any:
                text = editor.text().strip()
                if optional and not text:
                    return None
                return text

            def setter(value: Any) -> None:
                editor.setText("" if value is None else str(value))

            def resetter() -> None:
                editor.clear()

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            return binding, editor

        editor = QLineEdit(self)

        def getter() -> str:
            return editor.text().strip()

        def setter(value: Any) -> None:
            editor.setText("" if value is None else str(value))

        def resetter() -> None:
            editor.clear()

        binding = _EditorBinding(getter=getter, setter=setter, resetter=resetter, default=default)
        if default is not MISSING:
            binding.setter(default)
        return binding, editor

    def get_form_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for name, binding in self._bindings.items():
            data[name] = binding.getter()
        return data

    def set_form_data(self, values: dict[str, Any]) -> None:
        for name, value in values.items():
            binding = self._bindings.get(name)
            if binding is None:
                continue
            binding.setter(value)

    def set_from_config(self, config: Any) -> None:
        self.set_form_data(model_to_dict(config))

    def reset_to_defaults(self) -> None:
        for binding in self._bindings.values():
            if binding.default is MISSING:
                binding.resetter()
            else:
                binding.setter(binding.default)

    def to_session_config(self) -> Any:
        return build_model(self._session_config_cls, self.get_form_data())
