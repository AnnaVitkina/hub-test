"""Clone/pull a pipeline repo and run its entry script with I/O bridged."""

from __future__ import annotations

import io
import re
import runpy
import subprocess
import sys
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from hub.input_bridge import InputBridge
from hub.registry import FlowConfig

CONTENT_ROOT = Path("/content")
RESULT_PATH_PATTERNS = (
    re.compile(r"(?i)rate card:\s*(.+)$"),
    re.compile(r"(?i)extracted data:\s*(.+)$"),
    re.compile(r"(?i)saved rates layout workbook:\s*(.+)$"),
    re.compile(r"(?i)saved processed workbook:\s*(.+)$"),
    re.compile(r"(?i)saved extracted data to:\s*(.+)$"),
)

# Noise that should not appear in the hub activity feed.
_NOISE_LINE = re.compile(
    r"(?x)"
    r"^\s*$"
    r"|^=+$"
    r"|^-+$"
    r"|^\s*\[0\]\s*Skip"
    r"|^\s*Enter\s+(number|comma|a\s+number)"
    r"|^\s*Press Enter to confirm"
    r"|^\s*Invalid choice"
    r"|^\s*Please enter y or n"
    r"|^\s*Already up to date\.?$"
    r"|^\s*From https://github\.com"
    r"|^\s*\d+\s+files? changed"
    r"|^\s*create mode "
    r"|^\s*delete mode "
    r"|^\s*Fast-forward"
    r"|^\s*Updating [0-9a-f]+\.\.[0-9a-f]+"
)


class _TeeStream(io.TextIOBase):
    """Mirror writes to the original stream and a capture buffer."""

    def __init__(
        self,
        original: io.TextIOBase,
        on_line: Callable[[str], None],
        buffer: io.StringIO,
    ) -> None:
        self._original = original
        self._on_line = on_line
        self._buffer = buffer
        self._pending = ""

    def write(self, s: str) -> int:  # type: ignore[override]
        if not s:
            return 0
        try:
            self._original.write(s)
        except Exception:  # noqa: BLE001
            pass
        self._buffer.write(s)
        self._pending += s
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            self._on_line(line)
        return len(s)

    def flush(self) -> None:
        try:
            self._original.flush()
        except Exception:  # noqa: BLE001
            pass
        if self._pending:
            self._on_line(self._pending)
            self._pending = ""


@dataclass
class RunState:
    status: str = "idle"  # idle | preparing | running | waiting_input | done | error
    log_lines: list[str] = field(default_factory=list)
    pending_prompt: str | None = None
    result_paths: list[str] = field(default_factory=list)
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    # Lines printed since the last answered prompt — used as question context.
    _context_lines: list[str] = field(default_factory=list)

    def note(self, line: str) -> None:
        """Quiet hub activity line (shown in the UI feed)."""
        text = line.strip()
        if not text:
            return
        with self.lock:
            self.log_lines.append(text)

    def on_pipeline_line(self, line: str) -> None:
        """Receive raw pipeline stdout/stderr one line at a time."""
        with self.lock:
            self._context_lines.append(line)
            if _is_notable_pipeline_line(line):
                self.log_lines.append(line.rstrip())

    def take_context(self) -> str:
        with self.lock:
            block = "\n".join(self._context_lines).strip()
            self._context_lines = []
            return block

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "status": self.status,
                "log": "\n".join(self.log_lines[-80:]),
                "pending_prompt": self.pending_prompt,
                "result_paths": list(self.result_paths),
                "error": self.error,
            }


def _is_notable_pipeline_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or _NOISE_LINE.match(stripped):
        return False
    # Skip numbered menu rows and bare option dumps — they belong in the question panel.
    if re.match(r"^\[\d+\]\s+", stripped):
        return False
    if re.match(r"^\d+\.\s+\S+", stripped):
        return False
    lower = stripped.lower()
    keep_prefixes = (
        "warning",
        "error",
        "cannot continue",
        "pipeline",
        "processing summary",
        "shipper:",
        "flow:",
        "variant:",
        "saved ",
        "rate card",
        "extracted data",
        "using workbook",
        "loading ",
        "removed ",
        "dataframe shape",
        "transforming",
        "nothing to process",
        "cancelled",
        "skipped",
    )
    return any(lower.startswith(p) or p in lower for p in keep_prefixes)


class PipelineRunner:
    def __init__(self, content_root: Path | None = None) -> None:
        self.content_root = content_root or (
            CONTENT_ROOT if CONTENT_ROOT.exists() else Path.cwd() / "_pipeline_repos"
        )
        self.state = RunState()
        self.bridge = InputBridge()
        self._thread: threading.Thread | None = None
        self._stop_poll = threading.Event()

    def is_busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, config: FlowConfig, *, update_repo: bool = False) -> None:
        if self.is_busy():
            raise RuntimeError("A pipeline is already running.")
        with self.state.lock:
            self.state.status = "preparing"
            self.state.log_lines = []
            self.state.pending_prompt = None
            self.state.result_paths = []
            self.state.error = None
            self.state._context_lines = []
        self._stop_poll.clear()
        self._thread = threading.Thread(
            target=self._run_job,
            args=(config, update_repo),
            daemon=True,
            name=f"pipeline-{config.shipper}-{config.flow}",
        )
        self._thread.start()

    def submit_answer(self, answer: str) -> None:
        answer = answer if answer is not None else ""
        with self.state.lock:
            self.state.pending_prompt = None
            if self.state.status == "waiting_input":
                self.state.status = "running"
        display = answer if answer.strip() else "(Enter)"
        self.state.note(f"→ {display}")
        self.bridge.submit_answer(answer)

    def _set_status(self, status: str, error: str | None = None) -> None:
        with self.state.lock:
            self.state.status = status
            if error is not None:
                self.state.error = error

    def _run_job(self, config: FlowConfig, update_repo: bool = False) -> None:
        poller = threading.Thread(target=self._poll_prompts, daemon=True)
        poller.start()
        full_log = io.StringIO()
        try:
            repo_path = self._ensure_repo(config, update_repo=update_repo)
            entry_path = repo_path / config.entry_script
            if not entry_path.exists():
                raise FileNotFoundError(f"Entry script not found: {entry_path}")

            self._set_status("running")
            self.state.note(f"Running {config.shipper} · {config.flow}")

            if str(repo_path) not in sys.path:
                sys.path.insert(0, str(repo_path))

            self.bridge.install()
            old_stdout, old_stderr = sys.stdout, sys.stderr
            sys.stdout = _TeeStream(old_stdout, self.state.on_pipeline_line, full_log)  # type: ignore[assignment]
            sys.stderr = _TeeStream(old_stderr, self.state.on_pipeline_line, full_log)  # type: ignore[assignment]
            exit_code = 0
            try:
                runpy.run_path(str(entry_path), run_name="__main__")
            except SystemExit as exc:
                code = exc.code
                if code is None:
                    exit_code = 0
                elif isinstance(code, int):
                    exit_code = code
                else:
                    exit_code = 1
                    self.state.note(str(code))
            finally:
                sys.stdout.flush()
                sys.stderr.flush()
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                self.bridge.uninstall()

            paths = extract_result_paths(full_log.getvalue())
            with self.state.lock:
                self.state.result_paths = paths
            if exit_code != 0:
                self._set_status("error", error=f"Exited with code {exit_code}")
                self.state.note(f"Failed (exit {exit_code})")
            else:
                self._set_status("done")
                self.state.note("Finished")
        except Exception as exc:  # noqa: BLE001
            # Keep errors short in the feed; full traceback only in internal capture.
            full_log.write(traceback.format_exc())
            self.state.note(f"Error: {exc}")
            self._set_status("error", error=str(exc))
        finally:
            self._stop_poll.set()
            self.bridge.uninstall()

    def _poll_prompts(self) -> None:
        while not self._stop_poll.is_set():
            prompt = self.bridge.pop_prompt(block=True, timeout=0.2)
            if prompt is None:
                continue
            context = self.state.take_context()
            prompt_text = (prompt or "").strip()
            if context and prompt_text:
                display = f"{context}\n{prompt_text}"
            else:
                display = context or prompt_text or "Waiting for input…"
            with self.state.lock:
                self.state.pending_prompt = display
                self.state.status = "waiting_input"

    def _ensure_repo(self, config: FlowConfig, *, update_repo: bool = False) -> Path:
        self.content_root.mkdir(parents=True, exist_ok=True)
        repo_path = self.content_root / config.clone_dir
        if not repo_path.exists():
            self.state.note("Downloading repository…")
            subprocess.run(
                ["git", "clone", "--depth", "1", "--quiet", config.repo_url, str(repo_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            return repo_path

        # Skip network pull by default — this was the main Start delay.
        if not update_repo:
            return repo_path

        self.state.note("Updating repository…")
        result = subprocess.run(
            ["git", "pull", "--ff-only", "--quiet"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "git pull failed").strip()
            short = message.splitlines()[-1] if message else "git pull failed"
            self.state.note(f"Update warning: {short}")
        return repo_path


_LABEL_ONLY = re.compile(
    r"(?i)^(rate card|extracted data|saved rates layout workbook|"
    r"saved processed workbook|saved extracted data to)\s*:?\s*$"
)


def extract_result_paths(log_text: str) -> list[str]:
    found: list[str] = []
    lines = log_text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        for pattern in RESULT_PATH_PATTERNS:
            match = pattern.search(stripped)
            if not match:
                continue
            path = match.group(1).strip()
            if path and path not in found:
                found.append(path)

        if _LABEL_ONLY.match(stripped) and index + 1 < len(lines):
            nxt = lines[index + 1].strip()
            if nxt and nxt not in found:
                found.append(nxt)

    if found:
        return found

    fallback = re.compile(
        r"((?:/content/[^\s]+|/mnt/[^\s]+|[A-Za-z]:\\[^\s]+)\.(?:xlsx|xlsm|xlsb|xls|csv))",
        re.IGNORECASE,
    )
    for match in fallback.finditer(log_text):
        path = match.group(1).strip().rstrip(".,;")
        if path not in found:
            found.append(path)
    return found
