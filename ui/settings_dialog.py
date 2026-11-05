"""设置对话框。改完当场生效，不要求用户重启。"""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app import autostart
from app.config import Config
from core.exporter import ExportError, export_to_file, import_from_file
from core.repository import Repository
from ui import theme


class SettingsDialog(QDialog):
    def __init__(
        self, config: Config, repo: Repository | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._config = dataclasses.replace(config)
        self._original = dataclasses.replace(config)
        self._repo = repo
        self._ui = autostart.is_enabled()

        self.setWindowTitle("设置")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self._build()
        self._apply_theme()

    # ---------- 界面 ----------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        root.addWidget(self._build_record_group())
        root.addWidget(self._build_app_group())
        if self._repo is not None:
            root.addWidget(self._build_data_group())

        hint = QLabel("热键修改后立即生效，若与其它软件冲突会保留原热键。")
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        root.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_record_group(self) -> QGroupBox:
        group = QGroupBox("记录")
        form = QFormLayout(group)
        form.setContentsMargins(14, 16, 14, 12)
        form.setSpacing(10)

        self._hotkey = QKeySequenceEdit()
        self._hotkey.setKeySequence(QKeySequence(self._config.hotkey))
        self._hotkey.setMaximumSequenceLength(1)
        form.addRow("呼出热键", self._hotkey)

        self._max_items = QSpinBox()
        self._max_items.setRange(50, 5000)
        self._max_items.setSingleStep(50)
        self._max_items.setSuffix(" 条")
        self._max_items.setValue(self._config.max_items)
        form.addRow("最多保留", self._max_items)

        self._max_days = QSpinBox()
        self._max_days.setRange(0, 365)
        self._max_days.setSuffix(" 天")
        self._max_days.setSpecialValueText("不按时间清理")
        self._max_days.setValue(self._config.max_days)
        form.addRow("保留时长", self._max_days)

        self._strict = QCheckBox("过滤疑似密钥、口令")
        self._strict.setChecked(self._config.strict_secret_filter)
        form.addRow("", self._strict)
        return group

    def _build_app_group(self) -> QGroupBox:
        group = QGroupBox("程序")
        form = QFormLayout(group)
        form.setContentsMargins(14, 16, 14, 12)
        form.setSpacing(10)

        self._autostart = QCheckBox("登录 Windows 后自动运行")
        self._autostart.setChecked(self._ui)
        form.addRow("", self._autostart)
        return group

    def _build_data_group(self) -> QGroupBox:
        group = QGroupBox("数据")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 16, 14, 12)
        layout.setSpacing(8)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        export_button = QPushButton("导出为 JSON")
        import_button = QPushButton("从 JSON 导入")
        favorites_button = QPushButton("导出收藏夹")
        export_button.clicked.connect(self._on_export)
        import_button.clicked.connect(self._on_import)
        favorites_button.clicked.connect(self._on_export_favorites)
        buttons.addWidget(export_button)
        buttons.addWidget(import_button)
        buttons.addWidget(favorites_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        hint = QLabel("导入时按内容去重。导出收藏夹只写收藏项，图片会一起打包。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return group

    def _on_export(self) -> None:
        if self._repo is None:
            return
        suggested = time.strftime("clipnest-%Y%m%d-%H%M.json")
        path, _filter = QFileDialog.getSaveFileName(
            self, "导出历史记录", suggested, "JSON 文件 (*.json)"
        )
        if not path:
            return
        try:
            count = export_to_file(self._repo, Path(path))
        except ExportError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出完成", f"共导出 {count} 条记录。")

    def _on_export_favorites(self) -> None:
        if self._repo is None:
            return
        if not self._repo.favorites():
            QMessageBox.information(self, "收藏夹是空的", "先按 Ctrl+P 把内容加进收藏夹。")
            return
        suggested = time.strftime("clipnest-favorites-%Y%m%d-%H%M.json")
        path, _filter = QFileDialog.getSaveFileName(
            self, "导出收藏夹", suggested, "JSON 文件 (*.json)"
        )
        if not path:
            return
        try:
            count = export_to_file(self._repo, Path(path), favorites_only=True)
        except ExportError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        QMessageBox.information(
            self, "导出完成", f"共导出 {count} 条收藏，图片已一并打包。"
        )

    def _on_import(self) -> None:
        if self._repo is None:
            return
        path, _filter = QFileDialog.getOpenFileName(
            self, "导入历史记录", "", "JSON 文件 (*.json)"
        )
        if not path:
            return
        try:
            added, skipped = import_from_file(self._repo, Path(path))
        except ExportError as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        QMessageBox.information(
            self, "导入完成", f"新增 {added} 条，跳过重复 {skipped} 条。"
        )

    def _apply_theme(self) -> None:
        pal = theme.current()
        self.setStyleSheet(
            f"""
            QDialog {{ background: {pal.panel}; color: {pal.text}; }}
            QGroupBox {{
                border: 1px solid {pal.panel_border};
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 6px;
                color: {pal.text_muted};
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
            QLabel {{ color: {pal.text_muted}; }}
            QLabel#hint {{ color: {pal.text_faint}; font-size: 11px; }}
            QSpinBox, QKeySequenceEdit {{
                background: {pal.search_bg};
                border: 1px solid {pal.divider};
                border-radius: 6px;
                padding: 4px 8px;
                color: {pal.text};
                min-height: 22px;
            }}
            QCheckBox {{ color: {pal.text}; spacing: 8px; }}
            QPushButton {{
                background: {pal.search_bg};
                border: 1px solid {pal.divider};
                border-radius: 6px;
                padding: 6px 18px;
                color: {pal.text};
            }}
            QPushButton:hover {{ background: {pal.row_hover}; }}
            """
        )

    # ---------- 结果 ----------

    def result_config(self) -> Config:
        combo = self._hotkey.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText
        )
        if combo:
            self._config.hotkey = combo
        self._config.max_items = self._max_items.value()
        self._config.max_days = self._max_days.value()
        self._config.strict_secret_filter = self._strict.isChecked()
        return self._config

    def accepted_changes(self) -> dict[str, object]:
        """只返回真正变了的项，调用方按需处理。"""
        after = self.result_config()
        changed: dict[str, object] = {}
        if self._original.hotkey != after.hotkey:
            changed["hotkey"] = after.hotkey
        if (
            self._original.max_items != after.max_items
            or self._original.max_days != after.max_days
        ):
            changed["prune"] = True
        if self._autostart.isChecked() != self._ui:
            changed["autostart"] = self._autostart.isChecked()
        return changed
