"""Bridge pipeline input() calls into the Gradio hub UI."""

from __future__ import annotations

import builtins
import queue
import threading
from typing import Callable


class InputBridge:
    """Replace builtins.input so pipeline prompts wait for UI answers."""

    def __init__(self, timeout_seconds: float = 3600.0) -> None:
        self._prompt_queue: queue.Queue[str] = queue.Queue()
        self._answer_queue: queue.Queue[str] = queue.Queue()
        self._timeout = timeout_seconds
        self._lock = threading.Lock()
        self._active = False
        self._original_input: Callable[..., str] | None = None
        self._current_prompt: str | None = None

    @property
    def current_prompt(self) -> str | None:
        return self._current_prompt

    def install(self) -> None:
        with self._lock:
            if self._active:
                return
            self._original_input = builtins.input
            builtins.input = self._bridged_input  # type: ignore[assignment]
            self._active = True

    def uninstall(self) -> None:
        with self._lock:
            if not self._active:
                return
            if self._original_input is not None:
                builtins.input = self._original_input  # type: ignore[assignment]
            self._original_input = None
            self._active = False
            self._current_prompt = None
            self._drain(self._prompt_queue)
            self._drain(self._answer_queue)

    def _bridged_input(self, prompt: object = "") -> str:
        text = "" if prompt is None else str(prompt)
        self._current_prompt = text
        self._prompt_queue.put(text)
        try:
            answer = self._answer_queue.get(timeout=self._timeout)
        except queue.Empty as exc:
            self._current_prompt = None
            raise TimeoutError(
                f"Timed out waiting for hub answer to prompt: {text!r}"
            ) from exc
        self._current_prompt = None
        return answer

    def pop_prompt(self, block: bool = False, timeout: float = 0.05) -> str | None:
        try:
            if block:
                return self._prompt_queue.get(timeout=timeout)
            return self._prompt_queue.get_nowait()
        except queue.Empty:
            return None

    def submit_answer(self, answer: str) -> None:
        self._answer_queue.put(answer)

    @staticmethod
    def _drain(q: queue.Queue[str]) -> None:
        while True:
            try:
                q.get_nowait()
            except queue.Empty:
                break
