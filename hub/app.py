"""Gradio UI for the RMT pipeline hub."""

from __future__ import annotations

import time
from typing import Any

import gradio as gr

from hub.registry import get_flow_config, list_flows, list_shippers
from hub.runner import PipelineRunner

_runner = PipelineRunner()

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=Newsreader:opsz,wght@6..72,500;6..72,600&display=swap');

:root {
  --ink: #14212b;
  --muted: #5b6b78;
  --line: #d7e0e7;
  --paper: #f3f6f8;
  --panel: #ffffff;
  --accent: #0f6e56;
  --accent-deep: #0b5341;
  --warn: #9a3412;
  --ok: #0f6e56;
}

.gradio-container {
  max-width: 880px !important;
  margin: 0 auto !important;
  font-family: "Instrument Sans", sans-serif !important;
  color: var(--ink) !important;
  background:
    radial-gradient(1200px 500px at 10% -10%, #dce9ef 0%, transparent 55%),
    radial-gradient(900px 420px at 100% 0%, #e4efe9 0%, transparent 50%),
    var(--paper) !important;
}

footer, .svelte-1ipelgc { display: none !important; }

#hub-shell {
  padding: 1.5rem 0 2.5rem;
}

#brand {
  font-family: "Newsreader", Georgia, serif !important;
  font-size: 2.35rem !important;
  font-weight: 600 !important;
  letter-spacing: -0.02em !important;
  line-height: 1.1 !important;
  margin: 0 0 0.35rem !important;
  color: var(--ink) !important;
}

#tagline {
  color: var(--muted) !important;
  font-size: 0.98rem !important;
  margin: 0 0 1.4rem !important;
}

#controls {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 1rem 1rem 0.85rem;
  box-shadow: 0 10px 30px rgba(20, 33, 43, 0.04);
}

#start-btn {
  background: var(--accent) !important;
  border: none !important;
  color: #fff !important;
  font-weight: 600 !important;
  min-height: 44px;
}
#start-btn:hover {
  background: var(--accent-deep) !important;
}

#status-chip textarea {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  color: var(--muted) !important;
  font-size: 0.92rem !important;
  padding-top: 0.55rem !important;
}

#ask-panel {
  margin-top: 1rem;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 1rem;
}

#question-box textarea {
  font-family: ui-monospace, "Cascadia Mono", Menlo, monospace !important;
  font-size: 0.86rem !important;
  line-height: 1.45 !important;
  background: #f7fafb !important;
  border: 1px solid var(--line) !important;
  min-height: 140px !important;
}

#answer-box textarea {
  border: 1px solid var(--line) !important;
  min-height: 52px !important;
}

#submit-btn {
  background: var(--ink) !important;
  color: #fff !important;
  border: none !important;
  font-weight: 600 !important;
}

#result-panel {
  margin-top: 1rem;
  background: #ecf6f1;
  border: 1px solid #c7e4d7;
  border-radius: 14px;
  padding: 1rem;
}

#result-panel textarea {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  font-family: ui-monospace, "Cascadia Mono", Menlo, monospace !important;
  font-size: 0.88rem !important;
  color: var(--accent-deep) !important;
}

#activity details {
  margin-top: 1rem;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 0.35rem 0.85rem 0.85rem;
}

#activity summary {
  cursor: pointer;
  color: var(--muted);
  font-size: 0.9rem;
  padding: 0.55rem 0.15rem;
}

#activity textarea {
  font-family: ui-monospace, "Cascadia Mono", Menlo, monospace !important;
  font-size: 0.8rem !important;
  background: #f7fafb !important;
  border: 1px solid var(--line) !important;
  color: var(--muted) !important;
}
"""


def _flows_for_shipper(shipper: str) -> list[str]:
    if not shipper:
        return []
    try:
        return list_flows(shipper)
    except KeyError:
        return []


def on_shipper_change(shipper: str) -> dict[str, Any]:
    flows = _flows_for_shipper(shipper)
    value = flows[0] if flows else None
    return gr.update(choices=flows, value=value)


def _status_label(snap: dict) -> str:
    status = snap["status"]
    if status == "idle":
        return "Ready"
    if status == "preparing":
        return "Preparing…"
    if status == "running":
        return "Running…"
    if status == "waiting_input":
        return "Your turn — answer below"
    if status == "done":
        return "Done"
    if status == "error":
        return f"Failed — {snap.get('error') or 'see activity'}"
    return status


def _format_results(snap: dict) -> str:
    paths = snap.get("result_paths") or []
    if paths:
        return "\n".join(paths)
    if snap.get("status") == "error" and snap.get("error"):
        return snap["error"]
    if snap.get("status") == "done":
        return "No result path detected"
    return ""


def _pack(snap: dict) -> tuple[str, str, str, str]:
    return (
        snap["log"],
        snap["pending_prompt"] or "",
        _format_results(snap),
        _status_label(snap),
    )


def start_run(
    shipper: str,
    flow: str,
    update_repo: bool = False,
) -> tuple[str, str, str, str]:
    if _runner.is_busy():
        return _pack(_runner.state.snapshot())
    if not shipper or not flow:
        return "", "", "", "Choose shipper and flow"
    try:
        config = get_flow_config(shipper, flow)
        _runner.start(config, update_repo=bool(update_repo))
    except (KeyError, RuntimeError) as exc:
        return "", "", "", str(exc)
    return _pack(_runner.state.snapshot())


def submit_answer(answer: str) -> tuple[str, str, str, str]:
    snap = _runner.state.snapshot()
    if snap["status"] != "waiting_input":
        return _pack(snap)
    _runner.submit_answer(answer or "")
    time.sleep(0.12)
    return _pack(_runner.state.snapshot())


def poll_state() -> tuple[str, str, str, str]:
    return _pack(_runner.state.snapshot())


def build_app() -> gr.Blocks:
    shippers = list_shippers()
    default_shipper = shippers[0] if shippers else None
    default_flows = _flows_for_shipper(default_shipper) if default_shipper else []
    default_flow = default_flows[0] if default_flows else None

    theme = gr.themes.Soft(
        primary_hue=gr.themes.Color(
            c50="#ecf6f1",
            c100="#d5eee3",
            c200="#a9dcc7",
            c300="#74c4a6",
            c400="#3fa882",
            c500="#0f6e56",
            c600="#0b5341",
            c700="#084032",
            c800="#063126",
            c900="#04231b",
            c950="#02150f",
        ),
        neutral_hue="slate",
        font=gr.themes.GoogleFont("Instrument Sans"),
        font_mono=gr.themes.GoogleFont("IBM Plex Mono"),
    ).set(
        body_background_fill="#f3f6f8",
        block_background_fill="#ffffff",
        block_border_color="#d7e0e7",
        block_label_text_color="#5b6b78",
        button_primary_background_fill="#0f6e56",
        button_primary_background_fill_hover="#0b5341",
        button_primary_text_color="#ffffff",
    )

    with gr.Blocks(title="RMT Hub") as demo:
        with gr.Column(elem_id="hub-shell"):
            gr.HTML('<div id="brand">RMT Hub</div>')
            gr.HTML(
                '<p id="tagline">Pick a shipper and flow, start, then answer '
                "questions here.</p>"
            )

            with gr.Group(elem_id="controls"):
                with gr.Row():
                    shipper = gr.Dropdown(
                        label="Shipper",
                        choices=shippers,
                        value=default_shipper,
                        interactive=True,
                        scale=3,
                    )
                    flow = gr.Dropdown(
                        label="Flow",
                        choices=default_flows,
                        value=default_flow,
                        interactive=True,
                        scale=2,
                    )
                    start_btn = gr.Button("Start", elem_id="start-btn", scale=1)
                with gr.Row():
                    update_repo = gr.Checkbox(
                        label="Update from GitHub before run",
                        value=False,
                        info="Off = faster start (uses local copy)",
                    )
                status = gr.Textbox(
                    label=None,
                    show_label=False,
                    value="Ready",
                    interactive=False,
                    elem_id="status-chip",
                    lines=1,
                    max_lines=1,
                )

            with gr.Group(elem_id="ask-panel"):
                prompt = gr.Textbox(
                    label="Question",
                    lines=8,
                    max_lines=16,
                    interactive=False,
                    elem_id="question-box",
                    placeholder="Questions from the pipeline appear here",
                )
                answer = gr.Textbox(
                    label="Answer",
                    lines=1,
                    max_lines=3,
                    elem_id="answer-box",
                    placeholder="Same answer you would type in Colab",
                )
                submit_btn = gr.Button("Submit", elem_id="submit-btn")

            with gr.Group(elem_id="result-panel"):
                results = gr.Textbox(
                    label="Result",
                    lines=2,
                    max_lines=4,
                    interactive=False,
                    placeholder="Result file path shows up when the run finishes",
                )

            with gr.Accordion("Activity", open=False, elem_id="activity"):
                log = gr.Textbox(
                    label=None,
                    show_label=False,
                    lines=10,
                    max_lines=18,
                    interactive=False,
                )

        shipper.change(fn=on_shipper_change, inputs=[shipper], outputs=[flow])
        start_btn.click(
            fn=start_run,
            inputs=[shipper, flow, update_repo],
            outputs=[log, prompt, results, status],
        )
        submit_btn.click(
            fn=submit_answer,
            inputs=[answer],
            outputs=[log, prompt, results, status],
        ).then(lambda: "", outputs=[answer])
        answer.submit(
            fn=submit_answer,
            inputs=[answer],
            outputs=[log, prompt, results, status],
        ).then(lambda: "", outputs=[answer])

        timer = gr.Timer(0.7)
        timer.tick(fn=poll_state, outputs=[log, prompt, results, status])

    # Gradio 6 expects theme/css on launch; keep them on the app object for launch().
    demo._hub_theme = theme  # type: ignore[attr-defined]
    demo._hub_css = _CSS  # type: ignore[attr-defined]
    return demo


def launch(share: bool = False, server_port: int | None = 7860) -> None:
    demo = build_app()
    demo.queue()
    demo.launch(
        share=share,
        server_port=server_port,
        inline=False,
        quiet=True,
        footer_links=[],
        theme=getattr(demo, "_hub_theme", None),
        css=getattr(demo, "_hub_css", None),
    )
