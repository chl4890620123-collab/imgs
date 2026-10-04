from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QCheckBox, QDoubleSpinBox, QGroupBox, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QSlider, QSpinBox, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from audio import prepare_recording
from gemini_tts import GeminiTTS
from project import StudioProject
from render import render
from generation_plan import build_plan, plan_text
from video_recipe import PRESETS, RecipeStore, apply_preset


class StudioWindow(QMainWindow):
    def __init__(self, project_path: Path):
        super().__init__()
        self.project_path = project_path
        self.project_dir = project_path.parent
        self.project = StudioProject.load(project_path)
        self.recipe_store = RecipeStore(self.project_dir / "saseok_video_recipes.json")
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

        video_box = QGroupBox("영상 생성 — 쉬운 모드")
        video_layout = QFormLayout(video_box)

        self.video_scene = QComboBox()
        for scene in self.project.scenes:
            self.video_scene.addItem(f"{scene.id:02d}. {scene.title}", scene.id)
        self.video_scene.currentIndexChanged.connect(self.load_video_recipe)
        video_layout.addRow("장면", self.video_scene)

        self.video_preset = QComboBox()
        for key in ("high", "fast", "cinematic"):
            self.video_preset.addItem(PRESETS[key]["label"], key)
        self.video_preset.currentIndexChanged.connect(self.apply_video_preset)
        video_layout.addRow("품질", self.video_preset)

        self.call_budget = QSpinBox()
        self.call_budget.setRange(1, 6)
        video_layout.addRow("AI 호출 예산/장면", self.call_budget)

        self.advanced_video = QGroupBox("고급 설정")
        self.advanced_video.setCheckable(True)
        self.advanced_video.setChecked(False)
        advanced = QFormLayout(self.advanced_video)

        self.video_backend = QComboBox()
        self.video_backend.addItems(["ltx-2b", "hunyuan15", "wan22", "framepack"])
        advanced.addRow("추론 엔진", self.video_backend)

        self.video_width = QSpinBox()
        self.video_width.setRange(320, 1920)
        self.video_width.setSingleStep(32)
        self.video_height = QSpinBox()
        self.video_height.setRange(192, 1080)
        self.video_height.setSingleStep(8)
        size_row = QHBoxLayout()
        size_row.addWidget(self.video_width)
        size_row.addWidget(QLabel("×"))
        size_row.addWidget(self.video_height)
        advanced.addRow("생성 해상도", size_row)

        self.video_duration = QDoubleSpinBox()
        self.video_duration.setRange(2.0, 20.0)
        self.video_duration.setSingleStep(0.5)
        self.video_duration.setSuffix("초")
        advanced.addRow("한 번 생성 길이", self.video_duration)

        self.video_steps = QSpinBox()
        self.video_steps.setRange(4, 50)
        advanced.addRow("추론 Steps", self.video_steps)

        self.video_guidance = QDoubleSpinBox()
        self.video_guidance.setRange(1.0, 12.0)
        self.video_guidance.setSingleStep(0.1)
        advanced.addRow("Guidance", self.video_guidance)

        self.video_seed = QSpinBox()
        self.video_seed.setRange(0, 2147483647)
        advanced.addRow("Seed", self.video_seed)

        self.motion_strength = QSlider(Qt.Horizontal)
        self.motion_strength.setRange(0, 100)
        advanced.addRow("동작 강도", self.motion_strength)

        self.character_lock = QSlider(Qt.Horizontal)
        self.character_lock.setRange(0, 100)
        advanced.addRow("캐릭터 일관성", self.character_lock)

        self.camera_prompt = QLineEdit()
        advanced.addRow("카메라 지시", self.camera_prompt)

        self.video_negative = QTextEdit()
        self.video_negative.setMaximumHeight(70)
        advanced.addRow("네거티브", self.video_negative)

        self.post_upscale = QCheckBox("로컬 업스케일")
        self.post_interpolation = QCheckBox("프레임 보간")
        post_row = QHBoxLayout()
        post_row.addWidget(self.post_upscale)
        post_row.addWidget(self.post_interpolation)
        advanced.addRow("후처리", post_row)

        video_layout.addRow(self.advanced_video)

        video_buttons = QHBoxLayout()
        save_video = QPushButton("영상 설정 저장")
        save_video.clicked.connect(self.save_video_recipe)
        video_buttons.addWidget(save_video)
        show_plan = QPushButton("호출 계획 보기")
        show_plan.clicked.connect(self.show_generation_plan)
        video_buttons.addWidget(show_plan)
        video_layout.addRow(video_buttons)

        right.addWidget(video_box)
        if self.video_scene.count():
            self.load_video_recipe()

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

    def _current_scene_id(self) -> int:
        value = self.video_scene.currentData()
        return int(value) if value is not None else 1

    def load_video_recipe(self):
        recipe = self.recipe_store.get(self._current_scene_id())
        idx = self.video_preset.findData(recipe.preset)
        if idx >= 0:
            self.video_preset.blockSignals(True)
            self.video_preset.setCurrentIndex(idx)
            self.video_preset.blockSignals(False)
        self.call_budget.setValue(recipe.call_budget)
        inf = recipe.inference
        self.video_backend.setCurrentText(inf.backend)
        self.video_width.setValue(inf.width)
        self.video_height.setValue(inf.height)
        self.video_duration.setValue(inf.duration_sec)
        self.video_steps.setValue(inf.steps)
        self.video_guidance.setValue(inf.guidance)
        self.video_seed.setValue(inf.seed)
        self.motion_strength.setValue(inf.motion_strength)
        self.character_lock.setValue(inf.character_lock)
        self.camera_prompt.setText(inf.camera_prompt)
        self.video_negative.setPlainText(inf.negative_prompt)
        self.post_upscale.setChecked(recipe.post.upscale)
        self.post_interpolation.setChecked(recipe.post.interpolation)

    def apply_video_preset(self):
        key = self.video_preset.currentData()
        if not key:
            return
        recipe = self.recipe_store.get(self._current_scene_id())
        apply_preset(recipe, str(key))
        self.load_video_recipe()

    def save_video_recipe(self):
        recipe = self.recipe_store.get(self._current_scene_id())
        recipe.preset = str(self.video_preset.currentData() or "high")
        recipe.call_budget = self.call_budget.value()
        inf = recipe.inference
        inf.backend = self.video_backend.currentText()
        inf.width = self.video_width.value()
        inf.height = self.video_height.value()
        inf.duration_sec = self.video_duration.value()
        inf.steps = self.video_steps.value()
        inf.guidance = self.video_guidance.value()
        inf.seed = self.video_seed.value()
        inf.motion_strength = self.motion_strength.value()
        inf.character_lock = self.character_lock.value()
        inf.camera_prompt = self.camera_prompt.text().strip()
        inf.negative_prompt = self.video_negative.toPlainText().strip()
        recipe.post.upscale = self.post_upscale.isChecked()
        recipe.post.interpolation = self.post_interpolation.isChecked()
        self.recipe_store.save()

    def show_generation_plan(self):
        self.save_video_recipe()
        plan = build_plan(self.project, self.project_dir, self.recipe_store)
        QMessageBox.information(self, "AI 영상 호출 계획", plan_text(plan))

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
