from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QProcess, QTimer
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
from prompt_engine import apply_plan, plan_instruction
from inference import available_backends
from performance import performance_plan_text
from ltx_runner import available as ltx_available, build_job, finalize_job
from remote_jobs import RemoteQueue, default_queue_root
from performance_report import report_text as colab_performance_report
from quality_review import regeneration_plan
from shortform.clipping import find_highlights
from shortform.pipeline import run_local_clipping_pipeline


class StudioWindow(QMainWindow):
    def __init__(self, project_path: Path):
        super().__init__()
        self.project_path = project_path
        self.project_dir = project_path.parent
        self.project = StudioProject.load(project_path)
        self.recipe_store = RecipeStore(self.project_dir / "saseok_video_recipes.json")
        self.remote_queue_path = default_queue_root(self.project_dir)
        self.setWindowTitle("Saseok Studio — 사석 제작 편집기")
        self.resize(1450, 850)
        self._build_ui()
        self.refresh_table()
        if self.character.count():
            self.load_profile(self.character.currentText())
        self.remote_timer = QTimer(self)
        self.remote_timer.setInterval(5000)
        self.remote_timer.timeout.connect(lambda: self.refresh_remote_queue(silent=True))
        self.remote_timer.start()
        self.refresh_remote_queue(silent=True)

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

        prompt_box = QGroupBox("감독 프롬프트")
        prompt_layout = QVBoxLayout(prompt_box)
        self.director_prompt = QTextEdit()
        self.director_prompt.setPlaceholderText(
            "예: 장면 9에서 리아가 더 빠르게 진우를 밀치고, 카메라는 낮은 각도로 따라가. "
            "캐릭터 일관성 90, 선명도 75, 1080p. 서진우는 친구 녹음으로."
        )
        self.director_prompt.setMaximumHeight(110)
        prompt_layout.addWidget(self.director_prompt)

        prompt_buttons = QHBoxLayout()
        preview_prompt = QPushButton("변경 미리보기")
        preview_prompt.clicked.connect(self.preview_director_prompt)
        prompt_buttons.addWidget(preview_prompt)
        apply_prompt = QPushButton("프롬프트 적용")
        apply_prompt.clicked.connect(self.apply_director_prompt)
        prompt_buttons.addWidget(apply_prompt)
        prompt_layout.addLayout(prompt_buttons)
        right.addWidget(prompt_box)

        video_box = QGroupBox("영상 생성 — 쉬운 모드")
        video_layout = QFormLayout(video_box)

        self.video_scene = QComboBox()
        for scene in self.project.scenes:
            self.video_scene.addItem(f"{scene.id:02d}. {scene.title}", scene.id)
        self.video_scene.currentIndexChanged.connect(self.load_video_recipe)
        self.video_scene.currentIndexChanged.connect(self.refresh_shot_combo)
        video_layout.addRow("장면", self.video_scene)

        self.video_shot = QComboBox()
        video_layout.addRow("컷", self.video_shot)

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
        self.video_backend.addItems([x.key for x in available_backends("KR")])
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

        motion_buttons = QHBoxLayout()
        performance = QPushButton("연기 타임라인 보기")
        performance.clicked.connect(self.show_performance_plan)
        motion_buttons.addWidget(performance)
        self.generate_shot_button = QPushButton("선택 컷 LTX 생성")
        self.generate_shot_button.clicked.connect(self.generate_selected_shot)
        motion_buttons.addWidget(self.generate_shot_button)
        video_layout.addRow(motion_buttons)

        remote_box = QGroupBox("Colab GPU 백그라운드")
        remote_layout = QFormLayout(remote_box)

        queue_row = QHBoxLayout()
        self.remote_queue_path_edit = QLineEdit(str(self.remote_queue_path))
        queue_row.addWidget(self.remote_queue_path_edit)
        choose_queue = QPushButton("폴더 선택")
        choose_queue.clicked.connect(self.choose_remote_queue_root)
        queue_row.addWidget(choose_queue)
        remote_layout.addRow("공유 큐 폴더", queue_row)

        self.remote_status_label = QLabel("워커 확인 중…")
        remote_layout.addRow("워커", self.remote_status_label)

        remote_buttons = QHBoxLayout()
        submit_remote = QPushButton("선택 컷 Colab 큐 등록")
        submit_remote.clicked.connect(self.submit_colab_shot)
        remote_buttons.addWidget(submit_remote)
        submit_scene = QPushButton("장면 우선 컷 일괄 등록")
        submit_scene.clicked.connect(self.submit_colab_scene)
        remote_buttons.addWidget(submit_scene)
        refresh_remote = QPushButton("상태 새로고침")
        refresh_remote.clicked.connect(lambda: self.refresh_remote_queue(silent=False))
        remote_buttons.addWidget(refresh_remote)
        remote_layout.addRow(remote_buttons)

        remote_quality = QHBoxLayout()
        regenerate = QPushButton("불량 컷만 재생성")
        regenerate.clicked.connect(self.submit_bad_shots)
        remote_quality.addWidget(regenerate)
        perf_report = QPushButton("성능 리포트")
        perf_report.clicked.connect(self.show_colab_performance)
        remote_quality.addWidget(perf_report)
        remote_layout.addRow(remote_quality)

        remote_manage = QHBoxLayout()
        retry_remote = QPushButton("실패 작업 재시도")
        retry_remote.clicked.connect(self.retry_remote_shot)
        remote_manage.addWidget(retry_remote)
        cancel_remote = QPushButton("원격 작업 취소")
        cancel_remote.clicked.connect(self.cancel_remote_shot)
        remote_manage.addWidget(cancel_remote)
        remote_layout.addRow(remote_manage)

        video_layout.addRow(remote_box)

        right.addWidget(video_box)
        if self.video_scene.count():
            self.refresh_shot_combo()
            self.load_video_recipe()

        shortform_box = QGroupBox("숏폼 공장 — 긴 영상 → 9:16")
        shortform_layout = QFormLayout(shortform_box)

        source_row = QHBoxLayout()
        self.shortform_source = QLineEdit()
        self.shortform_source.setPlaceholderText("긴 영상 MP4/MOV 파일 선택")
        source_row.addWidget(self.shortform_source)
        choose_shortform = QPushButton("영상 선택")
        choose_shortform.clicked.connect(self.choose_shortform_source)
        source_row.addWidget(choose_shortform)
        shortform_layout.addRow("원본 영상", source_row)

        self.shortform_count = QSpinBox()
        self.shortform_count.setRange(1, 10)
        self.shortform_count.setValue(3)
        shortform_layout.addRow("후보 개수", self.shortform_count)

        self.shortform_duration = QDoubleSpinBox()
        self.shortform_duration.setRange(6.0, 60.0)
        self.shortform_duration.setValue(30.0)
        self.shortform_duration.setSingleStep(1.0)
        self.shortform_duration.setSuffix("초")
        shortform_layout.addRow("숏폼 길이", self.shortform_duration)

        shortform_buttons = QHBoxLayout()
        analyze_shortform = QPushButton("후보 분석")
        analyze_shortform.clicked.connect(self.analyze_shortform_source)
        shortform_buttons.addWidget(analyze_shortform)
        render_shortform = QPushButton("9:16 MP4 만들기")
        render_shortform.clicked.connect(self.render_shortform_source)
        shortform_buttons.addWidget(render_shortform)
        shortform_layout.addRow(shortform_buttons)

        self.shortform_result = QTextEdit()
        self.shortform_result.setReadOnly(True)
        self.shortform_result.setMaximumHeight(130)
        self.shortform_result.setPlaceholderText(
            "유료 API 없이 scene-change + 발화 밀도로 후보를 찾습니다."
        )
        shortform_layout.addRow("결과", self.shortform_result)

        right.addWidget(shortform_box)

        right.addStretch(1)
        export = QPushButton("현재 프로젝트 MP4 렌더")
        export.clicked.connect(self.export_video)
        right.addWidget(export)
        layout.addLayout(right, 1)

    def choose_shortform_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "숏폼 원본 영상 선택",
            str(self.project_dir),
            "Video (*.mp4 *.mov *.mkv *.webm *.avi);;All files (*)",
        )
        if path:
            self.shortform_source.setText(path)

    def _shortform_source_path(self) -> Path:
        value = self.shortform_source.text().strip()
        if not value:
            raise ValueError("먼저 원본 영상을 선택하세요.")
        source = Path(value).expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(source)
        return source

    def analyze_shortform_source(self):
        try:
            source = self._shortform_source_path()
            highlights = find_highlights(
                source,
                num_highlights=self.shortform_count.value(),
                target_duration_sec=self.shortform_duration.value(),
            )
        except Exception as e:
            self.shortform_result.setPlainText(str(e))
            return QMessageBox.critical(self, "숏폼 분석 실패", str(e))

        lines = [
            "로컬 분석 완료 — 유료 API 호출 없음",
            f"원본: {source.name}",
            "",
        ]
        for i, item in enumerate(highlights, 1):
            lines.append(
                f"{i}. {item.start:.1f}s ~ {item.end:.1f}s "
                f"({item.duration:.1f}s) / 점수 {item.score:.2f}"
            )
        self.shortform_result.setPlainText("\n".join(lines))

    def render_shortform_source(self):
        try:
            source = self._shortform_source_path()
            output_dir = self.project_dir / "media" / "shorts" / source.stem
            result = run_local_clipping_pipeline(
                source,
                output_dir,
                num_highlights=self.shortform_count.value(),
                target_duration_sec=self.shortform_duration.value(),
                width=1080,
                height=1920,
                fps=30,
            )
        except Exception as e:
            self.shortform_result.setPlainText(str(e))
            return QMessageBox.critical(self, "숏폼 렌더 실패", str(e))

        lines = [
            f"완료: {result['count']}개",
            f"저장 폴더: {result['output_dir']}",
            "",
        ]
        for item in result["outputs"]:
            h = item["highlight"]
            lines.append(
                f"{item['index']}. {Path(item['file']).name} "
                f"({h['start']:.1f}s ~ {h['end']:.1f}s)"
            )
        self.shortform_result.setPlainText("\n".join(lines))
        QMessageBox.information(
            self,
            "숏폼 렌더 완료",
            f"{result['count']}개 생성 완료\n{result['output_dir']}",
        )

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

    def preview_director_prompt(self):
        text = self.director_prompt.toPlainText().strip()
        if not text:
            return QMessageBox.information(self, "감독 프롬프트", "지시 내용을 입력하세요.")
        plan = plan_instruction(text, self.project, current_scene_id=self._current_scene_id())
        QMessageBox.information(
            self,
            "변경 미리보기",
            plan.text() + "\n\n원문 지시는 장면 생성 프롬프트에 그대로 보존됩니다.",
        )

    def apply_director_prompt(self):
        text = self.director_prompt.toPlainText().strip()
        if not text:
            return QMessageBox.information(self, "감독 프롬프트", "지시 내용을 입력하세요.")
        plan = plan_instruction(text, self.project, current_scene_id=self._current_scene_id())
        changed = apply_plan(plan, self.project, self.project_path, self.recipe_store)
        self.refresh_table()
        self.load_video_recipe()
        QMessageBox.information(
            self,
            "프롬프트 적용 완료",
            ("\n".join(changed) if changed else "장면 생성 지시를 저장했습니다."),
        )

    def _current_scene_id(self) -> int:
        value = self.video_scene.currentData()
        return int(value) if value is not None else 1

    def refresh_shot_combo(self):
        self.video_shot.clear()
        icons = {
            "pending": "·",
            "queued": "◷",
            "generating": "▶",
            "ready": "✓",
            "failed": "!",
        }
        for shot in self.project.scene_shots(self._current_scene_id()):
            state = "ready" if shot.visual else shot.generation_status
            status = icons.get(state, "·")
            self.video_shot.addItem(
                f"{status} {shot.id}  {shot.start:.1f}-{shot.start + shot.duration:.1f}s",
                shot.id,
            )

    def _current_shot(self):
        shot_id = self.video_shot.currentData()
        if not shot_id:
            return None
        try:
            return self.project.shot(str(shot_id))
        except KeyError:
            return None

    def _remote_queue(self) -> RemoteQueue:
        value = self.remote_queue_path_edit.text().strip()
        if not value:
            raise ValueError("Colab 공유 큐 폴더를 선택하세요.")
        return RemoteQueue(Path(value))

    def choose_remote_queue_root(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Google Drive의 SASEOK_GPU_QUEUE 폴더 선택",
            self.remote_queue_path_edit.text().strip() or str(self.project_dir),
        )
        if folder:
            self.remote_queue_path_edit.setText(folder)
            self.refresh_remote_queue(silent=True)

    def submit_colab_shot(self):
        shot = self._current_shot()
        if shot is None:
            return QMessageBox.information(self, "컷 선택", "Colab으로 보낼 컷을 먼저 선택하세요.")
        self.save_video_recipe()
        recipe = self.recipe_store.get(shot.scene_id)
        if recipe.inference.backend != "ltx-2b":
            return QMessageBox.information(
                self,
                "Colab GPU",
                "현재 Colab 워커의 실제 실행 백엔드는 LTX-Video 2B입니다. 추론 엔진을 ltx-2b로 선택하세요.",
            )
        try:
            queue = self._remote_queue()
            job = queue.submit_shot(
                self.project,
                shot,
                recipe,
                self.project_dir,
            )
        except Exception as exc:
            return QMessageBox.critical(self, "Colab 작업 등록 실패", str(exc))

        shot.generation_status = "queued"
        self.project.save(self.project_path)
        self.refresh_shot_combo()
        self.refresh_remote_queue(silent=True)
        QMessageBox.information(
            self,
            "Colab GPU 큐 등록 완료",
            f"{shot.id}\n{job['job_id']}\n\nColab Worker 노트북이 실행 중이면 자동으로 가져갑니다.",
        )

    def submit_colab_scene(self):
        self.save_video_recipe()
        scene_id = self._current_scene_id()
        recipe = self.recipe_store.get(scene_id)
        if recipe.inference.backend != "ltx-2b":
            return QMessageBox.information(
                self,
                "Colab GPU",
                "현재 Colab 워커는 ltx-2b 장면만 일괄 등록합니다.",
            )
        try:
            queue = self._remote_queue()
            jobs = queue.submit_scene_priority(
                self.project,
                scene_id,
                recipe,
                self.project_dir,
            )
            for job in jobs:
                self.project.shot(job["shot_id"]).generation_status = "queued"
            self.project.save(self.project_path)
            self.refresh_shot_combo()
            self.refresh_remote_queue(silent=True)
            QMessageBox.information(
                self,
                "장면 Colab 등록",
                f"장면 {scene_id}에서 호출 예산 {recipe.call_budget} 기준 {len(jobs)}개 컷을 등록했습니다.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "장면 등록 실패", str(exc))

    def submit_bad_shots(self):
        self.save_video_recipe()
        scene_id = self._current_scene_id()
        recipe = self.recipe_store.get(scene_id)
        plan = regeneration_plan(self.project, scene_id, recipe)
        if not plan:
            return QMessageBox.information(
                self,
                "선택 재생성",
                "현재 품질 점수 기준으로 다시 생성할 컷이 없습니다.",
            )
        try:
            queue = self._remote_queue()
            jobs = []
            for item in plan:
                shot = self.project.shot(item.shot_id)
                latest = queue.latest_job_for_shot(shot.id)
                if latest and latest.get("status") in {"queued", "running"}:
                    continue
                jobs.append(queue.submit_shot(self.project, shot, recipe, self.project_dir))
                shot.generation_status = "queued"
            self.project.save(self.project_path)
            self.refresh_shot_combo()
            QMessageBox.information(
                self,
                "불량 컷 재생성",
                f"{len(jobs)}개 컷을 Colab 큐에 등록했습니다.\n"
                + "\n".join(f"{x.shot_id}: {x.reason}" for x in plan),
            )
        except Exception as exc:
            QMessageBox.critical(self, "재생성 등록 실패", str(exc))

    def show_colab_performance(self):
        try:
            queue = self._remote_queue()
            QMessageBox.information(
                self,
                "Colab GPU 성능 리포트",
                colab_performance_report(queue.list_jobs(["done", "failed"])),
            )
        except Exception as exc:
            QMessageBox.warning(self, "성능 리포트", str(exc))

    def refresh_remote_queue(self, silent: bool = True):
        try:
            queue = self._remote_queue()
            recovered = queue.recover_stale_running(timeout_seconds=300)
            synced = queue.sync_all_done(self.project, self.project_path)
            changed = bool(synced or recovered)
            for shot in self.project.shots:
                job = queue.latest_job_for_shot(shot.id)
                if not job:
                    continue
                mapping = {
                    "queued": "queued",
                    "running": "generating",
                    "done": "ready" if shot.visual else "generating",
                    "failed": "failed",
                    "cancelled": "pending",
                }
                next_state = mapping.get(job.get("status"), shot.generation_status)
                if next_state != shot.generation_status:
                    shot.generation_status = next_state
                    changed = True
            if changed:
                self.project.save(self.project_path)
                self.refresh_shot_combo()
            self.remote_status_label.setText(queue.worker_summary())
            if not silent:
                jobs = queue.list_jobs()
                active = sum(1 for x in jobs if x.get("status") in {"queued", "running"})
                done = sum(1 for x in jobs if x.get("status") == "done")
                failed = sum(1 for x in jobs if x.get("status") == "failed")
                QMessageBox.information(
                    self,
                    "Colab GPU 상태",
                    f"{queue.worker_summary()}\n대기/실행 {active} · 완료 {done} · 실패 {failed}\n"
                    f"자동 반영 {len(synced)}개 · 끊긴 작업 회수 {len(recovered)}개",
                )
        except Exception as exc:
            if hasattr(self, "remote_status_label"):
                self.remote_status_label.setText("Colab 큐 확인 실패")
            if not silent:
                QMessageBox.warning(self, "Colab GPU 상태", str(exc))

    def retry_remote_shot(self):
        shot = self._current_shot()
        if shot is None:
            return
        try:
            queue = self._remote_queue()
            job = queue.latest_job_for_shot(shot.id)
            if not job:
                raise ValueError("이 컷의 원격 작업이 없습니다.")
            queue.retry(job["job_id"])
            shot.generation_status = "queued"
            self.project.save(self.project_path)
            self.refresh_shot_combo()
        except Exception as exc:
            QMessageBox.warning(self, "재시도 실패", str(exc))

    def cancel_remote_shot(self):
        shot = self._current_shot()
        if shot is None:
            return
        try:
            queue = self._remote_queue()
            job = queue.latest_job_for_shot(shot.id)
            if not job:
                raise ValueError("이 컷의 원격 작업이 없습니다.")
            queue.cancel(job["job_id"])
            self.refresh_remote_queue(silent=True)
        except Exception as exc:
            QMessageBox.warning(self, "취소 실패", str(exc))

    def show_performance_plan(self):
        self.save_video_recipe()
        recipe = self.recipe_store.get(self._current_scene_id())
        text = performance_plan_text(self.project, self._current_scene_id(), recipe)
        QMessageBox.information(self, "연기 / 행동 타임라인", text or "계획이 없습니다.")

    def generate_selected_shot(self):
        shot = self._current_shot()
        if shot is None:
            return QMessageBox.information(self, "컷 선택", "생성할 컷을 먼저 선택하세요.")
        self.save_video_recipe()
        recipe = self.recipe_store.get(shot.scene_id)
        if recipe.inference.backend != "ltx-2b":
            return QMessageBox.information(
                self, "LTX 생성", "현재 직접 실행 연결은 LTX-Video 2B 백엔드에 연결되어 있습니다."
            )
        ok, detail = ltx_available()
        if not ok:
            return QMessageBox.information(
                self,
                "LTX 실행 준비 필요",
                detail + "\n\nLTX-Video를 설치한 뒤 LTX_VIDEO_HOME 환경변수를 저장소 경로로 설정하세요.",
            )
        try:
            job = build_job(self.project, shot, recipe, self.project_dir)
        except Exception as e:
            return QMessageBox.critical(self, "LTX 작업 생성 실패", str(e))

        shot.generation_status = "generating"
        self.project.save(self.project_path)
        self._active_ltx_job = job
        self._active_ltx_shot_id = shot.id

        self.ltx_process = QProcess(self)
        self.ltx_process.setWorkingDirectory(str(Path(detail)))
        self.ltx_process.finished.connect(self._on_ltx_finished)
        self.ltx_process.errorOccurred.connect(
            lambda _err: QMessageBox.critical(
                self, "LTX 실행 오류", self.ltx_process.errorString()
            )
        )
        self.generate_shot_button.setEnabled(False)
        self.generate_shot_button.setText("LTX 생성 중…")
        self.ltx_process.start(job.command[0], list(job.command[1:]))

    def _on_ltx_finished(self, exit_code, _exit_status):
        self.generate_shot_button.setEnabled(True)
        self.generate_shot_button.setText("선택 컷 LTX 생성")
        shot = self.project.shot(self._active_ltx_shot_id)
        if exit_code != 0:
            shot.generation_status = "failed"
            self.project.save(self.project_path)
            return QMessageBox.critical(
                self,
                "LTX 생성 실패",
                self.ltx_process.readAllStandardError().data().decode("utf-8", errors="replace")[-4000:],
            )
        try:
            out = finalize_job(self._active_ltx_job)
            shot.visual = str(out.relative_to(self.project_dir)).replace("\\", "/")
            shot.generation_status = "ready"
            shot.quality_score = None
            shot.quality_flags = []
            self.project.save(self.project_path)
            self.refresh_shot_combo()
            QMessageBox.information(self, "LTX 생성 완료", f"{shot.id}\n{out}")
        except Exception as e:
            shot.generation_status = "failed"
            self.project.save(self.project_path)
            QMessageBox.critical(self, "결과 처리 실패", str(e))

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
