"""SisFall EDA — run before training to understand the data.

Usage (from project root):
    uv run --project AI_ML/fall_detection python AI_ML/fall_detection/eda.py

Plots are saved to AI_ML/fall_detection/eda_plots/  (git-ignored).
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless — no display needed
import matplotlib.pyplot as plt
import numpy as np

# ── paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DEFAULT = ROOT / "archive (2)" / "SisFall_dataset"
OUT_DIR = Path(__file__).resolve().parent / "eda_plots"

# ── physical-unit conversion (bits → SI) ─────────────────────────────────────
# ADXL345: ±16 g, 13-bit  → 32/8192 ≈ 0.003906 g/bit
# ITG3200:  ±2000 °/s, 16-bit → 4000/65536 ≈ 0.06104 °/s/bit
ADXL_SCALE = (2 * 16) / (2**13)
ITG_SCALE = (2 * 2000) / (2**16)

COL_NAMES = [
    "Accel X (g)",
    "Accel Y (g)",
    "Accel Z (g)",
    "Gyro X (°/s)",
    "Gyro Y (°/s)",
    "Gyro Z (°/s)",
]

FALL_CODES = {f"F{i:02d}" for i in range(1, 16)}  # F01–F15
ADL_CODES = {f"D{i:02d}" for i in range(1, 20)}  # D01–D19

FALL_LABELS = {
    "F01": "Forward slip",
    "F02": "Backward slip",
    "F03": "Lateral slip",
    "F04": "Forward trip",
    "F05": "Jogging trip",
    "F06": "Fainting (vert)",
    "F07": "Fainting (table)",
    "F08": "Getting up fwd",
    "F09": "Getting up lat",
    "F10": "Sitting fwd",
    "F11": "Sitting bwd",
    "F12": "Sitting lat",
    "F13": "Seated faint fwd",
    "F14": "Seated faint bwd",
    "F15": "Seated faint lat",
}
ADL_LABELS = {
    "D01": "Walk slow",
    "D02": "Walk fast",
    "D03": "Jog slow",
    "D04": "Jog fast",
    "D05": "Stairs slow",
    "D06": "Stairs fast",
    "D07": "Sit half slow",
    "D08": "Sit half fast",
    "D09": "Sit low slow",
    "D10": "Sit low fast",
    "D11": "Collapse to chair",
    "D12": "Lie slow",
    "D13": "Lie fast",
    "D14": "Lateral roll",
    "D15": "Kneel bend",
    "D16": "Bend no knees",
    "D17": "Get in car",
    "D18": "Stumble",
    "D19": "Jump",
}


# ── helpers ───────────────────────────────────────────────────────────────────


def parse_file(path: Path) -> np.ndarray | None:
    """Parse one SisFall .txt file → float32 array (N, 6) in SI units.

    Rows look like:  17,-179, -99, -18,-504,-352,  76,-697,-279;
    We take cols 0-5 (ADXL345 accel + ITG3200 gyro) — MPU-6050 compatible.
    """
    rows = []
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip().rstrip(";")
        if not line:
            continue
        try:
            vals = [float(v) for v in line.split(",")]
        except ValueError:
            continue
        if len(vals) == 9:
            rows.append(vals[:6])
    if not rows:
        return None
    arr = np.array(rows, dtype=np.float32)
    arr[:, :3] *= ADXL_SCALE
    arr[:, 3:] *= ITG_SCALE
    return arr


def load_dataset(dataset_root: Path) -> list[dict]:
    """Scan all subject sub-dirs and return list of record dicts."""
    records = []
    for subject_dir in sorted(dataset_root.iterdir()):
        if not subject_dir.is_dir():
            continue
        subject = subject_dir.name  # SA01, SE06, …
        for fpath in sorted(subject_dir.glob("*.txt")):
            parts = fpath.stem.split("_")  # e.g. ['F05', 'SA01', 'R04']
            if len(parts) < 3:
                continue
            code, trial = parts[0], parts[2]
            is_fall = code.startswith("F")
            data = parse_file(fpath)
            if data is None:
                continue
            records.append(
                {
                    "path": fpath,
                    "code": code,
                    "subject": subject,
                    "trial": trial,
                    "is_fall": is_fall,
                    "data": data,
                    "length": len(data),
                }
            )
    return records


# ── plots ─────────────────────────────────────────────────────────────────────


def plot_class_distribution(records: list[dict], out: Path) -> None:
    """Bar chart: files per activity code, falls in red, ADL in blue."""
    from collections import Counter

    counts = Counter(r["code"] for r in records)

    fall_codes = sorted([c for c in counts if c.startswith("F")])
    adl_codes = sorted([c for c in counts if c.startswith("D")])

    fig, axes = plt.subplots(1, 2, figsize=(16, 5))
    fig.suptitle("SisFall — Files per Activity Code", fontsize=14, fontweight="bold")

    for ax, codes, title, color in [
        (axes[0], fall_codes, "Falls  (F01–F15)", "#e74c3c"),
        (axes[1], adl_codes, "ADL   (D01–D19)", "#3498db"),
    ]:
        vals = [counts[c] for c in codes]
        bars = ax.bar(codes, vals, color=color, edgecolor="white", linewidth=0.5)
        ax.set_title(title, fontsize=12)
        ax.set_xlabel("Activity code")
        ax.set_ylabel("Number of files")
        ax.set_ylim(0, max(vals) * 1.2)
        for bar, v in zip(bars, vals):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.3,
                str(v),
                ha="center",
                va="bottom",
                fontsize=8,
            )
        ax.tick_params(axis="x", rotation=45)

    plt.tight_layout()
    fig.savefig(out / "01_class_distribution.png", dpi=120)
    plt.close(fig)
    print("  saved 01_class_distribution.png")


def plot_signal_lengths(records: list[dict], out: Path) -> None:
    """Histogram of recording lengths (rows @ 200 Hz), split by label."""
    falls = [r["length"] for r in records if r["is_fall"]]
    adls = [r["length"] for r in records if not r["is_fall"]]

    fig, ax = plt.subplots(figsize=(10, 4))
    bins = np.linspace(0, max(falls + adls) + 100, 50)
    ax.hist(adls, bins=bins, alpha=0.7, label=f"ADL  (n={len(adls)})", color="#3498db")
    ax.hist(
        falls, bins=bins, alpha=0.7, label=f"Fall (n={len(falls)})", color="#e74c3c"
    )
    ax.set_title("Signal Length Distribution (samples @ 200 Hz)", fontsize=13)
    ax.set_xlabel("Number of samples")
    ax.set_ylabel("Count")
    ax.legend()

    # annotate seconds axis on top
    ax2 = ax.twiny()
    ax2.set_xlim(np.array(ax.get_xlim()) / 200)
    ax2.set_xlabel("Duration (seconds)")

    plt.tight_layout()
    fig.savefig(out / "02_signal_lengths.png", dpi=120)
    plt.close(fig)
    print("  saved 02_signal_lengths.png")


def plot_sample_waveforms(records: list[dict], out: Path) -> None:
    """Side-by-side: 6-channel waveform for one fall and one ADL."""
    fall_ex = next(r for r in records if r["code"] == "F06")  # fainting — dramatic
    adl_ex = next(r for r in records if r["code"] == "D02")  # fast walk

    fig, axes = plt.subplots(6, 2, figsize=(14, 12), sharex=False)
    fig.suptitle(
        "Sample Waveforms — Fall (F06 fainting) vs ADL (D02 fast walk)",
        fontsize=13,
        fontweight="bold",
    )

    titles = [
        f"{fall_ex['code']} — {FALL_LABELS[fall_ex['code']]} "
        f"({fall_ex['subject']}, {fall_ex['trial']})",
        f"{adl_ex['code']} — {ADL_LABELS[adl_ex['code']]} "
        f"({adl_ex['subject']}, {adl_ex['trial']})",
    ]

    for col_idx, (rec, title, color) in enumerate(
        [
            (fall_ex, titles[0], "#e74c3c"),
            (adl_ex, titles[1], "#3498db"),
        ]
    ):
        t = np.arange(len(rec["data"])) / 200.0
        axes[0, col_idx].set_title(title, fontsize=10)
        for ch in range(6):
            axes[ch, col_idx].plot(t, rec["data"][:, ch], color=color, linewidth=0.7)
            axes[ch, col_idx].set_ylabel(COL_NAMES[ch], fontsize=8)
            axes[ch, col_idx].tick_params(labelsize=7)
            if ch == 5:
                axes[ch, col_idx].set_xlabel("Time (s)", fontsize=8)

    plt.tight_layout()
    fig.savefig(out / "03_sample_waveforms.png", dpi=120)
    plt.close(fig)
    print("  saved 03_sample_waveforms.png")


def plot_channel_stats(records: list[dict], out: Path) -> None:
    """Mean ± std per channel, comparing falls vs ADL (per-window mean)."""
    fall_means = [r["data"].mean(axis=0) for r in records if r["is_fall"]]
    adl_means = [r["data"].mean(axis=0) for r in records if not r["is_fall"]]
    fall_arr = np.array(fall_means)  # (N_falls, 6)
    adl_arr = np.array(adl_means)  # (N_adl, 6)

    x = np.arange(6)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(
        "Per-Channel Statistics — Fall vs ADL (mean of recording means)",
        fontsize=13,
        fontweight="bold",
    )

    for ax, arr, label, color in [
        (axes[0], fall_arr, "Falls", "#e74c3c"),
        (axes[1], adl_arr, "ADL", "#3498db"),
    ]:
        means = arr.mean(axis=0)
        stds = arr.std(axis=0)
        ax.bar(
            x,
            means,
            width=0.6,
            yerr=stds,
            capsize=4,
            color=color,
            alpha=0.8,
            label=label,
        )
        ax.set_xticks(x)
        ax.set_xticklabels(COL_NAMES, rotation=30, ha="right", fontsize=9)
        ax.set_title(f"{label} (n={len(arr)})", fontsize=11)
        ax.set_ylabel("Mean value")
        ax.axhline(0, color="black", linewidth=0.5, linestyle="--")

    plt.tight_layout()
    fig.savefig(out / "04_channel_stats.png", dpi=120)
    plt.close(fig)
    print("  saved 04_channel_stats.png")


def plot_accel_magnitude(records: list[dict], out: Path) -> None:
    """Violin: peak accel magnitude (||accel||_2) per file, fall vs ADL."""

    def peak_mag(r):
        mag = np.linalg.norm(r["data"][:, :3], axis=1)
        return float(mag.max())

    fall_peaks = [peak_mag(r) for r in records if r["is_fall"]]
    adl_peaks = [peak_mag(r) for r in records if not r["is_fall"]]

    fig, ax = plt.subplots(figsize=(7, 6))
    parts = ax.violinplot(
        [adl_peaks, fall_peaks], positions=[1, 2], showmedians=True, showextrema=True
    )
    for pc, color in zip(parts["bodies"], ["#3498db", "#e74c3c"]):
        pc.set_facecolor(color)
        pc.set_alpha(0.7)

    ax.set_xticks([1, 2])
    ax.set_xticklabels(["ADL", "Fall"], fontsize=12)
    ax.set_ylabel("Peak ||accel|| (g)", fontsize=11)
    ax.set_title("Peak Acceleration Magnitude Distribution", fontsize=13)

    med_adl = np.median(adl_peaks)
    med_fall = np.median(fall_peaks)
    ax.annotate(
        f"median={med_adl:.2f}g",
        xy=(1, med_adl),
        xytext=(1.15, med_adl + 0.5),
        fontsize=9,
    )
    ax.annotate(
        f"median={med_fall:.2f}g",
        xy=(2, med_fall),
        xytext=(2.05, med_fall + 0.5),
        fontsize=9,
    )

    plt.tight_layout()
    fig.savefig(out / "05_accel_magnitude.png", dpi=120)
    plt.close(fig)
    print("  saved 05_accel_magnitude.png")


# ── text report ───────────────────────────────────────────────────────────────


def print_report(records: list[dict]) -> None:
    from collections import Counter

    total = len(records)
    n_fall = sum(r["is_fall"] for r in records)
    n_adl = total - n_fall
    lengths = [r["length"] for r in records]

    # NaN check
    nan_files = [r["path"].name for r in records if np.isnan(r["data"]).any()]

    print("\n" + "=" * 60)
    print("  SisFall Dataset — EDA Summary")
    print("=" * 60)
    print(f"  Total files      : {total}")
    print(f"  Falls            : {n_fall}  ({n_fall/total*100:.1f}%)")
    print(f"  ADL (non-falls)  : {n_adl}  ({n_adl/total*100:.1f}%)")
    print(f"  Files with NaN   : {len(nan_files)}")
    if nan_files:
        for f in nan_files[:5]:
            print(f"    >> {f}")
    print()
    print("  Signal length (samples @ 200 Hz)")
    print(f"    min  : {min(lengths)}  ({min(lengths)/200:.1f}s)")
    print(f"    max  : {max(lengths)}  ({max(lengths)/200:.1f}s)")
    print(f"    mean : {np.mean(lengths):.0f}  ({np.mean(lengths)/200:.1f}s)")
    print(f"    std  : {np.std(lengths):.0f}")
    print()

    # per-code file count
    counts = Counter(r["code"] for r in records)
    print("  Fall files per code:")
    for code in sorted(FALL_CODES):
        if code in counts:
            print(f"    {code} ({FALL_LABELS[code]:<28}) : {counts[code]}")
    print()
    print("  ADL files per code:")
    for code in sorted(ADL_CODES):
        if code in counts:
            print(f"    {code} ({ADL_LABELS[code]:<28}) : {counts[code]}")

    # Subject breakdown
    subj_types = Counter(
        "SA" if r["subject"].startswith("SA") else "SE" for r in records
    )
    print()
    print(
        f"  Subjects: SA (young adults) = {subj_types['SA']} files, "
        f"SE (elderly) = {subj_types['SE']} files"
    )
    print("=" * 60)
    print()


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dataset",
        type=Path,
        default=DATASET_DEFAULT,
        help="Path to SisFall_dataset root folder",
    )
    args = ap.parse_args()

    if not args.dataset.exists():
        print(f"Dataset not found: {args.dataset}")
        print("Pass --dataset <path> to override.")
        raise SystemExit(1)

    OUT_DIR.mkdir(exist_ok=True)
    print(f"Loading dataset from: {args.dataset}")
    records = load_dataset(args.dataset)
    print(f"Loaded {len(records)} recordings.\n")

    print_report(records)

    print("Generating plots...")
    plot_class_distribution(records, OUT_DIR)
    plot_signal_lengths(records, OUT_DIR)
    plot_sample_waveforms(records, OUT_DIR)
    plot_channel_stats(records, OUT_DIR)
    plot_accel_magnitude(records, OUT_DIR)

    print(f"\nAll plots saved to: {OUT_DIR}")


if __name__ == "__main__":
    main()
