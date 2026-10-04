from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QSlider, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from audio import prepare_recording
from gemini_tts import GeminiTTS
from project import StudioProject
from render import render


class StudioWindow(QMainWindow):
    def __init__(self, project_path: Path):
        super().__init__()
        self.project_path = project_path
        self.project_dir = project_path.parent
        self.project = StudioProject.load(project_path)
        self.setWindowTitle("Saseok Studio — 사석 제작 편집기")
        self.resize(1450, 850)
        self._build_ui()
        self.refresh_table()
        if self.character.count():
            self.load_profile(self.character.currentText())

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)

        left = QVBoxLayout()
        left.addWidget(QLabel("대사 / 음성 트랙"))
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "장면", "인물", "대사", "소스", "녹음"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemSelectionChanged.connect(self.on_line_selected)
        left.addWidget(self.table)
        buttons = QHBoxLayout()
        for label, fn in [
            ("친구 녹음 넣기", self.import_recording),
            ("선택 대사 AI 생성", self.generate_ai),
            ("선택 대사 음소거", self.mute_line),
            ("자동 선택으로 복구", self.restore_line),
        ]:
            b = QPushButton(label)
            b.clicked.connect(fn)
            buttons.addWidget(b)
        left.addLayout(buttons)
        layout.addLayout(left, 3)

        right = QVBoxLayout()
        form = QFormLayout()
        self.character = QComboBox()
        self.character.addItems(sorted(self.project.characters))
        self.character.currentTextChanged.connect(self.load_profile)
        form.addRow("성우/캐릭터", self.character)

        self.mode = QComboBox()
        self.mode.addItems(["ai", "external", "muted"])
        form.addRow("기본 음성 소스", self.mode)

        self.model = QComboBox()
        self.model.addItems(["gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts"])
        form.addRow("Gemini TTS", self.model)

        self.voice = QLineEdit()
        form.addRow("Voice 이름", self.voice)

        self.sliders = {}
        for key, title in [
            ("age", "나이 느낌"),
            ("pitch", "음역"),
            ("speed", "말 속도"),
            ("emotion", "감정 강도"),
            ("power", "발성 힘"),
            ("distance", "거리감"),
        ]:
            row = QHBoxLayout()
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            value = QLabel("50")
            slider.valueChanged.connect(lambda v, lab=value: lab.setText(str(v)))
            row.addWidget(slider)
            row.addWidget(value)
            self.sliders[key] = slider
            form.addRow(title, row)

        self.direction = QTextEdit()
        self.direction.setPlaceholderText("예: 낮고 차분하지만 피로가 묻어남. 끝음을 과장하지 않음.")
        self.direction.setMaximumHeight(100)
        form.addRow("목소리 방향", self.direction)
        right.addLayout(form)

        save = QPushButton("이 설정을 캐릭터 기본값으로 저장")
        save.clicked.connect(self.save_profile)
        right.addWidget(save)

        for label, mode in [
            ("이 캐릭터 AI 음성 전체 끄기", "muted"),
            ("이 캐릭터를 친구 녹음 우선으로", "external"),
            ("이 캐릭터를 AI 성우로 복구", "ai"),
        ]:
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, m=mode: self._set_character_mode(m))
            right.addWidget(b)

        right.addStretch(1)
        export = QPushButton("현재 프로젝트 MP4 렌더")
        export.clicked.connect(self.export_video)
        right.addWidget(export)
        layout.addLayout(right, 1)

    def selected_line(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        line_id = self.table.item(rows[0].row(), 0).text()
        return next((x for x in self.project.dialogue if x.id == line_id), None)

    def source_text(self, line):
        profile = self.project.profile(line.character)
        mode = line.source_override or profile.mode
        if mode == "muted":
            return "음소거"
        if mode == "external":
            return "친구 녹음" if line.external_audio and (self.project_dir / line.external_audio).exists() else "친구 녹음 필요"
        return "AI" if line.ai_audio and (self.project_dir / line.ai_audio).exists() else "AI 생성 필요"

    def refresh_table(self):
        self.table.setRowCount(len(self.project.dialogue))
        for r, line in enumerate(self.project.dialogue):
            vals = [
                line.id,
                str(line.scene_id),
                line.character,
                line.text,
                self.source_text(line),
                "있음" if line.external_audio and (self.project_dir / line.external_audio).exists() else "-",
            ]
            for c, v in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(v))
        self.table.resizeColumnsToContents()

    def load_profile(self, name):
        if not name:
            return
        p = self.project.profile(name)
        self.mode.setCurrentText(p.mode)
        self.model.setCurrentText(p.model)
        self.voice.setText(p.voice_name)
        for k, slider in self.sliders.items():
            slider.setValue(getattr(p, k))
        self.direction.setPlainText(p.direction)

    def save_profile(self):
        name = self.character.currentText()
        p = self.project.profile(name)
        p.mode = self.mode.currentText()
        p.model = self.model.currentText()
        p.voice_name = self.voice.text().strip() or "Kore"
        for k, slider in self.sliders.items():
            setattr(p, k, slider.value())
        p.direction = self.direction.toPlainText().strip()
        self.project.save(self.project_path)
        self.refresh_table()

    def import_recording(self):
        line = self.selected_line()
        if not line:
            return QMessageBox.information(self, "선택", "대사를 먼저 선택하세요.")
        src, _ = QFileDialog.getOpenFileName(
            self, "친구 녹음 선택", "", "Audio (*.wav *.mp3 *.m4a *.aac *.flac)"
        )
        if not src:
            return
        dst = self.project_dir / (line.external_audio or f"media/audio/actors/{line.character}/{line.id}.wav")
        try:
            prepare_recording(src, dst)
        except Exception as e:
            return QMessageBox.critical(self, "오디오 처리 실패", str(e))
        line.external_audio = str(dst.relative_to(self.project_dir)).replace("\\", "/")
        line.source_override = "external"
        self.project.save(self.project_path)
        self.refresh_table()

    def generate_ai(self):
        line = self.selected_line()
        if not line:
            return QMessageBox.information(self, "선택", "대사를 먼저 선택하세요.")
        self.save_profile()
        p = self.project.profile(line.character)
        out = self.project_dir / (line.ai_audio or f"media/audio/ai/{line.character}/{line.id}.wav")
        try:
            GeminiTTS().generate(line, p, out)
        except Exception as e:
            return QMessageBox.critical(self, "TTS 실패", str(e))
        line.ai_audio = str(out.relative_to(self.project_dir)).replace("\\", "/")
        line.source_override = "ai"
        self.project.save(self.project_path)
        self.refresh_table()

    def mute_line(self):
        line = self.selected_line()
        if line:
            line.source_override = "muted"
            self.project.save(self.project_path)
            self.refresh_table()

    def restore_line(self):
        line = self.selected_line()
        if line:
            line.source_override = None
            self.project.save(self.project_path)
            self.refresh_table()

    def _set_character_mode(self, mode):
        p = self.project.profile(self.character.currentText())
        p.mode = mode
        self.project.save(self.project_path)
        self.load_profile(self.character.currentText())
        self.refresh_table()

    def on_line_selected(self):
        line = self.selected_line()
        if line and line.character != self.character.currentText():
            self.character.setCurrentText(line.character)

    def export_video(self):
        out, _ = QFileDialog.getSaveFileName(
            self,
            "MP4 저장",
            str(self.project_dir / "SASEOK_STUDIO_PREVIEW.mp4"),
            "MP4 (*.mp4)",
        )
        if not out:
            return
        try:
            render(self.project, self.project_dir, Path(out))
        except Exception as e:
            return QMessageBox.critical(self, "렌더 실패", str(e))
        QMessageBox.information(self, "완료", f"렌더 완료\n{out}")


def main():
    app = QApplication(sys.argv)
    if len(sys.argv) > 1:
        project = Path(sys.argv[1]).resolve()
    else:
        project = Path(__file__).resolve().parents[1] / "saseok_studio_project.json"
        if not project.exists():
            from bootstrap import build
            build(Path(__file__).resolve().parents[1], project)
    window = StudioWindow(project)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
