"""
emi_controller.py — главный управляющий скрипт EMI Stress-Tester
Управляет генератором помех (ESP32), запускает сетевые тесты,
логирует данные с EMI-датчика, синхронизирует по timestamp.
"""

import serial
import subprocess
import csv
import time
import threading
import json
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────
# Конфигурация
# ──────────────────────────────────────────────
SERIAL_PORT   = "/dev/ttyUSB0"   # порт ESP32
BAUD_RATE     = 115200
IPERF_SERVER  = "192.168.1.100"  # IP iperf3-сервера
IPERF_PORT    = 5201
PING_HOST     = "192.168.1.100"
PING_COUNT    = 20

LOG_DIR       = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

SESSION_ID    = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE      = LOG_DIR / f"session_{SESSION_ID}.csv"
RAW_EMI_FILE  = LOG_DIR / f"emi_raw_{SESSION_ID}.csv"

# Шаги теста: (pwm_freq_hz, duty_percent, label)
TEST_STEPS = [
    (0,    0,  "baseline"),
    (50,   30, "50Hz_low"),
    (50,   70, "50Hz_high"),
    (100,  50, "100Hz"),
    (500,  50, "500Hz"),
    (1000, 50, "1kHz"),
    (5000, 50, "5kHz"),
    (10000,50, "10kHz"),
    (50000,50, "50kHz"),
]

STABILIZE_TIME = 3   # сек между изменением параметров и запуском теста
IPERF_DURATION = 10  # сек


# ──────────────────────────────────────────────
# Класс: соединение с ESP32
# ──────────────────────────────────────────────
class ESP32Controller:
    def __init__(self, port: str, baud: int):
        self.ser = serial.Serial(port, baud, timeout=2)
        time.sleep(2)          # ждём готовности ESP32
        print(f"[ESP32] Подключено: {port}")

    def send_command(self, freq: int, duty: int) -> str:
        """Отправляет команду вида 'SET:freq=1000,duty=50' и читает ответ."""
        cmd = f"SET:freq={freq},duty={duty}\n"
        self.ser.write(cmd.encode())
        resp = self.ser.readline().decode().strip()
        return resp

    def stop(self):
        self.ser.write(b"STOP\n")
        self.ser.close()


# ──────────────────────────────────────────────
# Класс: чтение EMI-датчика в фоновом потоке
# ──────────────────────────────────────────────
class EMISensor:
    """
    Читает данные с EMI-датчика (ADC через ESP32 второй UART или I2C).
    Формат строки от датчика: 'EMI:<значение_мВ>\n'
    """
    def __init__(self, port: str, baud: int):
        self.ser    = serial.Serial(port, baud, timeout=1)
        self.latest = {"timestamp": None, "emi_mv": 0.0}
        self._lock  = threading.Lock()
        self._stop  = threading.Event()
        self._raw_rows = []

    def _read_loop(self):
        while not self._stop.is_set():
            try:
                line = self.ser.readline().decode().strip()
                if line.startswith("EMI:"):
                    val = float(line.split(":")[1])
                    ts  = datetime.now().isoformat()
                    with self._lock:
                        self.latest = {"timestamp": ts, "emi_mv": val}
                    self._raw_rows.append([ts, val])
            except Exception:
                pass

    def start(self):
        t = threading.Thread(target=self._read_loop, daemon=True)
        t.start()

    def stop(self):
        self._stop.set()
        self.ser.close()

    def get(self) -> dict:
        with self._lock:
            return dict(self.latest)

    def save_raw(self, path: Path):
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "emi_mv"])
            w.writerows(self._raw_rows)


# ──────────────────────────────────────────────
# Сетевые тесты
# ──────────────────────────────────────────────
def run_iperf3(server: str, port: int, duration: int) -> dict:
    """Запускает iperf3 и возвращает словарь с результатами."""
    try:
        result = subprocess.run(
            ["iperf3", "-c", server, "-p", str(port),
             "-t", str(duration), "-J"],
            capture_output=True, text=True, timeout=duration + 10
        )
        data = json.loads(result.stdout)
        bps  = data["end"]["sum_received"]["bits_per_second"]
        return {
            "throughput_mbps": round(bps / 1e6, 3),
            "retransmits":     data["end"]["sum_sent"].get("retransmits", 0),
        }
    except Exception as e:
        print(f"  [iperf3] Ошибка: {e}")
        return {"throughput_mbps": 0.0, "retransmits": -1}


def run_ping(host: str, count: int) -> dict:
    """Запускает ping и парсит packet loss и avg rtt."""
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), host],
            capture_output=True, text=True, timeout=count * 2 + 5
        )
        lines = result.stdout.splitlines()
        loss_line = next((l for l in lines if "packet loss" in l), "")
        rtt_line  = next((l for l in lines if "rtt" in l or "round-trip" in l), "")

        # packet loss
        loss = 0.0
        for part in loss_line.split():
            if "%" in part:
                loss = float(part.replace("%", ""))
                break

        # avg RTT
        avg_rtt = 0.0
        if "/" in rtt_line:
            parts   = rtt_line.split("=")[-1].strip().split("/")
            avg_rtt = float(parts[1])

        return {"packet_loss_pct": loss, "avg_rtt_ms": avg_rtt}
    except Exception as e:
        print(f"  [ping] Ошибка: {e}")
        return {"packet_loss_pct": 100.0, "avg_rtt_ms": -1}


# ──────────────────────────────────────────────
# Главный цикл
# ──────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  EMI Stress-Tester — старт сессии", SESSION_ID)
    print("=" * 60)

    esp  = ESP32Controller(SERIAL_PORT, BAUD_RATE)

    # Датчик — второй UART (или тот же порт, если ESP32 мультиплексирует)
    # Для автономного запуска без датчика — заменить на EMISensorMock()
    emi_port = "/dev/ttyUSB1"
    emi  = EMISensor(emi_port, BAUD_RATE)
    emi.start()

    rows = []
    fieldnames = [
        "timestamp", "step_label", "pwm_freq_hz", "duty_pct",
        "emi_mv",
        "throughput_mbps", "retransmits",
        "packet_loss_pct", "avg_rtt_ms",
    ]

    try:
        for freq, duty, label in TEST_STEPS:
            print(f"\n[STEP] {label}  freq={freq} Hz  duty={duty}%")

            # 1. Установить параметры генератора
            resp = esp.send_command(freq, duty)
            print(f"  ESP32 → {resp}")

            # 2. Дать сигналу стабилизироваться
            time.sleep(STABILIZE_TIME)

            # 3. Снять EMI
            emi_snap = emi.get()
            emi_val  = emi_snap["emi_mv"]
            print(f"  EMI   = {emi_val:.2f} мВ")

            # 4. Запустить сетевые тесты параллельно
            ts = datetime.now().isoformat()

            iperf_res = run_iperf3(IPERF_SERVER, IPERF_PORT, IPERF_DURATION)
            ping_res  = run_ping(PING_HOST, PING_COUNT)

            print(f"  iperf3 → {iperf_res['throughput_mbps']} Мбит/с  "
                  f"retx={iperf_res['retransmits']}")
            print(f"  ping   → loss={ping_res['packet_loss_pct']}%  "
                  f"rtt={ping_res['avg_rtt_ms']} мс")

            # 5. Записать строку
            row = {
                "timestamp":       ts,
                "step_label":      label,
                "pwm_freq_hz":     freq,
                "duty_pct":        duty,
                "emi_mv":          round(emi_val, 2),
                **iperf_res,
                **ping_res,
            }
            rows.append(row)

    except KeyboardInterrupt:
        print("\n[!] Прерывание пользователем")

    finally:
        esp.stop()
        emi.stop()

        # Сохранить сводный лог
        with open(LOG_FILE, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        print(f"\n[OK] Лог сохранён → {LOG_FILE}")

        # Сохранить сырые данные датчика
        emi.save_raw(RAW_EMI_FILE)
        print(f"[OK] EMI сырые данные → {RAW_EMI_FILE}")


if __name__ == "__main__":
    main()
