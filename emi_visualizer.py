"""
emi_visualizer.py — визуализация результатов EMI Stress-Tester
Строит 3D-график: EMI (мВ) × частота (Гц) × параметр сети
"""

import csv
import sys
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
from pathlib import Path
from mpl_toolkits.mplot3d import Axes3D   # noqa: F401


# ──────────────────────────────────────────────
# Загрузка данных
# ──────────────────────────────────────────────
def load_log(path: str) -> dict:
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "label":          row["step_label"],
                "freq":           float(row["pwm_freq_hz"]),
                "duty":           float(row["duty_pct"]),
                "emi_mv":         float(row["emi_mv"]),
                "throughput":     float(row["throughput_mbps"]),
                "packet_loss":    float(row["packet_loss_pct"]),
                "retransmits":    int(row["retransmits"]),
                "avg_rtt":        float(row["avg_rtt_ms"]),
            })
    return rows


# ──────────────────────────────────────────────
# 3D-график
# ──────────────────────────────────────────────
def plot_3d(rows: list, y_metric: str, y_label: str, title: str,
            out_path: Path):
    freqs = np.array([r["freq"]    for r in rows])
    emi   = np.array([r["emi_mv"]  for r in rows])
    vals  = np.array([r[y_metric]  for r in rows])

    fig = plt.figure(figsize=(11, 7))
    ax  = fig.add_subplot(111, projection="3d")

    # Нормировка цвета по значению метрики
    norm   = plt.Normalize(vals.min(), vals.max())
    colors = cm.plasma(norm(vals))

    sc = ax.scatter(
        np.log10(freqs + 1),   # log-шкала частоты для читаемости
        emi,
        vals,
        c=vals,
        cmap="plasma",
        s=80,
        depthshade=True,
        edgecolors="white",
        linewidths=0.4,
    )

    # Линия тренда (проекция на плоскость EMI-метрика)
    idx = np.argsort(emi)
    ax.plot(
        np.log10(freqs[idx] + 1),
        emi[idx],
        vals[idx],
        color="white",
        linewidth=1.2,
        alpha=0.6,
        linestyle="--",
    )

    ax.set_xlabel("log₁₀(Частота ШИМ, Гц)", labelpad=10)
    ax.set_ylabel("Уровень ЭМП, мВ",         labelpad=10)
    ax.set_zlabel(y_label,                    labelpad=10)
    ax.set_title(title, pad=18, fontsize=12, fontweight="bold")

    # Аннотации точек
    for r in rows:
        ax.text(
            np.log10(r["freq"] + 1),
            r["emi_mv"],
            r[y_metric],
            r["label"],
            fontsize=6.5,
            color="lightgray",
            alpha=0.85,
        )

    cbar = fig.colorbar(sc, ax=ax, shrink=0.5, pad=0.1)
    cbar.set_label(y_label, fontsize=9)

    fig.patch.set_facecolor("#0f0f1a")
    ax.set_facecolor("#0f0f1a")
    ax.tick_params(colors="lightgray")
    ax.xaxis.label.set_color("lightgray")
    ax.yaxis.label.set_color("lightgray")
    ax.zaxis.label.set_color("lightgray")
    ax.title.set_color("white")

    plt.tight_layout()
    plt.savefig(out_path, dpi=160, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"[OK] График сохранён → {out_path}")
    plt.close()


# ──────────────────────────────────────────────
# 2D сводка
# ──────────────────────────────────────────────
def plot_summary(rows: list, out_path: Path):
    freqs      = [r["freq"]       for r in rows]
    emi        = [r["emi_mv"]     for r in rows]
    throughput = [r["throughput"] for r in rows]
    loss       = [r["packet_loss"]for r in rows]
    rtt        = [r["avg_rtt"]    for r in rows]

    fig, axes = plt.subplots(3, 1, figsize=(10, 10),
                             facecolor="#0f0f1a", sharex=False)

    colors_line = ["#00e5ff", "#ff4081", "#69ff47"]
    labels  = [
        ("Уровень ЭМП, мВ",          emi,        colors_line[0]),
        ("Пропускная способность, Мбит/с", throughput, colors_line[1]),
        ("Потеря пакетов, %",         loss,       colors_line[2]),
    ]

    x     = list(range(len(freqs)))
    xlbls = [r["label"] for r in rows]

    for ax, (ylabel, data, color) in zip(axes, labels):
        ax.set_facecolor("#0f0f1a")
        ax.plot(x, data, color=color, linewidth=2.0, marker="o",
                markersize=6, markerfacecolor="white")
        ax.fill_between(x, data, alpha=0.12, color=color)
        ax.set_ylabel(ylabel, color="lightgray", fontsize=9)
        ax.set_xticks(x)
        ax.set_xticklabels(xlbls, rotation=30, ha="right",
                           color="lightgray", fontsize=8)
        ax.tick_params(colors="lightgray")
        ax.spines[["top", "right"]].set_visible(False)
        for spine in ax.spines.values():
            spine.set_color("#333355")
        ax.grid(axis="y", color="#333355", linewidth=0.5)

    fig.suptitle("EMI Stress-Tester — сводные результаты",
                 color="white", fontsize=13, fontweight="bold", y=0.99)
    plt.tight_layout()
    plt.savefig(out_path, dpi=160, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"[OK] Сводка сохранена → {out_path}")
    plt.close()


# ──────────────────────────────────────────────
# Анализ корреляции
# ──────────────────────────────────────────────
def print_correlation(rows: list):
    emi        = np.array([r["emi_mv"]      for r in rows])
    throughput = np.array([r["throughput"]  for r in rows])
    loss       = np.array([r["packet_loss"] for r in rows])
    rtt        = np.array([r["avg_rtt"]     for r in rows])

    print("\n── Коэффициенты корреляции Пирсона ──────────────────")
    for name, arr in [("Throughput", throughput),
                      ("Packet Loss", loss),
                      ("RTT",         rtt)]:
        if arr.std() > 0 and emi.std() > 0:
            r = np.corrcoef(emi, arr)[0, 1]
            print(f"  EMI ↔ {name:16s}: r = {r:+.3f}")
        else:
            print(f"  EMI ↔ {name:16s}: недостаточно данных")
    print()


# ──────────────────────────────────────────────
# Точка входа
# ──────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        # Демонстрационный режим: генерируем синтетические данные
        print("[!] Файл не указан — запуск в демо-режиме")
        demo_rows = [
            {"label": s, "freq": f, "duty": 50,
             "emi_mv": 2.0 + i * 1.8 + (i % 3) * 0.5,
             "throughput": 98.9 - i * 0.4 - (i % 2) * 0.3,
             "packet_loss": 0.5 + i * 0.35,
             "retransmits": i,
             "avg_rtt": 8.85 + i * 0.05}
            for i, (f, s) in enumerate([
                (0,     "baseline"),
                (50,    "50Hz_low"),
                (50,    "50Hz_high"),
                (100,   "100Hz"),
                (500,   "500Hz"),
                (1000,  "1kHz"),
                (5000,  "5kHz"),
                (10000, "10kHz"),
                (50000, "50kHz"),
            ])
        ]
        rows = demo_rows
        prefix = Path("logs/demo")
        prefix.parent.mkdir(exist_ok=True)
    else:
        rows   = load_log(sys.argv[1])
        prefix = Path(sys.argv[1]).stem

    print_correlation(rows)

    plot_3d(rows, "packet_loss", "Потеря пакетов, %",
            "EMI × Частота ШИМ × Потеря пакетов",
            Path(f"logs/{prefix}_3d_loss.png"))

    plot_3d(rows, "throughput", "Throughput, Мбит/с",
            "EMI × Частота ШИМ × Пропускная способность",
            Path(f"logs/{prefix}_3d_throughput.png"))

    plot_summary(rows, Path(f"logs/{prefix}_summary.png"))


if __name__ == "__main__":
    main()
