"""System-wide switches. Currently one: whether AI may act."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.db import SystemStateRow

_AI_ENABLED = "ai_enabled"


class SystemState:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ai_enabled(self) -> bool:
        row = self._session.get(SystemStateRow, _AI_ENABLED)
        return row is None or row.value == "true"

    def set_ai_enabled(self, enabled: bool) -> None:
        row = self._session.get(SystemStateRow, _AI_ENABLED)
        value = "true" if enabled else "false"
        if row is None:
            self._session.add(SystemStateRow(key=_AI_ENABLED, value=value))
        else:
            row.value = value
        self._session.flush()
