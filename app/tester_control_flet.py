import csv
import datetime as dt
import json
import queue
import re
import base64
import subprocess
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import flet as ft

try:
    import serial  # type: ignore
except Exception:
    serial = None


@dataclass
class StepResult:
    timestamp_utc: str
    frequency_hz: int
    duty_percent: int
    duration_s: int
    field_v_m: Optional[float]
    field_t: Optional[float]
    ping_avg_ms: Optional[float]
    packet_loss_percent: Optional[float]
    iperf_mbps: Optional[float]
    speedtest_download_mbps: Optional[float]
    speedtest_upload_mbps: Optional[float]
    raw_sensor_line: str
    notes: str


def _run_command(command: list[str], timeout: int) -> tuple[int, str, str]:
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
        encoding="utf-8",
        errors="replace",
    )
    return process.returncode, process.stdout, process.stderr


def _parse_ping(output: str) -> tuple[Optional[float], Optional[float]]:
    # Поддержка английской и русской локали Windows ping.
    avg_patterns = [
        r"Average = (\d+)\w*",
        r"Среднее = (\d+)\w*",
    ]
    loss_patterns = [
        r"Lost = \d+ \((\d+)% loss\)",
        r"Потеряно = \d+ \((\d+)% потерь\)",
    ]

    avg_ms = None
    loss = None

    for pattern in avg_patterns:
        m = re.search(pattern, output)
        if m:
            avg_ms = float(m.group(1))
            break

    for pattern in loss_patterns:
        m = re.search(pattern, output)
        if m:
            loss = float(m.group(1))
            break

    return avg_ms, loss


def _parse_iperf_json(output: str) -> Optional[float]:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return None

    bits_per_second = (
        data.get("end", {})
        .get("sum_received", {})
        .get("bits_per_second")
    )
    if bits_per_second is None:
        bits_per_second = (
            data.get("end", {})
            .get("sum", {})
            .get("bits_per_second")
        )
    if bits_per_second is None:
        return None
    return round(bits_per_second / 1_000_000, 3)


def _parse_speedtest_json(output: str) -> tuple[Optional[float], Optional[float]]:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return None, None

    download = data.get("download", {}).get("bandwidth")
    upload = data.get("upload", {}).get("bandwidth")
    if download is not None:
        download = round((download * 8) / 1_000_000, 3)
    if upload is not None:
        upload = round((upload * 8) / 1_000_000, 3)
    return download, upload


def _parse_sensor_line(line: str) -> tuple[Optional[float], Optional[float]]:
    # Ожидаемый формат: E=12.4;B=0.003 или JSON {"E":12.4,"B":0.003}
    line = line.strip()
    if not line:
        return None, None

    if line.startswith("{") and line.endswith("}"):
        try:
            payload = json.loads(line)
            return payload.get("E"), payload.get("B")
        except json.JSONDecodeError:
            return None, None

    m_e = re.search(r"E\s*=\s*([0-9]+(?:\.[0-9]+)?)", line)
    m_b = re.search(r"B\s*=\s*([0-9]+(?:\.[0-9]+)?)", line)
    e = float(m_e.group(1)) if m_e else None
    b = float(m_b.group(1)) if m_b else None
    return e, b


def _to_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _read_csv_points(csv_path: Path, x_key: str, y_key: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    if not csv_path.exists():
        return points

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            x = _to_float((row.get(x_key) or "").strip())
            y = _to_float((row.get(y_key) or "").strip())
            if x is not None and y is not None:
                points.append((x, y))
    return points


def _build_svg_chart(
    points: list[tuple[float, float]],
    x_label: str,
    y_label: str,
    width: int = 1080,
    height: int = 320,
) -> str:
    margin_left = 70
    margin_right = 20
    margin_top = 20
    margin_bottom = 50

    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    if x_min == x_max:
        x_max = x_min + 1.0
    if y_min == y_max:
        y_max = y_min + 1.0

    def sx(x: float) -> float:
        return margin_left + (x - x_min) / (x_max - x_min) * plot_w

    def sy(y: float) -> float:
        return margin_top + plot_h - (y - y_min) / (y_max - y_min) * plot_h

    polyline = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in points)

    x_ticks = []
    y_ticks = []
    tick_count = 5
    for i in range(tick_count + 1):
        tx = margin_left + (plot_w * i / tick_count)
        ty = margin_top + (plot_h * i / tick_count)
        x_val = x_min + (x_max - x_min) * i / tick_count
        y_val = y_max - (y_max - y_min) * i / tick_count
        x_ticks.append(
            f'<line x1="{tx:.1f}" y1="{margin_top + plot_h}" x2="{tx:.1f}" y2="{margin_top + plot_h + 6}" stroke="#4A6699" />'
            f'<text x="{tx:.1f}" y="{margin_top + plot_h + 20}" text-anchor="middle" fill="#9EC2FF" font-size="11">{x_val:.2f}</text>'
        )
        y_ticks.append(
            f'<line x1="{margin_left - 6}" y1="{ty:.1f}" x2="{margin_left}" y2="{ty:.1f}" stroke="#4A6699" />'
            f'<text x="{margin_left - 10}" y="{ty + 4:.1f}" text-anchor="end" fill="#9EC2FF" font-size="11">{y_val:.2f}</text>'
        )

    circles = "".join(
        f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="2.8" fill="#8CF3FF" />' for x, y in points
    )

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect x="0" y="0" width="{width}" height="{height}" fill="#0C1324"/>
  <rect x="{margin_left}" y="{margin_top}" width="{plot_w}" height="{plot_h}" fill="#0E1830" stroke="#2B4678"/>
  <line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}" stroke="#5D7DB7"/>
  <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" stroke="#5D7DB7"/>
  {"".join(x_ticks)}
  {"".join(y_ticks)}
  <polyline fill="none" stroke="#45E0FF" stroke-width="2.5" points="{polyline}" />
  {circles}
  <text x="{margin_left + plot_w / 2:.1f}" y="{height - 8}" text-anchor="middle" fill="#9EC2FF" font-size="12">{x_label}</text>
  <text x="18" y="{margin_top + plot_h / 2:.1f}" transform="rotate(-90 18 {margin_top + plot_h / 2:.1f})" text-anchor="middle" fill="#9EC2FF" font-size="12">{y_label}</text>
</svg>
"""
    return svg.strip()


class TesterRunner:
    def __init__(self, log_queue: queue.Queue[str]) -> None:
        self.log_queue = log_queue
        self.stop_event = threading.Event()

    def log(self, text: str) -> None:
        timestamp = dt.datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {text}")

    def stop(self) -> None:
        self.stop_event.set()

    def run(
        self,
        serial_port: str,
        baudrate: int,
        iperf_host: str,
        ping_host: str,
        steps: list[tuple[int, int, int]],
        output_csv: Path,
    ) -> None:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        results: list[StepResult] = []

        ser = None
        if serial_port and serial is not None:
            try:
                ser = serial.Serial(serial_port, baudrate=baudrate, timeout=2)
                self.log(f"Подключение к тестеру: {serial_port} @ {baudrate}")
                time.sleep(1.0)
                ser.reset_input_buffer()
            except Exception as exc:
                self.log(f"Не удалось открыть порт: {exc}")
                ser = None
        elif serial_port and serial is None:
            self.log("Пакет pyserial не установлен. Данные датчика будут пустыми.")

        try:
            for frequency, duty, duration in steps:
                if self.stop_event.is_set():
                    self.log("Остановка по запросу пользователя.")
                    break

                self.log(
                    f"Шаг: частота={frequency} Гц, заполнение={duty}%, длительность={duration} с"
                )

                if ser is not None:
                    command = f"SET FREQ={frequency} DUTY={duty} DUR={duration}\n"
                    ser.write(command.encode("utf-8", errors="replace"))
                    ser.flush()

                # Время стабилизации генератора и поля.
                time.sleep(max(1, duration // 4))

                sensor_line = ""
                e_field = None
                b_field = None
                if ser is not None:
                    try:
                        sensor_line = ser.readline().decode("utf-8", errors="replace").strip()
                        e_field, b_field = _parse_sensor_line(sensor_line)
                    except Exception as exc:
                        self.log(f"Ошибка чтения датчика: {exc}")

                # ping
                ping_cmd = ["ping", ping_host, "-n", "10"]
                ping_avg, ping_loss = None, None
                try:
                    _, ping_out, _ = _run_command(ping_cmd, timeout=40)
                    ping_avg, ping_loss = _parse_ping(ping_out)
                except Exception as exc:
                    self.log(f"ping завершился с ошибкой: {exc}")

                # iperf3
                iperf_mbps = None
                try:
                    _, iperf_out, _ = _run_command(
                        ["iperf3", "-c", iperf_host, "-J", "-t", "10"],
                        timeout=40,
                    )
                    iperf_mbps = _parse_iperf_json(iperf_out)
                except Exception as exc:
                    self.log(f"iperf3 завершился с ошибкой: {exc}")

                # speedtest
                download, upload = None, None
                try:
                    _, speed_out, _ = _run_command(
                        ["speedtest", "--accept-license", "--accept-gdpr", "-f", "json"],
                        timeout=120,
                    )
                    download, upload = _parse_speedtest_json(speed_out)
                except Exception as exc:
                    self.log(f"speedtest завершился с ошибкой: {exc}")

                result = StepResult(
                    timestamp_utc=dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    frequency_hz=frequency,
                    duty_percent=duty,
                    duration_s=duration,
                    field_v_m=e_field,
                    field_t=b_field,
                    ping_avg_ms=ping_avg,
                    packet_loss_percent=ping_loss,
                    iperf_mbps=iperf_mbps,
                    speedtest_download_mbps=download,
                    speedtest_upload_mbps=upload,
                    raw_sensor_line=sensor_line,
                    notes="ok",
                )
                results.append(result)
                self.log(
                    "Шаг завершен: "
                    f"E={result.field_v_m}, ping={result.ping_avg_ms} мс, "
                    f"потери={result.packet_loss_percent}%, iperf={result.iperf_mbps} Мбит/с"
                )
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

        with output_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(StepResult("", 0, 0, 0, None, None, None, None, None, None, None, "", "")).keys()))
            writer.writeheader()
            for row in results:
                writer.writerow(asdict(row))

        self.log(f"Сохранено результатов: {len(results)} в {output_csv}")


def _build_steps(
    frequency_start: int,
    frequency_stop: int,
    frequency_step: int,
    duty_percent: int,
    duration_s: int,
) -> list[tuple[int, int, int]]:
    steps: list[tuple[int, int, int]] = []
    if frequency_step <= 0:
        raise ValueError("Шаг частоты должен быть положительным.")
    if frequency_stop < frequency_start:
        raise ValueError("Конечная частота должна быть больше или равна начальной.")
    if not (0 <= duty_percent <= 100):
        raise ValueError("Коэффициент заполнения должен быть в диапазоне 0..100.")
    if duration_s <= 0:
        raise ValueError("Длительность шага должна быть больше нуля.")

    frequency = frequency_start
    while frequency <= frequency_stop:
        steps.append((frequency, duty_percent, duration_s))
        frequency += frequency_step
    return steps


def main(page: ft.Page) -> None:
    page.title = "EMI Quantum Console"
    page.window_width = 1200
    page.window_height = 840
    page.scroll = ft.ScrollMode.AUTO
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#070B16"

    log_queue: queue.Queue[str] = queue.Queue()
    runner = TesterRunner(log_queue)
    worker: Optional[threading.Thread] = None

    serial_port = ft.TextField(label="COM-порт тестера", value="COM3", width=180, color="#D7E6FF")
    baudrate = ft.TextField(label="Скорость порта", value="115200", width=160, color="#D7E6FF")
    iperf_host = ft.TextField(label="IP iperf3-сервера", value="192.168.1.10", width=210, color="#D7E6FF")
    ping_host = ft.TextField(label="Хост для ping", value="8.8.8.8", width=160, color="#D7E6FF")
    output_csv = ft.TextField(label="Файл результата CSV", value="results/session.csv", width=380, color="#D7E6FF")

    frequency_start = ft.TextField(label="Частота от, Гц", value="10000", width=160, color="#D7E6FF")
    frequency_stop = ft.TextField(label="Частота до, Гц", value="50000", width=160, color="#D7E6FF")
    frequency_step = ft.TextField(label="Шаг частоты, Гц", value="10000", width=170, color="#D7E6FF")
    duty_percent = ft.TextField(label="Заполнение, %", value="30", width=160, color="#D7E6FF")
    duration_s = ft.TextField(label="Длительность шага, с", value="15", width=180, color="#D7E6FF")

    csv_for_plot = ft.TextField(label="CSV для графика", value="results/session.csv", width=380, color="#D7E6FF")
    x_metric = ft.Dropdown(
        label="Ось X",
        value="frequency_hz",
        width=220,
        options=[
            ft.dropdown.Option("frequency_hz"),
            ft.dropdown.Option("field_v_m"),
            ft.dropdown.Option("field_t"),
            ft.dropdown.Option("duty_percent"),
            ft.dropdown.Option("duration_s"),
        ],
    )
    y_metric = ft.Dropdown(
        label="Ось Y",
        value="iperf_mbps",
        width=260,
        options=[
            ft.dropdown.Option("iperf_mbps"),
            ft.dropdown.Option("packet_loss_percent"),
            ft.dropdown.Option("ping_avg_ms"),
            ft.dropdown.Option("speedtest_download_mbps"),
            ft.dropdown.Option("speedtest_upload_mbps"),
            ft.dropdown.Option("field_v_m"),
            ft.dropdown.Option("field_t"),
        ],
    )
    chart = ft.Image(src="", width=1080, height=320)
    chart_hint = ft.Text("Загрузите CSV, чтобы построить график.", color="#86A9FF")

    log_view = ft.TextField(
        label="Журнал",
        multiline=True,
        min_lines=14,
        max_lines=14,
        width=1080,
        color="#D7E6FF",
        bgcolor="#0E1426",
    )

    def ui_log(message: str) -> None:
        log_view.value = (log_view.value + "\n" + message).strip()
        page.update()

    def flush_logs() -> None:
        while True:
            try:
                ui_log(log_queue.get_nowait())
            except queue.Empty:
                break

    def log_pump() -> None:
        while True:
            if hasattr(page, "call_from_thread"):
                page.call_from_thread(flush_logs)
            else:
                flush_logs()
            time.sleep(0.5)

    threading.Thread(target=log_pump, daemon=True).start()

    def draw_chart(_: Optional[ft.ControlEvent] = None) -> None:
        csv_path = Path(csv_for_plot.value.strip())
        points = _read_csv_points(csv_path, x_metric.value or "", y_metric.value or "")
        if not points:
            chart.src_base64 = None
            chart_hint.value = "Нет валидных числовых данных для выбранных осей."
            page.update()
            return

        points.sort(key=lambda p: p[0])
        svg = _build_svg_chart(
            points,
            x_label=x_metric.value or "X",
            y_label=y_metric.value or "Y",
            width=1080,
            height=320,
        )
        chart.src_base64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        chart_hint.value = f"Построено точек: {len(points)}"
        page.update()

    def start_run(_: ft.ControlEvent) -> None:
        nonlocal worker
        if worker and worker.is_alive():
            ui_log("Процесс уже запущен.")
            return

        try:
            parsed_steps = _build_steps(
                frequency_start=int(frequency_start.value.strip()),
                frequency_stop=int(frequency_stop.value.strip()),
                frequency_step=int(frequency_step.value.strip()),
                duty_percent=int(duty_percent.value.strip()),
                duration_s=int(duration_s.value.strip()),
            )
        except Exception as exc:
            ui_log(f"Ошибка параметров шага: {exc}")
            return

        runner.stop_event.clear()
        worker = threading.Thread(
            target=runner.run,
            args=(
                serial_port.value.strip(),
                int(baudrate.value.strip()),
                iperf_host.value.strip(),
                ping_host.value.strip(),
                parsed_steps,
                Path(output_csv.value.strip()),
            ),
            daemon=True,
        )
        worker.start()
        ui_log("Запуск сценария тестирования.")

    def stop_run(_: ft.ControlEvent) -> None:
        runner.stop()
        ui_log("Отправлен запрос на остановку.")

    page.add(
        ft.Container(
            padding=20,
            border_radius=16,
            gradient=ft.LinearGradient(
                begin=ft.Alignment(-1, -1),
                end=ft.Alignment(1, 1),
                colors=["#0C1224", "#111B34", "#0A1730"],
            ),
            border=ft.border.all(1, "#2A4D91"),
            shadow=ft.BoxShadow(blur_radius=30, color="#112B66", spread_radius=1),
            content=ft.Column(
                controls=[
                    ft.Text(
                        "EMI Quantum Console",
                        size=28,
                        weight=ft.FontWeight.BOLD,
                        color="#8EE8FF",
                    ),
                    ft.Text(
                        "Управление тестером, сбор телеметрии и анализ CSV",
                        color="#8FAFDA",
                    ),
                    ft.Divider(color="#1E366E"),
                    ft.Text("Подключение и сеть", color="#9CC5FF", weight=ft.FontWeight.W_600),
                    ft.Row([serial_port, baudrate, iperf_host, ping_host, output_csv], wrap=True, spacing=10),
                    ft.Text("Параметры сценария", color="#9CC5FF", weight=ft.FontWeight.W_600),
                    ft.Row([frequency_start, frequency_stop, frequency_step, duty_percent, duration_s], spacing=10),
                    ft.Row(
                        [
                            ft.ElevatedButton("Старт теста", icon=ft.Icons.PLAY_ARROW, on_click=start_run),
                            ft.OutlinedButton("Стоп", icon=ft.Icons.STOP, on_click=stop_run),
                            ft.OutlinedButton("Построить график из CSV", icon=ft.Icons.SHOW_CHART, on_click=draw_chart),
                        ]
                    ),
                    ft.Divider(color="#1E366E"),
                    ft.Text("Построение графика", color="#9CC5FF", weight=ft.FontWeight.W_600),
                    ft.Row([csv_for_plot, x_metric, y_metric], wrap=True, spacing=10),
                    chart_hint,
                    chart,
                    ft.Divider(color="#1E366E"),
                    log_view,
                ],
                spacing=10,
            ),
        ),
    )


if __name__ == "__main__":
    ft.app(target=main)
