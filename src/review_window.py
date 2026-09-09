"""Local session review dashboard."""

from __future__ import annotations

import html
from pathlib import Path
from typing import cast

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from src.app_logging import export_troubleshooting_bundle
from src.interview_plan import InterviewQuestion, QuestionBank
from src.session_repository import SessionRepository, SessionSummary


class ReviewWindow(QDialog):
    def __init__(
        self,
        repository: SessionRepository | None = None,
        *,
        question_bank: QuestionBank | None = None,
        retention_days: int = 0,
        redact_exports: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.repository = repository or SessionRepository()
        self.question_bank = question_bank or QuestionBank()
        self._sessions: list[SessionSummary] = []
        self._entries: list[dict] = []
        self._visible_entries: list[dict] = []
        self.setWindowTitle("Practice Review")
        self.resize(1050, 720)

        self.session_list = QListWidget()
        self.session_list.currentRowChanged.connect(self._select_session)
        self.category_filter = QComboBox()
        self.category_filter.addItem("All categories", None)
        for category in (
            "recruiter",
            "behavioral",
            "technical",
            "coding",
            "system_design",
            "general",
        ):
            self.category_filter.addItem(category.replace("_", " ").title(), category)
        self.category_filter.currentIndexChanged.connect(self._apply_filter)
        self.difficulty_filter = QComboBox()
        self.difficulty_filter.addItem("All difficulties", None)
        for difficulty in ("introductory", "intermediate", "advanced"):
            self.difficulty_filter.addItem(difficulty.title(), difficulty)
        self.difficulty_filter.currentIndexChanged.connect(self._apply_filter)
        self.attempt_list = QListWidget()
        self.attempt_list.currentRowChanged.connect(self._render_entry)
        self.bank_list = QListWidget()
        self.bank_question = QLineEdit()
        self.bank_question.setPlaceholderText("Question bank question")
        self.bank_category = QComboBox()
        for category in ("recruiter", "behavioral", "technical", "coding", "system_design"):
            self.bank_category.addItem(category.replace("_", " ").title(), category)
        self.bank_difficulty = QComboBox()
        for difficulty in ("introductory", "intermediate", "advanced"):
            self.bank_difficulty.addItem(difficulty.title(), difficulty)
        self.bank_status = QComboBox()
        for status in ("new", "practicing", "mastered"):
            self.bank_status.addItem(status.title(), status)
        add_bank = QPushButton("Add / Update")
        add_bank.clicked.connect(self._save_bank_question)
        remove_bank = QPushButton("Remove")
        remove_bank.clicked.connect(self._remove_bank_question)
        self.bank_list.currentRowChanged.connect(self._load_bank_question)
        self.detail = QTextBrowser()
        self.metrics = QLabel("Select a session to review progress.")
        self.metrics.setWordWrap(True)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Sessions"))
        left_layout.addWidget(self.session_list)
        left_layout.addWidget(self.category_filter)
        left_layout.addWidget(self.difficulty_filter)
        left_layout.addWidget(QLabel("Questions and attempts"))
        left_layout.addWidget(self.attempt_list)
        left_layout.addWidget(QLabel("Reusable question bank"))
        left_layout.addWidget(self.bank_list)
        left_layout.addWidget(self.bank_question)
        left_layout.addWidget(self.bank_category)
        left_layout.addWidget(self.bank_difficulty)
        left_layout.addWidget(self.bank_status)
        bank_buttons = QHBoxLayout()
        bank_buttons.addWidget(add_bank)
        bank_buttons.addWidget(remove_bank)
        left_layout.addLayout(bank_buttons)

        self.mark_checkbox = QCheckBox("Mark for future practice")
        self.note_edit = QPlainTextEdit()
        self.note_edit.setPlaceholderText("Personal notes…")
        self.note_edit.setMaximumHeight(85)
        save_note = QPushButton("Save Note")
        save_note.clicked.connect(self._save_note)
        export_md = QPushButton("Export Markdown")
        export_md.clicked.connect(lambda: self._export("md"))
        export_pdf = QPushButton("Export PDF")
        export_pdf.clicked.connect(lambda: self._export("pdf"))
        export_diagnostics = QPushButton("Troubleshooting Bundle")
        export_diagnostics.clicked.connect(self._export_diagnostics)
        self.redact_checkbox = QCheckBox("Redact email, phone and profile links")
        self.redact_checkbox.setChecked(redact_exports)
        delete_session = QPushButton("Delete Session")
        delete_session.clicked.connect(self._delete_session)
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(0, 3650)
        self.retention_spin.setValue(retention_days)
        self.retention_spin.setSpecialValueText("Keep forever")
        self.retention_spin.setSuffix(" days")
        cleanup = QPushButton("Run Cleanup")
        cleanup.clicked.connect(self._cleanup)
        delete_all = QPushButton("Delete All Practice Data")
        delete_all.clicked.connect(self._delete_all)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.metrics)
        right_layout.addWidget(self.detail, 1)
        right_layout.addWidget(self.mark_checkbox)
        right_layout.addWidget(self.note_edit)
        note_row = QHBoxLayout()
        note_row.addWidget(save_note)
        note_row.addStretch()
        right_layout.addLayout(note_row)
        export_row = QHBoxLayout()
        export_row.addWidget(export_md)
        export_row.addWidget(export_pdf)
        export_row.addWidget(export_diagnostics)
        export_row.addWidget(self.redact_checkbox)
        export_row.addStretch()
        right_layout.addLayout(export_row)
        privacy_row = QHBoxLayout()
        privacy_row.addWidget(QLabel("Auto-delete after"))
        privacy_row.addWidget(self.retention_spin)
        privacy_row.addWidget(cleanup)
        privacy_row.addStretch()
        privacy_row.addWidget(delete_session)
        privacy_row.addWidget(delete_all)
        right_layout.addLayout(privacy_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([330, 720])
        layout = QVBoxLayout(self)
        title = QLabel("Session Review Dashboard")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        local = QLabel("All review, exports, notes, and cleanup happen locally on this Mac.")
        layout.addWidget(title)
        layout.addWidget(local)
        layout.addWidget(splitter)
        self.refresh()
        self._refresh_bank()

    def refresh(self) -> None:
        self._sessions = self.repository.list_sessions()
        self.session_list.clear()
        for session in self._sessions:
            profile = session.profile or "default"
            score = "—" if session.average_score is None else f"{session.average_score:.1f}/5"
            self.session_list.addItem(
                f"{session.started_at[:16].replace('T', ' ')} · {profile}\n"
                f"{session.questions} questions · {session.attempts} attempts · {score}"
            )
        if self._sessions:
            self.session_list.setCurrentRow(0)

    def _select_session(self, row: int) -> None:
        if not 0 <= row < len(self._sessions):
            self._entries = []
            self._apply_filter()
            return
        self._entries = self.repository.read(self._sessions[row].path)
        data = self.repository.metrics(self._entries)
        summary, recommendations = self.repository.end_summary(self._entries)
        weaknesses = cast(list[tuple[str, float]], data["weaknesses"])
        weak = (
            ", ".join(f"{name.replace('_', ' ')} {score}/5" for name, score in weaknesses)
            or "not enough data"
        )
        star_notes = []
        overused = cast(list[str], data["overused_star_prompts"])
        underdeveloped = cast(list[str], data["underdeveloped_star_prompts"])
        if overused:
            star_notes.append(f"Overused STAR prompts: {len(overused)}.")
        if underdeveloped:
            star_notes.append(f"Underdeveloped STAR prompts: {len(underdeveloped)}.")
        self.metrics.setText(
            f"{summary} Fillers/min: {data['filler_words_per_minute']}. "
            f"Weakest: {weak}. {' '.join(star_notes)} "
            f"Next: {' '.join(recommendations)}"
        )
        self._apply_filter()

    def _apply_filter(self) -> None:
        category = self.category_filter.currentData()
        difficulty = self.difficulty_filter.currentData()
        self._visible_entries = [
            item
            for item in self._entries
            if item.get("question")
            and (
                category is None
                or item.get("category") == category
                or item.get("feedback", {}).get("question_type") == category
            )
            and (difficulty is None or item.get("difficulty") == difficulty)
        ]
        self.attempt_list.clear()
        for item in self._visible_entries:
            suffix = (
                f" · attempt {item.get('attempt_number')}"
                if item.get("type") == "candidate_attempt"
                else " · coached"
            )
            self.attempt_list.addItem(str(item["question"]) + suffix)
        if self._visible_entries:
            self.attempt_list.setCurrentRow(0)
        else:
            self.detail.clear()

    def _render_entry(self, row: int) -> None:
        if not 0 <= row < len(self._visible_entries):
            return
        item = self._visible_entries[row]
        feedback = item.get("feedback", {})
        scores = " · ".join(
            f"{name.replace('_', ' ')} {value}/5"
            for name, value in feedback.get("scores", {}).items()
            if value is not None
        )
        improvements = "".join(
            f"<li>{html.escape(str(value))}</li>" for value in feedback.get("improvements", [])
        )
        self.detail.setHtml(
            f"<h2>{html.escape(str(item['question']))}</h2>"
            f"<h3>Coached answer</h3><p>{_html(item.get('answer', '—'))}</p>"
            f"<h3>Candidate response</h3><p>{_html(item.get('candidate_transcript', '—'))}</p>"
            f"<p><b>Scores:</b> {html.escape(scores or '—')}</p>"
            f"<h3>Improvements</h3><ol>{improvements}</ol>"
            f"<h3>Improved answer</h3><p>{_html(feedback.get('improved_answer', '—'))}</p>"
            f"<p><b>Attempt comparison:</b> {_html((item.get('comparison') or {}).get('summary', 'First attempt or not available.'))}</p>"
        )
        metadata = (
            self.repository.metadata().get("questions", {}).get(_key(str(item["question"])), {})
        )
        self.mark_checkbox.setChecked(bool(metadata.get("marked")))
        self.note_edit.setPlainText(str(metadata.get("note", "")))

    def _save_note(self) -> None:
        item = self._current_entry()
        if item:
            self.repository.update_question(
                str(item["question"]),
                note=self.note_edit.toPlainText(),
                marked=self.mark_checkbox.isChecked(),
            )

    def _export(self, extension: str) -> None:
        session = self._current_session()
        if session is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Practice Session",
            f"{session.session_id}.{extension}",
            f"{extension.upper()} (*.{extension})",
        )
        if not filename:
            return
        if extension == "pdf":
            self.repository.export_pdf(
                session.path, Path(filename), redact=self.redact_checkbox.isChecked()
            )
        else:
            self.repository.export_markdown(
                session.path, Path(filename), redact=self.redact_checkbox.isChecked()
            )

    def _delete_session(self) -> None:
        session = self._current_session()
        if (
            session
            and QMessageBox.question(
                self, "Delete session?", "Permanently delete this session and its retained audio?"
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.repository.delete_session(session.path)
            self.refresh()

    def _export_diagnostics(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Troubleshooting Bundle",
            "interview-helper-diagnostics.zip",
            "ZIP (*.zip)",
        )
        if filename:
            export_troubleshooting_bundle(Path(filename))

    def _cleanup(self) -> None:
        self.repository.cleanup(self.retention_spin.value())
        self.refresh()

    def _delete_all(self) -> None:
        if (
            QMessageBox.warning(
                self,
                "Delete all practice data?",
                "This permanently deletes every session, retained candidate recording, note, and marker.",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.repository.delete_all()
            self.refresh()

    def _refresh_bank(self) -> None:
        self._bank_items = self.question_bank.load()
        self.bank_list.clear()
        for item in self._bank_items:
            self.bank_list.addItem(
                f"{item.get('text', '')}\n{item.get('category', 'general')} · "
                f"{item.get('difficulty', 'intermediate')} · {item.get('status', 'new')}"
            )

    def _load_bank_question(self, row: int) -> None:
        if not 0 <= row < len(getattr(self, "_bank_items", [])):
            return
        item = self._bank_items[row]
        self.bank_question.setText(str(item.get("text", "")))
        for combo, key in (
            (self.bank_category, "category"),
            (self.bank_difficulty, "difficulty"),
            (self.bank_status, "status"),
        ):
            index = combo.findData(item.get(key))
            combo.setCurrentIndex(max(0, index))

    def _save_bank_question(self) -> None:
        text = self.bank_question.text().strip()
        if not text:
            return
        row = self.bank_list.currentRow()
        values = {
            "text": text,
            "category": self.bank_category.currentData(),
            "difficulty": self.bank_difficulty.currentData(),
            "topic": self.bank_category.currentData().replace("_", " "),
            "status": self.bank_status.currentData(),
        }
        if 0 <= row < len(getattr(self, "_bank_items", [])):
            self.question_bank.update(self._bank_items[row]["id"], **values)
        else:
            self.question_bank.add(
                InterviewQuestion(
                    text,
                    values["category"],
                    values["difficulty"],
                    values["topic"],
                    "manual",
                ),
                status=values["status"],
            )
        self._refresh_bank()

    def _remove_bank_question(self) -> None:
        row = self.bank_list.currentRow()
        if 0 <= row < len(getattr(self, "_bank_items", [])):
            self.question_bank.delete(self._bank_items[row]["id"])
            self.bank_question.clear()
            self._refresh_bank()

    def _current_session(self):
        row = self.session_list.currentRow()
        return self._sessions[row] if 0 <= row < len(self._sessions) else None

    def _current_entry(self):
        row = self.attempt_list.currentRow()
        return self._visible_entries[row] if 0 <= row < len(self._visible_entries) else None


def _html(value: object) -> str:
    return html.escape(str(value)).replace("\n", "<br>")


def _key(question: str) -> str:
    return " ".join(__import__("re").findall(r"\w+", question.casefold()))
