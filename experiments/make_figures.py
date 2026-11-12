"""Journal figures (Springer JEET artwork rules).

Rules applied: no titles or captions inside figures, panel letters (a), (b), (c) only,
Arial-metric sans-serif font (Liberation Sans) at a uniform 8 pt, lines >= 0.3 pt,
patterns/markers in addition to colour, 174 mm single-column width, 600 dpi,
files named Fig1 ... Fig6 (TIFF for submission, PNG for the Word file, PDF vector).
Graphics program: Python 3 / Matplotlib.
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
from otgfr.network import build_network, ZONES, TIES_CLOSED

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
F = os.path.join(R, "figures")
os.makedirs(F, exist_ok=True)
MM = 1 / 25.4
W = 174 * MM
FS = 8
C = dict(otg="#2a78d6", local_soc="#eb6834", telecom="#1baf7a", local_rating="#eda100", dp="#6250d6",
         ref="#52514e", grid="#e4e3df", ink="#000000", ink2="#333333")
ZC = ["#dceafa", "#fde3d6", "#d7f2e6", "#fbefcc"]
ZH = ["///", "\\\\\\", "...", "xx"]
plt.rcParams.update({"font.family": "Liberation Sans", "font.size": FS, "axes.titlesize": FS, "axes.labelsize": FS,
                     "xtick.labelsize": FS, "ytick.labelsize": FS, "legend.fontsize": FS - 1, "axes.linewidth": 0.6,
                     "axes.edgecolor": C["ink2"], "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": C["grid"], "grid.linewidth": 0.4, "lines.linewidth": 1.4,
                     "legend.frameon": False, "hatch.linewidth": 0.5, "mathtext.fontset": "custom",
                     "mathtext.rm": "Liberation Sans", "mathtext.it": "Liberation Sans:italic"})


def save(fig, n):
    for ext, kw in [("png", dict(dpi=600)), ("tif", dict(dpi=600, pil_kwargs={"compression": "tiff_lzw"})), ("pdf", {})]:
        fig.savefig(os.path.join(F, f"Fig{n}.{ext}"), bbox_inches="tight", **kw)
    plt.close(fig)


def panel(ax, letter, x=-0.16, y=1.04):
    ax.text(x, y, f"({letter})", transform=ax.transAxes, fontsize=FS, fontweight="bold", va="bottom")


# ---------------------------------------------------------------- Fig. 1 system single-line diagram
def fig1_system():
    net = build_network()
    pos = {}
    for b in range(18):
        pos[b] = (b * 1.0, 0.0)
    for i, b in enumerate(range(18, 22)):
        pos[b] = (1 + i * 1.0, -1.6)
    for i, b in enumerate(range(22, 25)):
        pos[b] = (2 + i * 1.0, 2.2)
    for i, b in enumerate(range(25, 33)):
        pos[b] = (5 + (i + 1) * 1.0, -3.2)
    edges = [(i, i + 1) for i in range(17)] + [(1, 18), (18, 19), (19, 20), (20, 21), (2, 22), (22, 23), (23, 24),
                                                 (5, 25)] + [(i, i + 1) for i in range(25, 32)]
    fig, ax = plt.subplots(figsize=(W, 3.0))
    ax.axis("off"); ax.grid(False)
    zone_of = net["zone_of"]
    for k, (name, z) in enumerate(ZONES.items()):
        xs = [pos[b][0] for b in z["buses"]]; ys = [pos[b][1] for b in z["buses"]]
        top = 0.5 if k == 3 else 0.0   # room for the zone-4 bus labels drawn above the buses
        ax.add_patch(FancyBboxPatch((min(xs) - 0.45, min(ys) - 0.55), max(xs) - min(xs) + 0.9, max(ys) - min(ys) + 1.1 + top,
                                    boxstyle="round,pad=0.02,rounding_size=0.25", fc=ZC[k], ec=C["ink2"], lw=0.6,
                                    hatch=ZH[k], alpha=0.55, zorder=0))
        if k == 3:
            ax.text(max(xs) + 0.65, min(ys) + 0.25, f"Zone {k+1}", fontsize=FS, fontweight="bold", va="center")
        else:
            ax.text(min(xs) - 0.35, max(ys) + 0.62, f"Zone {k+1}", fontsize=FS, fontweight="bold", va="bottom")
    for a, b in edges:
        ax.plot([pos[a][0], pos[b][0]], [pos[a][1], pos[b][1]], color=C["ink"], lw=1.0, zorder=1)
    for a, b in TIES_CLOSED:
        (x1, y1), (x2, y2) = pos[a], pos[b]
        yb = -4.15
        ax.plot([x1, x1 + 0.45, x1 + 0.45, x2, x2], [y1, y1, yb, yb, y2], color=C["ink"], lw=1.0, ls="--", zorder=1)
    crit = {3: "H", 6: "S", 29: "W"}
    for b, (x, y) in pos.items():
        ax.plot(x, y, "o", ms=4.5, mfc="white", mec=C["ink"], mew=0.8, zorder=3)
        if b >= 25:   # zone 4: labels above the bus so tie lines can enter from below
            ax.text(x - 0.12, y + 0.3, str(b + 1), ha="right", va="bottom", fontsize=FS - 1.5)
        else:
            ax.text(x - 0.1 if b == 5 else x + 0.1, y - 0.42, str(b + 1), ha="right" if b == 5 else ("left" if b in (1, 2) else "center"), va="top", fontsize=FS - 1.5)
        if b in crit:
            dx, dy = (0.42, -0.42) if b >= 25 else (0.38, 0.38)
            ax.plot(x + dx, y + dy, marker="*", ms=8, mfc=C["ink"], mec=C["ink"], zorder=4)
    for k, z in enumerate(ZONES.values()):
        x, y = pos[z["gfm"]]
        ax.add_patch(Rectangle((x - 0.32, y + 0.75), 0.64, 0.42, fc="white", ec=C["otg"], lw=1.0, zorder=4))
        ax.text(x, y + 0.96, "GFM", ha="center", va="center", fontsize=FS - 2, zorder=5)
        ax.plot([x, x], [y, y + 0.75], color=C["otg"], lw=1.0, zorder=2)
    x0, y0 = pos[0]
    ax.plot([x0 - 0.9, x0], [y0, y0], color=C["ink"], lw=1.0)
    ax.plot([x0 - 0.75, x0 - 0.45], [y0 - 0.22, y0 + 0.22], color="#c00000", lw=1.6)
    ax.plot([x0 - 0.75, x0 - 0.45], [y0 + 0.22, y0 - 0.22], color="#c00000", lw=1.6)
    ax.text(x0 - 0.95, y0 + 0.3, "Substation\n(lost)", ha="center", va="bottom", fontsize=FS - 1.5)
    # legend
    lx, ly = -1.3, -2.75
    ax.plot([lx, lx + 0.6], [ly, ly], color=C["ink"], lw=1.0); ax.text(lx + 0.75, ly, "Line", va="center", fontsize=FS - 1)
    ax.plot([lx, lx + 0.6], [ly - 0.5, ly - 0.5], color=C["ink"], lw=1.0, ls="--"); ax.text(lx + 0.75, ly - 0.5, "Closed tie line", va="center", fontsize=FS - 1)
    ax.add_patch(Rectangle((lx + 0.1, ly - 1.15), 0.4, 0.3, fc="white", ec=C["otg"], lw=1.0))
    ax.text(lx + 0.75, ly - 1.0, "Grid-forming BESS + PV", va="center", fontsize=FS - 1)
    ax.plot(lx + 0.3, ly - 1.5, marker="*", ms=8, color=C["ink"]); ax.text(lx + 0.75, ly - 1.5, "Critical load", va="center", fontsize=FS - 1)
    ax.set_xlim(-1.6, 18.3); ax.set_ylim(-4.5, 3.4); ax.set_aspect("equal")
    save(fig, 1)


# ---------------------------------------------------------------- Fig. 2 architecture block diagram
def box(ax, x, y, w, h, text, fc, ec, fs=FS - 1, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.015", fc=fc, ec=ec, lw=0.8))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal")


def arrow(ax, a, b, color=C["ink2"], lw=0.9, ls="-"):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=7, color=color, lw=lw, ls=ls))


def fig2_architecture():
    fig, ax = plt.subplots(figsize=(W, 4.1)); ax.set_xlim(0, 1); ax.set_ylim(0.04, 0.95); ax.axis("off"); ax.grid(False)
    for i in range(4):
        x = 0.02 + i * 0.245
        ax.add_patch(FancyBboxPatch((x, 0.50), 0.225, 0.43, boxstyle="round,pad=0.005,rounding_size=0.02",
                                    fc="#f4f8fd", ec=C["otg"], lw=0.8))
        ax.text(x + 0.1125, 0.905, f"Zone {i+1}" if i < 3 else "Zone N", ha="center", fontweight="bold")
        box(ax, x + 0.01, 0.79, 0.205, 0.085, "Local telemetry\n(load, PV, SoE)", "white", C["ink2"])
        box(ax, x + 0.01, 0.69, 0.205, 0.085, "CLPU learner and\nzone planner", "white", C["ink2"])
        box(ax, x + 0.01, 0.59, 0.205, 0.085, "Walsh code\nencoder", "white", C["otg"])
        box(ax, x + 0.01, 0.51, 0.205, 0.07, "GFM inverter\nP–f droop + pilot", "#dceafa", C["otg"])
        for y0, y1 in [(0.79, 0.775), (0.69, 0.675), (0.59, 0.58)]:
            arrow(ax, (x + 0.1125, y0), (x + 0.1125, y1))
        arrow(ax, (x + 0.14, 0.51), (x + 0.14, 0.415), C["otg"], lw=1.1)
        arrow(ax, (x + 0.08, 0.415), (x + 0.08, 0.51), C["dp"], lw=1.0, ls="--")
    ax.text(0.15, 0.455, "pilot", fontsize=FS - 1); ax.text(0.03, 0.455, "frequency", fontsize=FS - 1)
    ax.add_patch(FancyBboxPatch((0.02, 0.28), 0.96, 0.13, boxstyle="round,pad=0.005,rounding_size=0.02",
                                fc="#eef7f1", ec=C["telecom"], lw=1.0, hatch="...", alpha=0.9))
    ax.text(0.5, 0.375, "Energized island acting as an analogue aggregation server", ha="center", fontweight="bold")
    ax.text(0.5, 0.315, r"$\Delta\omega(t) = [\,\Sigma_k\, p_k(t) + \Delta P_{\mathrm{base}}(t)\,]\,/\,\Sigma_k D_k$",
            ha="center", fontsize=FS + 1)
    box(ax, 0.02, 0.07, 0.30, 0.15, "Ratio coded decoding\n" r"$y_m = L^{-1}\Sigma_t\, c_m(t)\,\Delta\omega(t)$" "\n"
        r"$\hat{x} = y_{\mathrm{num}}\,/\,y_{\mathrm{den}}$", "#f4f2fd", C["dp"])
    box(ax, 0.35, 0.07, 0.30, 0.15, "Island-wide quantities\nenergy surplus, head-room,\nrequests, fused CLPU model",
        "#f4f2fd", C["dp"])
    box(ax, 0.68, 0.07, 0.30, 0.15, "Zone update\nenergy price, CLPU estimate,\npriority pick-up", "#f4f8fd", C["otg"])
    arrow(ax, (0.17, 0.28), (0.17, 0.22), C["dp"], lw=1.1)
    arrow(ax, (0.32, 0.145), (0.35, 0.145)); arrow(ax, (0.65, 0.145), (0.68, 0.145))
    ax.annotate("", xy=(0.995, 0.71), xytext=(0.985, 0.145),
                arrowprops=dict(arrowstyle="-|>", color=C["otg"], lw=1.0, connectionstyle="arc3,rad=0.25"))
    save(fig, 2)


# ---------------------------------------------------------------- Fig. 3 channel validation
def fig3_channel():
    e1 = json.load(open(os.path.join(R, "exp1_channel_validation.json")))
    e2 = json.load(open(os.path.join(R, "exp2_time_domain.json")))
    fig, axs = plt.subplots(1, 3, figsize=(W, 2.3))
    pr = np.array(e1["ac_amplitude"]["10kW"]["pairs"])
    ax = axs[0]
    ax.plot([-1, 1], [-1, 1], color=C["ref"], lw=0.8, ls="--")
    ax.scatter(pr[:, 0], pr[:, 1], s=10, color=C["otg"], marker="o", label="Mean", edgecolor="white", lw=0.3)
    ax.scatter(pr[:, 2], pr[:, 3], s=10, color=C["local_soc"], marker="s", label="Weighted mean", edgecolor="white", lw=0.3)
    ax.set_xlabel("True aggregate"); ax.set_ylabel("Decoded aggregate"); ax.legend(loc="upper left")
    panel(ax, "a", -0.24)
    ax = axs[1]
    Ls = [int(k) for k in e1["lin_length"]]
    ax.plot(Ls, [e1["lin_length"][str(l)]["mean"]["rmse"] for l in Ls], "-o", color=C["otg"], ms=4, label="Code length")
    ax.set_xscale("log", base=2); ax.set_yscale("log")
    ax.set_xlabel("Code length L (chips)"); ax.set_ylabel("RMSE")
    panel(ax, "b", -0.24)
    ax = axs[2]
    tc = sorted(e2["sweep"], key=float)
    ax.plot([float(t) for t in tc], [e2["sweep"][t]["rmse"] for t in tc], "-o", color=C["otg"], ms=4, label="RMSE")
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("Chip duration (s)"); ax.set_ylabel("Transient RMSE")
    ax2 = ax.twinx(); ax2.grid(False); ax2.spines["right"].set_visible(True)
    ax2.plot([float(t) for t in tc], [e2["sweep"][t]["peak_df_mhz"] for t in tc], "--s", color=C["local_soc"], ms=4,
             label="Peak excursion")
    ax2.set_ylabel("Peak excursion (mHz)")
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, fontsize=FS - 1.5)
    panel(ax, "c", -0.24)
    fig.tight_layout(w_pad=1.6); save(fig, 3)


# ---------------------------------------------------------------- Fig. 4 restoration outcomes
def fig4_outcomes():
    S = json.load(open(os.path.join(R, "exp3_restoration.json")))["summary"]
    fig, axs = plt.subplots(1, 3, figsize=(W, 2.5), gridspec_kw=dict(width_ratios=[1.15, 1.15, 1.3]))
    names = [("local_rating", "Local\nrating", C["local_rating"], "//"), ("local_soc", "Local\nSoC", C["local_soc"], "\\\\"),
             ("telecom_p0.90", "Tel.\np = 0.9", C["telecom"], ".."), ("otg", "OTG\nFR", C["otg"], ""),
             ("full_info", "Full\ninfo", C["ref"], "xx")]
    for ax, key, lab, scale, letter in [(axs[0], "pwes_rel_pct", "PWES (% of full information)", 1, "a"),
                                        (axs[1], "crit_frac", "Critical energy served (%)", 100, "b")]:
        for i, (n, t, c, h) in enumerate(names):
            m, lo, hi = [v * scale for v in S[n][key]]
            ax.bar(i, m, color=c, width=0.7, edgecolor="black", lw=0.4, hatch=h)
            ax.errorbar(i, m, yerr=[[m - lo], [hi - m]], color=C["ink"], lw=0.7, capsize=2)
            ax.text(i, hi + 0.8, f"{m:.1f}", ha="center", fontsize=FS - 1.5)
        ax.set_xticks(range(len(names))); ax.set_xticklabels([t for _, t, _, _ in names], fontsize=FS - 1.5)
        ax.set_ylim(60, 106); ax.set_ylabel(lab); panel(ax, letter, -0.22)
    ax = axs[2]
    ps = [0.0, 0.25, 0.5, 0.75, 0.9, 1.0]
    m = np.array([S[f"telecom_p{p:.2f}"]["pwes_rel_pct"] for p in ps])
    ax.fill_between(ps, m[:, 1], m[:, 2], color=C["telecom"], alpha=0.25, lw=0)
    ax.plot(ps, m[:, 0], "-o", color=C["telecom"], ms=4, label="Telecom FL")
    o = S["otg"]["pwes_rel_pct"]
    ax.axhline(o[0], color=C["otg"], lw=1.6, label="OTG-FR (no telecom)")
    ax.axhline(S["local_soc"]["pwes_rel_pct"][0], color=C["local_soc"], lw=1.2, ls="--", label="Local SoC droop")
    ax.set_xlabel("Telecom link availability p"); ax.set_ylabel("PWES (%)"); ax.set_ylim(70, 104)
    ax.legend(loc="center left", bbox_to_anchor=(0.0, 0.62)); panel(ax, "c", -0.22)
    fig.tight_layout(w_pad=1.2); save(fig, 4)


# ---------------------------------------------------------------- Fig. 5 traces
def fig5_traces():
    s0 = json.load(open(os.path.join(R, "exp3_restoration.json")))["per_scenario"][0]
    hrs = 18 + 0.25 * np.arange(96)
    fig, axs = plt.subplots(1, 3, figsize=(W, 2.2))
    for n, lab, c, ls in [("full_info", "Full information", C["ref"], "-"), ("local_soc", "Local SoC droop", C["local_soc"], "--"),
                          ("otg", "OTG-FR", C["otg"], "-")]:
        tr = s0[n]["trace"]
        axs[0].plot(hrs, tr["served_mw"], color=c, ls=ls, lw=1.1, label=lab)
        axs[1].plot(hrs, tr["lam"], color=c, ls=ls, lw=1.1, label=lab)
        axs[2].plot(hrs, np.mean(tr["soe"], axis=1) * 100, color=c, ls=ls, lw=1.1, label=lab)
    axs[0].set_ylabel("Served load (MW)"); axs[1].set_ylabel("Energy price λ"); axs[1].set_yscale("log")
    axs[2].set_ylabel("Mean SoE (%)")
    for a, l in zip(axs, "abc"):
        a.set_xlabel("Time of day (h)"); a.set_xticks([18, 24, 30, 36, 42]); a.set_xticklabels(["18", "00", "06", "12", "18"])
        panel(a, l, -0.24)
    axs[0].legend(loc="upper center")
    fig.tight_layout(w_pad=1.4); save(fig, 5)


# ---------------------------------------------------------------- Fig. 6 robustness and scaling
def fig6_robust():
    S = json.load(open(os.path.join(R, "exp3_restoration.json")))["summary"]
    e4 = json.load(open(os.path.join(R, "exp4_scaling_robustness.json")))
    fig, axs = plt.subplots(1, 3, figsize=(W, 2.2))
    ax = axs[0]
    keys = ["otg", "otg_dp0.05", "otg_dp0.10", "otg_dp0.20"]; xs = [0, 0.05, 0.1, 0.2]
    ax.plot(xs, [S[k]["pwes_rel_pct"][0] for k in keys], "-o", color=C["dp"], ms=4, label="PWES")
    ax.plot(xs, [S[k]["crit_frac"][0] * 100 for k in keys], "--s", color=C["otg"], ms=4, label="Critical served")
    ax.set_xlabel("Dither σ (code units)"); ax.set_ylabel("Percentage (%)"); ax.set_ylim(85, 101); ax.legend(loc="lower left")
    panel(ax, "a", -0.24)
    ax = axs[1]
    keys = ["otg", "otg_noise1%", "otg_noise2%"]
    ax.bar(range(3), [S[k]["pwes_rel_pct"][0] for k in keys], color=C["otg"], width=0.6, edgecolor="black", lw=0.4, hatch="//")
    ax.axhline(S["local_soc"]["pwes_rel_pct"][0], color=C["local_soc"], ls="--", lw=1.1, label="Local SoC droop")
    ax.set_xticks(range(3)); ax.set_xticklabels(["0.5", "1.0", "2.0"]); ax.set_ylim(75, 100)
    ax.set_xlabel("Chip-level load noise (%)"); ax.set_ylabel("PWES (%)"); ax.legend(loc="upper right")
    panel(ax, "b", -0.24)
    ax = axs[2]
    Ns = [int(n) for n in e4["scaling"]]
    ax.plot(Ns, [e4["scaling"][str(n)]["mae_mean"] for n in Ns], "-o", color=C["otg"], ms=4, label="OTG-FR MAE")
    ax.set_xscale("log", base=2); ax.set_xlabel("Number of zones N"); ax.set_ylabel("MAE (code units)"); ax.set_ylim(0, 0.2)
    ax2 = ax.twinx(); ax2.grid(False); ax2.spines["right"].set_visible(True)
    ax2.plot(Ns, [128] * len(Ns), color=C["otg"], lw=1.0, ls=":", label="OTG-FR round")
    ax2.plot(Ns, [2 * n for n in Ns], color=C["telecom"], lw=1.2, ls="--", marker="^", ms=3.5, label="Polled telecom round")
    ax2.set_ylabel("Round time (s)"); ax2.set_yscale("log", base=2); ax2.set_ylim(2 ** 2, 2 ** 10)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=FS - 2)
    panel(ax, "c", -0.24)
    fig.tight_layout(w_pad=1.4); save(fig, 6)


if __name__ == "__main__":
    fig1_system(); fig2_architecture(); fig3_channel(); fig4_outcomes(); fig5_traces(); fig6_robust()
    print("written", F)
