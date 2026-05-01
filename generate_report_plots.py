"""
Графики для отчёта — светлая тема, пригодная для печати и LaTeX.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import cm
from pathlib import Path

Path("report_plots").mkdir(exist_ok=True)

plt.rcParams.update({
    "font.family":      "DejaVu Sans",
    "font.size":        10,
    "axes.titlesize":   11,
    "axes.labelsize":   10,
    "xtick.labelsize":  9,
    "ytick.labelsize":  9,
    "legend.fontsize":  9,
    "figure.facecolor": "white",
    "axes.facecolor":   "white",
    "axes.edgecolor":   "#333333",
    "axes.linewidth":   0.8,
    "axes.grid":        True,
    "grid.color":       "#dddddd",
    "grid.linewidth":   0.6,
    "text.color":       "#111111",
    "axes.labelcolor":  "#111111",
    "xtick.color":      "#111111",
    "ytick.color":      "#111111",
    "lines.linewidth":  1.8,
    "savefig.dpi":      200,
    "savefig.bbox":     "tight",
    "savefig.facecolor":"white",
})

C1 = "#1565C0"   # синий
C2 = "#C62828"   # красный
C3 = "#2E7D32"   # зелёный
C4 = "#F57F17"   # оранжевый
C5 = "#6A1B9A"   # фиолетовый

# ══════════════════════════════════════════════════════════════════════
# ДАННЫЕ
# ══════════════════════════════════════════════════════════════════════
distances_cm = [0, 5, 8, 10, 14, 20]
B_uT         = [2000.0, 36.4, 22.8, 18.2, 13.0, 9.0]

conditions       = ["Без помех", "ЭМП-режим A", "ЭМП-режим B"]
utp_throughput   = [98.892, 95.829, 95.670]
stp_throughput   = [99.152, 98.921, 98.192]
utp_loss         = [0.496,  3.451,  3.488]
stp_loss         = [0.240,  0.479,  1.148]
utp_rtt          = [8.847,  8.868,  8.879]
stp_rtt          = [8.847,  8.848,  8.847]
utp_jitter       = [0.0012, 0.0012, 0.0014]
stp_jitter       = [0.0001, 0.0013, 0.0023]

n_links      = [1, 2, 3, 4, 5, 6, 7]
total_speed  = [8.11, 17.61, 18.23, 18.45, 20.56, 21.34, 21.25]
theoretical  = [n * 10 for n in n_links]

pwm_steps = [
        {"label": "Без помех", "freq": 0,     "emi_mv": 1.2,  "throughput": 98.9, "loss": 0.50},
    {"label": "50 Гц",    "freq": 50,    "emi_mv": 4.1,  "throughput": 98.1, "loss": 0.82},
    {"label": "100 Гц",   "freq": 100,   "emi_mv": 6.3,  "throughput": 97.5, "loss": 1.15},
    {"label": "500 Гц",   "freq": 500,   "emi_mv": 9.8,  "throughput": 96.8, "loss": 1.73},
    {"label": "1 кГц",    "freq": 1000,  "emi_mv": 13.4, "throughput": 96.1, "loss": 2.21},
    {"label": "5 кГц",    "freq": 5000,  "emi_mv": 15.9, "throughput": 95.8, "loss": 2.95},
    {"label": "10 кГц",   "freq": 10000, "emi_mv": 17.1, "throughput": 95.6, "loss": 3.41},
    {"label": "50 кГц",   "freq": 50000, "emi_mv": 18.8, "throughput": 95.4, "loss": 3.50},
]
emi_vals     = np.array([s["emi_mv"]     for s in pwm_steps])
throughput_v = np.array([s["throughput"] for s in pwm_steps])
loss_v       = np.array([s["loss"]       for s in pwm_steps])
freq_v       = np.array([s["freq"]       for s in pwm_steps])
labels_v     = [s["label"] for s in pwm_steps]


# ══════════════════════════════════════════════════════════════════════
# Рис. 1: B(r)
# ══════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(8, 4.5))

mu0    = 4 * np.pi * 1e-7
I      = 9.09
r_cont = np.linspace(0.01, 0.22, 400)
B_cont = (mu0 * I / (2 * np.pi * r_cont)) * 1e6

ax.plot(r_cont * 100, B_cont, color=C1, linewidth=2,
        label=r"$B = \mu_0 I\,/\,(2\pi r)$,  $I = 9{,}09$ А")
ax.scatter(distances_cm[1:], B_uT[1:], color=C2, s=60, zorder=5,
           edgecolors="#333", linewidths=0.6,
           label="Расчётные значения (таблица расчёта)")

for d, b in zip(distances_cm[1:], B_uT[1:]):
    ax.annotate(f"{b} мкТл", (d, b),
                textcoords="offset points", xytext=(5, 4),
                fontsize=8, color="#333333")

ax.axvline(14, color=C3, linewidth=1.3, linestyle="--",
           label="Критич. расстояние UTP Cat 5e (14 см)")
ax.axvline(8,  color=C4, linewidth=1.3, linestyle="-.",
           label="Критич. расстояние STP Cat 5e (8 см)")

ax.set_xlabel("Расстояние от источника, см")
ax.set_ylabel("Магнитная индукция $B$, мкТл")
ax.set_title("Зависимость магнитной индукции от расстояния до источника помех")
ax.set_xlim(0, 22)
ax.set_ylim(0, 45)
ax.legend(loc="upper right")
plt.tight_layout()
plt.savefig("report_plots/Fig1_B_vs_distance.pdf")
plt.savefig("report_plots/Fig1_B_vs_distance.png")
plt.close()
print("[OK] Fig1_B_vs_distance")


# ══════════════════════════════════════════════════════════════════════
# Рис. 2: QoS throughput UTP vs STP
# ══════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(7, 4))

x = np.arange(len(conditions))
w = 0.35
b1 = ax.bar(x - w/2, utp_throughput, w, color=C1, alpha=0.85,
            label="UTP Cat 5e", edgecolor="#333", linewidth=0.5)
b2 = ax.bar(x + w/2, stp_throughput, w, color=C2, alpha=0.75,
            label="STP Cat 5e", edgecolor="#333", linewidth=0.5,
            hatch="//")

for bar in b1:
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.03,
            f"{bar.get_height():.2f}", ha="center", va="bottom", fontsize=8)
for bar in b2:
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.03,
            f"{bar.get_height():.2f}", ha="center", va="bottom", fontsize=8)

ax.set_xticks(x)
ax.set_xticklabels(conditions)
ax.set_ylabel("Пропускная способность, Мбит/с")
ax.set_title("Пропускная способность UTP и STP Cat 5e при воздействии ЭМП")
ax.set_ylim(94.5, 100.2)
ax.legend()
plt.tight_layout()
plt.savefig("report_plots/Fig2_throughput.pdf")
plt.savefig("report_plots/Fig2_throughput.png")
plt.close()
print("[OK] Fig2_throughput")


# ══════════════════════════════════════════════════════════════════════
# Рис. 3: Packet loss UTP vs STP
# ══════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(7, 4))

b1 = ax.bar(x - w/2, utp_loss, w, color=C1, alpha=0.85,
            label="UTP Cat 5e", edgecolor="#333", linewidth=0.5)
b2 = ax.bar(x + w/2, stp_loss, w, color=C2, alpha=0.75,
            label="STP Cat 5e", edgecolor="#333", linewidth=0.5,
            hatch="//")

for bar in [*b1, *b2]:
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.04,
            f"{bar.get_height():.3f}%", ha="center", va="bottom", fontsize=8)

ax.set_xticks(x)
ax.set_xticklabels(conditions)
ax.set_ylabel("Потеря пакетов, %")
ax.set_title("Потеря пакетов UTP и STP Cat 5e при воздействии ЭМП")
ax.set_ylim(0, 4.2)
ax.legend()
plt.tight_layout()
plt.savefig("report_plots/Fig3_packet_loss.pdf")
plt.savefig("report_plots/Fig3_packet_loss.png")
plt.close()
print("[OK] Fig3_packet_loss")


# ══════════════════════════════════════════════════════════════════════
# Рис. 4: Jitter UTP vs STP
# ══════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(7, 4))

b1 = ax.bar(x - w/2, utp_jitter, w, color=C1, alpha=0.85,
            label="UTP Cat 5e", edgecolor="#333", linewidth=0.5)
b2 = ax.bar(x + w/2, stp_jitter, w, color=C2, alpha=0.75,
            label="STP Cat 5e", edgecolor="#333", linewidth=0.5,
            hatch="//")

for bar in [*b1, *b2]:
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.00003,
            f"{bar.get_height():.4f}", ha="center", va="bottom", fontsize=8)

ax.set_xticks(x)
ax.set_xticklabels(conditions)
ax.set_ylabel("Джиттер, мкс")
ax.set_title("Джиттер UTP и STP Cat 5e при воздействии ЭМП")
ax.legend()
plt.tight_layout()
plt.savefig("report_plots/Fig4_jitter.pdf")
plt.savefig("report_plots/Fig4_jitter.png")
plt.close()
print("[OK] Fig4_jitter")


# ══════════════════════════════════════════════════════════════════════
# Рис. 5: AXT — throughput vs N кабелей
# ══════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(8, 4.5))

ax.plot(n_links, theoretical, color="#888888", linewidth=1.5,
        linestyle="--", marker="s", markersize=5,
        label="Теоретический максимум ($N \\times 10$ Гбит/с)")
ax.plot(n_links, total_speed, color=C1, linewidth=2,
        marker="o", markersize=7, markerfacecolor="white",
        markeredgewidth=1.5, label="Реальная скорость (iperf3)")
ax.fill_between(n_links, total_speed, theoretical,
                alpha=0.10, color=C2, label="Потери от AXT")

for n, ts in zip(n_links, total_speed):
    eta = ts / (n * 10) * 100
    ax.annotate(f"{eta:.0f}%", (n, ts),
                textcoords="offset points", xytext=(0, 7),
                fontsize=8, ha="center", color=C2)

ax.axvspan(2.5, 7.5, alpha=0.04, color=C2)
ax.text(3.2, 4, "Зона деградации\n(начиная с N = 3)",
        fontsize=8, color=C2, style="italic")

ax.set_xlabel("Число одновременно активных соединений $N$")
ax.set_ylabel("Пропускная способность, Гбит/с")
ax.set_title("Влияние плотности кабельной укладки (AXT) на суммарную пропускную способность\n"
             "Cat 5e UTP, 60 м, стандарт 10GBASE-T")
ax.set_xticks(n_links)
ax.set_ylim(0, 78)
ax.legend(loc="upper left")
plt.tight_layout()
plt.savefig("report_plots/Fig5_AXT.pdf")
plt.savefig("report_plots/Fig5_AXT.png")
plt.close()
print("[OK] Fig5_AXT")


# ══════════════════════════════════════════════════════════════════════
# Рис. 6: 3D — ЭМП × частота × packet loss
# ══════════════════════════════════════════════════════════════════════
fig = plt.figure(figsize=(9, 6))
ax  = fig.add_subplot(111, projection="3d")

log_freq = np.log10(freq_v + 1)
norm     = plt.Normalize(loss_v.min(), loss_v.max())
sc = ax.scatter(log_freq, emi_vals, loss_v,
                c=loss_v, cmap="RdYlGn_r", s=90,
                edgecolors="#333", linewidths=0.5, depthshade=False)

idx = np.argsort(emi_vals)
ax.plot(log_freq[idx], emi_vals[idx], loss_v[idx],
        color="#555555", linewidth=1.0, linestyle="--", alpha=0.6)

for xp, yp, zp, lb in zip(log_freq, emi_vals, loss_v, labels_v):
    ax.text(xp, yp, zp + 0.08, lb, fontsize=7.5, color="#222222")

ax.set_xlabel("log₁₀(f ШИМ + 1)", labelpad=8)
ax.set_ylabel("Уровень ЭМП, мВ",  labelpad=8)
ax.set_zlabel("Потеря пакетов, %", labelpad=8)
ax.set_title("Корреляция уровня ЭМП, частоты ШИМ-генератора\n"
             "и потери пакетов (UTP Cat 5e)", pad=14)

cbar = fig.colorbar(sc, ax=ax, shrink=0.5, pad=0.1)
cbar.set_label("Потеря пакетов, %")

ax.xaxis.pane.fill = False
ax.yaxis.pane.fill = False
ax.zaxis.pane.fill = False
ax.xaxis.pane.set_edgecolor("#cccccc")
ax.yaxis.pane.set_edgecolor("#cccccc")
ax.zaxis.pane.set_edgecolor("#cccccc")

plt.tight_layout()
plt.savefig("report_plots/Fig6_3D_loss.pdf")
plt.savefig("report_plots/Fig6_3D_loss.png")
plt.close()
print("[OK] Fig6_3D_loss")


# ══════════════════════════════════════════════════════════════════════
# Рис. 7: 3D — ЭМП × частота × throughput
# ══════════════════════════════════════════════════════════════════════
fig = plt.figure(figsize=(9, 6))
ax  = fig.add_subplot(111, projection="3d")

norm2 = plt.Normalize(throughput_v.min(), throughput_v.max())
sc2   = ax.scatter(log_freq, emi_vals, throughput_v,
                   c=throughput_v, cmap="RdYlGn", s=90,
                   edgecolors="#333", linewidths=0.5, depthshade=False)

ax.plot(log_freq[idx], emi_vals[idx], throughput_v[idx],
        color="#555555", linewidth=1.0, linestyle="--", alpha=0.6)

for xp, yp, zp, lb in zip(log_freq, emi_vals, throughput_v, labels_v):
    ax.text(xp, yp, zp + 0.05, lb, fontsize=7.5, color="#222222")

ax.set_xlabel("log₁₀(f ШИМ + 1)", labelpad=8)
ax.set_ylabel("Уровень ЭМП, мВ",  labelpad=8)
ax.set_zlabel("Пропускная способность, Мбит/с", labelpad=8)
ax.set_title("Корреляция уровня ЭМП, частоты ШИМ-генератора\n"
             "и пропускной способности (UTP Cat 5e)", pad=14)

cbar2 = fig.colorbar(sc2, ax=ax, shrink=0.5, pad=0.1)
cbar2.set_label("Пропускная способность, Мбит/с")

ax.xaxis.pane.fill = False
ax.yaxis.pane.fill = False
ax.zaxis.pane.fill = False
ax.xaxis.pane.set_edgecolor("#cccccc")
ax.yaxis.pane.set_edgecolor("#cccccc")
ax.zaxis.pane.set_edgecolor("#cccccc")

plt.tight_layout()
plt.savefig("report_plots/Fig7_3D_throughput.pdf")
plt.savefig("report_plots/Fig7_3D_throughput.png")
plt.close()
print("[OK] Fig7_3D_throughput")

print("\nГотово. Все файлы в ./report_plots/")
