import base64
import csv
import datetime as dt
import math
import asyncio
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

import flet as ft


SIMULATION_DURATION_S = 30.0
TICK_S = 0.5
APP_DIR = Path(__file__).resolve().parent
OUTPUT_CSV = APP_DIR / "results" / "simulated_emi_session.csv"


@dataclass(frozen=True)
class ReportPoint:
    time_s: float
    label: str
    distance_cm: float
    b_uT: float
    pwm_freq_hz: int
    duty_pct: int
    throughput: float
    packet_loss: float
    delay: float
    jitter: float


@dataclass
class SimulationSample:
    timestamp: str
    time_s: float
    mode: str
    distance_cm: float
    b_uT: float
    emi_mv: float
    pwm_freq_hz: int
    duty_pct: int
    throughput_mbps: float
    packet_loss_pct: float
    delay_ms: float
    jitter_ms: float
    jitter_us: float


REPORT_POINTS = [
    ReportPoint(
        time_s=0.0,
        label="Без помех",
        distance_cm=20.0,
        b_uT=9.0,
        pwm_freq_hz=0,
        duty_pct=0,
        throughput=99.152,
        packet_loss=0.240,
        delay=8.847,
        jitter=0.0001,
    ),
    ReportPoint(
        time_s=15.0,
        label="ЭМП-режим A",
        distance_cm=8.0,
        b_uT=22.8,
        pwm_freq_hz=10_000,
        duty_pct=50,
        throughput=98.921,
        packet_loss=0.479,
        delay=8.848,
        jitter=0.0013,
    ),
    ReportPoint(
        time_s=30.0,
        label="ЭМП-режим B",
        distance_cm=5.0,
        b_uT=36.4,
        pwm_freq_hz=50_000,
        duty_pct=50,
        throughput=98.192,
        packet_loss=1.148,
        delay=8.847,
        jitter=0.0023,
    ),
]


def _lerp(a: float, b: float, p: float) -> float:
    return a + (b - a) * p


def _smoothstep(p: float) -> float:
    p = max(0.0, min(1.0, p))
    return p * p * (3.0 - 2.0 * p)


def _segment_for_time(time_s: float) -> tuple[ReportPoint, ReportPoint, float]:
    if time_s <= REPORT_POINTS[1].time_s:
        left, right = REPORT_POINTS[0], REPORT_POINTS[1]
    else:
        left, right = REPORT_POINTS[1], REPORT_POINTS[2]
    span = right.time_s - left.time_s
    return left, right, _smoothstep((time_s - left.time_s) / span)


def _sample_at(time_s: float) -> SimulationSample:
    time_s = max(0.0, min(SIMULATION_DURATION_S, time_s))
    left, right, p = _segment_for_time(time_s)
    time_phase = time_s * math.tau

    b_uT = _lerp(left.b_uT, right.b_uT, p)
    # Синусоидальная составляющая показывает внешний фон помех,
    # но в контрольных точках отчета метрики остаются ровно табличными.
    edge_factor = 4.0 * p * (1.0 - p)
    background_ripple = (
        0.82 * math.sin(time_phase * 1.35)
        + 0.34 * math.sin(time_phase * 3.7 + 0.8)
        + 0.18 * math.sin(time_phase * 6.1 + 1.6)
    ) * edge_factor
    measured_b = max(0.0, b_uT + background_ripple)

    mode = left.label if p < 0.5 else right.label
    if time_s >= SIMULATION_DURATION_S:
        mode = REPORT_POINTS[-1].label

    emi_stress = measured_b / 36.4
    noise_gate = edge_factor * (0.35 + 0.65 * emi_stress)

    throughput_noise = (
        0.340 * math.sin(time_phase * 0.93 + 0.4)
        + 0.150 * math.sin(time_phase * 2.6)
        + 0.075 * math.sin(time_phase * 6.4 + 2.2)
    ) * noise_gate
    loss_noise = (
        0.230 * math.sin(time_phase * 1.6 + 1.1)
        + 0.095 * math.sin(time_phase * 4.2)
        + 0.050 * math.sin(time_phase * 7.0 + 0.7)
    ) * noise_gate
    delay_noise = (
        0.052 * math.sin(time_phase * 1.15 + 0.3)
        + 0.023 * math.sin(time_phase * 3.4 + 1.7)
        + 0.012 * math.sin(time_phase * 6.6)
    ) * noise_gate
    jitter_noise = (
        0.00032 * math.sin(time_phase * 1.9 + 2.0)
        + 0.00014 * math.sin(time_phase * 5.1)
        + 0.00008 * math.sin(time_phase * 8.2 + 1.4)
    ) * noise_gate

    throughput = _lerp(left.throughput, right.throughput, p) + throughput_noise
    packet_loss = _lerp(left.packet_loss, right.packet_loss, p) + loss_noise
    delay = _lerp(left.delay, right.delay, p) + delay_noise
    jitter_ms = round(max(0.0, _lerp(left.jitter, right.jitter, p) + jitter_noise), 4)

    return SimulationSample(
        timestamp=dt.datetime.now().isoformat(timespec="seconds"),
        time_s=round(time_s, 1),
        mode=mode,
        distance_cm=round(_lerp(left.distance_cm, right.distance_cm, p), 2),
        b_uT=round(measured_b, 2),
        emi_mv=round(measured_b * 17.3, 2),
        pwm_freq_hz=round(_lerp(left.pwm_freq_hz, right.pwm_freq_hz, p)),
        duty_pct=round(_lerp(left.duty_pct, right.duty_pct, p)),
        throughput_mbps=round(throughput, 3),
        packet_loss_pct=round(max(0.0, packet_loss), 3),
        delay_ms=round(delay, 3),
        jitter_ms=jitter_ms,
        jitter_us=round(jitter_ms * 1000.0, 2),
    )


def _svg_chart(
    samples: list[SimulationSample],
    title: str,
    series: list[tuple[str, str, str]],
    y_label: str,
    width: int = 520,
    height: int = 218,
    y_min: float | None = None,
    y_max: float | None = None,
) -> str:
    ml, mr, mt, mb = 54, 18, 34, 34
    pw = width - ml - mr
    ph = height - mt - mb

    xs = [s.time_s for s in samples] or [0.0]
    values: list[float] = []
    for attr, _, _ in series:
        values.extend(float(getattr(s, attr)) for s in samples)
    if not values:
        values = [0.0]

    xmin, xmax = 0.0, SIMULATION_DURATION_S
    ymin = min(values) if y_min is None else y_min
    ymax = max(values) if y_max is None else y_max
    if abs(ymax - ymin) < 1e-9:
        ymax = ymin + 1.0
    pad = (ymax - ymin) * 0.12
    ymin = ymin - pad if y_min is None else y_min
    ymax = ymax + pad if y_max is None else y_max

    def sx(x: float) -> float:
        return ml + (x - xmin) / (xmax - xmin) * pw

    def sy(y: float) -> float:
        return mt + ph - (y - ymin) / (ymax - ymin) * ph

    grid = []
    for i in range(6):
        x = ml + pw * i / 5
        y = mt + ph * i / 5
        xv = xmin + (xmax - xmin) * i / 5
        yv = ymax - (ymax - ymin) * i / 5
        grid.append(f'<line x1="{x:.1f}" y1="{mt}" x2="{x:.1f}" y2="{mt + ph}" stroke="#233A66" stroke-width="1"/>')
        grid.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml + pw}" y2="{y:.1f}" stroke="#233A66" stroke-width="1"/>')
        grid.append(f'<text x="{x:.1f}" y="{height - 12}" text-anchor="middle" fill="#9EC2FF" font-size="10">{xv:.0f}</text>')
        grid.append(f'<text x="{ml - 9}" y="{y + 4:.1f}" text-anchor="end" fill="#9EC2FF" font-size="10">{yv:.2f}</text>')

    paths = []
    legends = []
    for index, (attr, label, color) in enumerate(series):
        points = " ".join(f"{sx(s.time_s):.2f},{sy(float(getattr(s, attr))):.2f}" for s in samples)
        if points:
            paths.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.8" points="{points}" />')
            paths.extend(
                f'<circle cx="{sx(s.time_s):.2f}" cy="{sy(float(getattr(s, attr))):.2f}" r="2.4" fill="{color}" />'
                for s in samples[-10:]
            )
        if label:
            lx = ml + index * 126
            legends.append(f'<circle cx="{lx}" cy="27" r="5" fill="{color}"/><text x="{lx + 10}" y="31" fill="#D7E6FF" font-size="11">{label}</text>')

    return f"""
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" rx="10" fill="#0B1224"/>
  <text x="{ml}" y="16" fill="#F6FAFF" font-size="14" font-weight="700">{title}</text>
  {"".join(legends)}
  <rect x="{ml}" y="{mt}" width="{pw}" height="{ph}" fill="#101B34" stroke="#2B4678" />
  {"".join(grid)}
  {"".join(paths)}
  <text x="{ml + pw / 2:.1f}" y="{height - 1}" text-anchor="middle" fill="#9EC2FF" font-size="10">время, с</text>
  <text x="15" y="{mt + ph / 2:.1f}" transform="rotate(-90 15 {mt + ph / 2:.1f})" text-anchor="middle" fill="#9EC2FF" font-size="10">{y_label}</text>
</svg>
""".strip()


def _chart_image(samples: list[SimulationSample], *args, **kwargs) -> ft.Image:
    svg = _svg_chart(samples, *args, **kwargs)
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return ft.Image(
        src=f"data:image/svg+xml;base64,{encoded}",
        width=520,
        height=218,
        fit=ft.BoxFit.CONTAIN,
    )


def _save_csv(samples: list[SimulationSample]) -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(samples[0]).keys()))
        writer.writeheader()
        for sample in samples:
            writer.writerow(asdict(sample))


def main(page: ft.Page) -> None:
    page.title = "Arduino Console"
    page.window_width = 1280
    page.window_height = 900
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#070B16"
    page.padding = 18

    samples = [_sample_at(0.0)]
    running = False
    stop_event = threading.Event()

    timer_text = ft.Text("00.0 / 30.0 с", size=28, weight=ft.FontWeight.BOLD, color="#8EE8FF")
    mode_text = ft.Text("Без помех", size=18, color="#FFB44C", weight=ft.FontWeight.W_700)
    progress = ft.ProgressBar(value=0, width=360, color="#38D5FF", bgcolor="#13223C")

    qos_value = ft.Text("99.152 / 0.240%", size=20, weight=ft.FontWeight.BOLD, color="#F6FAFF")
    latency_value = ft.Text("8.847 мс / 0.1 мкс", size=20, weight=ft.FontWeight.BOLD, color="#F6FAFF")
    csv_text = ft.Text(f"CSV: {OUTPUT_CSV}", color="#8FAFDA")

    chart_throughput = ft.Container()
    chart_loss = ft.Container()
    chart_delay = ft.Container()

    start_button = ft.ElevatedButton("Запустить", icon=ft.Icons.PLAY_ARROW)
    reset_button = ft.OutlinedButton("Сброс", icon=ft.Icons.RESTART_ALT)

    def metric_card(title: str, value: ft.Text, accent: str) -> ft.Container:
        return ft.Container(
            width=250,
            padding=16,
            border_radius=10,
            bgcolor="#101C2F",
            border=ft.border.all(1, "#263D66"),
            content=ft.Column(
                [
                    ft.Text(title, color=accent, weight=ft.FontWeight.W_700),
                    value,
                ],
                spacing=7,
            ),
        )

    def render() -> None:
        current = samples[-1]
        timer_text.value = f"{current.time_s:04.1f} / 30.0 с"
        mode_text.value = current.mode
        progress.value = current.time_s / SIMULATION_DURATION_S
        qos_value.value = f"{current.throughput_mbps:.3f} / {current.packet_loss_pct:.3f}%"
        latency_value.value = f"{current.delay_ms:.3f} мс / {current.jitter_us:.1f} мкс"

        chart_throughput.content = _chart_image(
            samples,
            "Throughput",
            [
                ("throughput_mbps", "", "#63E6BE"),
            ],
            "Мбит/с",
            y_min=97.5,
            y_max=99.6,
        )
        chart_loss.content = _chart_image(
            samples,
            "Packet Loss",
            [
                ("packet_loss_pct", "", "#FF5EA8"),
            ],
            "%",
            y_min=0,
            y_max=1.6,
        )
        chart_delay.content = _chart_image(
            samples,
            "Delay и Jitter",
            [
                ("delay_ms", "delay", "#FFB44C"),
                ("jitter_us", "jitter, мкс", "#38D5FF"),
            ],
            "delay, мс / jitter, мкс",
            y_min=0,
            y_max=9.2,
        )
        page.update()

    async def run_simulation() -> None:
        nonlocal running, samples
        running = True
        stop_event.clear()
        start_button.disabled = True
        reset_button.disabled = True

        samples = [_sample_at(0.0)]
        render()

        total_steps = int(SIMULATION_DURATION_S / TICK_S)
        for step in range(1, total_steps + 1):
            if stop_event.is_set():
                break
            target_elapsed = step * TICK_S
            await asyncio.sleep(TICK_S)
            samples.append(_sample_at(target_elapsed))
            render()

        if samples[-1].time_s < SIMULATION_DURATION_S and not stop_event.is_set():
            samples.append(_sample_at(SIMULATION_DURATION_S))
        _save_csv(samples)
        running = False
        start_button.disabled = False
        reset_button.disabled = False
        render()

    def start(_: ft.ControlEvent) -> None:
        if running:
            return
        page.run_task(run_simulation)

    def reset(_: ft.ControlEvent) -> None:
        nonlocal samples
        if running:
            stop_event.set()
            return
        samples = [_sample_at(0.0)]
        render()

    start_button.on_click = start
    reset_button.on_click = reset

    page.add(
        ft.Container(
            padding=18,
            border_radius=16,
            gradient=ft.LinearGradient(
                begin=ft.Alignment(-1, -1),
                end=ft.Alignment(1, 1),
                colors=["#0C1224", "#101B34", "#081326"],
            ),
            border=ft.border.all(1, "#2A4D91"),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column([timer_text, mode_text, progress], spacing=8),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row([start_button, reset_button, csv_text], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row(
                        [
                            metric_card("Mbps / loss", qos_value, "#63E6BE"),
                            metric_card("Delay / jitter", latency_value, "#FF5EA8"),
                        ],
                        spacing=14,
                    ),
                    ft.Row(
                        [
                            ft.Column([chart_loss], spacing=14),
                            ft.Column([chart_throughput, chart_delay], spacing=14),
                        ],
                        spacing=16,
                    ),
                    ft.Container(
                        padding=14,
                        border_radius=10,
                        bgcolor="#101C2F",
                        border=ft.border.all(1, "#263D66"),
                        content=ft.Text(
                            "Контрольные точки: 0 с — без помех; 15 с — ЭМП-режим A; 30 с — ЭМП-режим B. "
                            "Итоговые значения совпадают с таблицей отчета для выбранной линии.",
                            color="#D7E6FF",
                        ),
                    ),
                ],
                spacing=14,
            ),
        )
    )
    render()


if __name__ == "__main__":
    ft.app(target=main)
