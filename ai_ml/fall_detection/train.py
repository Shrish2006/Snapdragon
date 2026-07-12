"""SisFall fall detection — 1D-CNN training pipeline.

Full flow:
  load SisFall → sliding windows → subject-wise split → normalise
  → train FallCNN (PyTorch) → post-training report → export ONNX

Run from project root:
    uv run --project AI_ML/fall_detection python AI_ML/fall_detection/train.py

Outputs (all git-ignored):
    AI_ML/fall_detection/models/fall_detection.onnx
    AI_ML/fall_detection/models/scaler.npz
    AI_ML/fall_detection/training_plots/01_loss_accuracy.png
    AI_ML/fall_detection/training_plots/02_confusion_matrix.png
    AI_ML/fall_detection/training_plots/03_roc_curve.png
    AI_ML/fall_detection/training_plots/04_precision_recall.png
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from eda import load_dataset, DATASET_DEFAULT

MODELS_DIR = HERE / "models"
PLOTS_DIR  = HERE / "training_plots"

# ── hyper-parameters ──────────────────────────────────────────────────────────
WINDOW   = 200    # samples (1 s @ 200 Hz)
STRIDE   = 50     # 75 % overlap
BATCH    = 256
LR       = 1e-3
EPOCHS   = 50
ES_PAT   = 7      # early-stop patience (val loss)
LR_PAT   = 3      # ReduceLROnPlateau patience

# ── subject-wise split ────────────────────────────────────────────────────────
TEST_SUBJECTS = {
    "SA19", "SA20", "SA21", "SA22", "SA23",
    "SE11", "SE12", "SE13", "SE14", "SE15",
}


# ── data helpers ──────────────────────────────────────────────────────────────

def make_windows(records: list[dict]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Slice every recording into fixed (WINDOW, 6) chunks."""
    X, y, groups = [], [], []
    for r in records:
        data  = r["data"]          # (N, 6) float32, SI units
        label = 1 if r["is_fall"] else 0
        subj  = r["subject"]
        for start in range(0, len(data) - WINDOW + 1, STRIDE):
            X.append(data[start : start + WINDOW])
            y.append(label)
            groups.append(subj)
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32), groups


def subject_split(
    X: np.ndarray, y: np.ndarray, groups: list[str]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    test_mask = np.array([g in TEST_SUBJECTS for g in groups])
    return X[~test_mask], y[~test_mask], X[test_mask], y[test_mask]


def normalise(
    X_tr: np.ndarray, X_te: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Per-channel StandardScaler fitted on training data only."""
    mean = X_tr.mean(axis=(0, 1))   # (6,)
    std  = X_tr.std(axis=(0, 1)) + 1e-8
    return (X_tr - mean) / std, (X_te - mean) / std, mean, std


# ── model ─────────────────────────────────────────────────────────────────────

class FallCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv1d(6, 32, kernel_size=7, padding=3),
            nn.BatchNorm1d(32), nn.ReLU(),
            nn.Conv1d(32, 64, kernel_size=5, padding=2),
            nn.BatchNorm1d(64), nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm1d(128), nn.ReLU(),
            nn.MaxPool1d(2),
        )
        self.head = nn.Sequential(
            nn.AdaptiveAvgPool1d(1),
            nn.Flatten(),
            nn.Linear(128, 64), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(64, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.features(x)).squeeze(1)


# ── training ──────────────────────────────────────────────────────────────────

def make_loaders(
    X_tr: np.ndarray, y_tr: np.ndarray,
    X_te: np.ndarray, y_te: np.ndarray,
) -> tuple[DataLoader, DataLoader]:
    # Conv1d expects (batch, channels, length) → permute (N,200,6) → (N,6,200)
    def to_tensor(X, y):
        xt = torch.tensor(X).permute(0, 2, 1)
        yt = torch.tensor(y)
        return TensorDataset(xt, yt)

    tr = DataLoader(to_tensor(X_tr, y_tr), batch_size=BATCH, shuffle=True,  num_workers=0)
    te = DataLoader(to_tensor(X_te, y_te), batch_size=BATCH, shuffle=False, num_workers=0)
    return tr, te


def train_model(
    tr_loader: DataLoader, te_loader: DataLoader, pos_weight: float, device: torch.device
) -> tuple[FallCNN, dict]:
    model = FallCNN().to(device)
    criterion = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([pos_weight], device=device)
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=LR_PAT, factor=0.5, verbose=False
    )

    history = {"train_loss": [], "val_loss": [], "train_acc": [], "val_acc": []}
    best_val  = float("inf")
    best_state = None
    no_improve = 0

    for epoch in range(1, EPOCHS + 1):
        # ── train ──
        model.train()
        t_loss, t_correct, t_total = 0.0, 0, 0
        for xb, yb in tr_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            logits = model(xb)
            loss   = criterion(logits, yb)
            loss.backward()
            optimizer.step()
            t_loss    += loss.item() * len(yb)
            t_correct += ((logits > 0) == yb.bool()).sum().item()
            t_total   += len(yb)

        # ── validate ──
        model.eval()
        v_loss, v_correct, v_total = 0.0, 0, 0
        with torch.no_grad():
            for xb, yb in te_loader:
                xb, yb = xb.to(device), yb.to(device)
                logits  = model(xb)
                v_loss    += criterion(logits, yb).item() * len(yb)
                v_correct += ((logits > 0) == yb.bool()).sum().item()
                v_total   += len(yb)

        tl = t_loss / t_total
        vl = v_loss / v_total
        ta = t_correct / t_total
        va = v_correct / v_total
        history["train_loss"].append(tl)
        history["val_loss"].append(vl)
        history["train_acc"].append(ta)
        history["val_acc"].append(va)

        scheduler.step(vl)
        lr_now = optimizer.param_groups[0]["lr"]
        print(f"Epoch {epoch:3d}/{EPOCHS} | "
              f"loss {tl:.4f}  val_loss {vl:.4f} | "
              f"acc {ta:.4f}  val_acc {va:.4f} | lr {lr_now:.6f}")

        if vl < best_val:
            best_val   = vl
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= ES_PAT:
                print(f"  Early stop at epoch {epoch} (no val improvement for {ES_PAT} epochs)")
                break

    model.load_state_dict(best_state)
    return model, history


# ── post-training report ──────────────────────────────────────────────────────

def evaluate(model: FallCNN, te_loader: DataLoader, device: torch.device):
    from sklearn.metrics import (
        classification_report, confusion_matrix,
        roc_curve, auc, precision_recall_curve, average_precision_score,
    )

    model.eval()
    all_logits, all_labels = [], []
    with torch.no_grad():
        for xb, yb in te_loader:
            logits = model(xb.to(device)).cpu()
            all_logits.append(logits)
            all_labels.append(yb)

    logits = torch.cat(all_logits).numpy()
    labels = torch.cat(all_labels).numpy().astype(int)
    probs  = 1 / (1 + np.exp(-logits))   # sigmoid
    preds  = (probs >= 0.5).astype(int)

    print("\n" + "=" * 60)
    print("  Test Set Classification Report")
    print("=" * 60)
    print(classification_report(labels, preds, target_names=["ADL", "Fall"]))

    PLOTS_DIR.mkdir(exist_ok=True)

    # ── 02 confusion matrix ──
    cm = confusion_matrix(labels, preds)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    fig.suptitle("Confusion Matrix", fontsize=13, fontweight="bold")
    for ax, norm, title in [
        (axes[0], None,        "Raw counts"),
        (axes[1], "true",      "Normalised (recall)"),
    ]:
        cm_disp = cm.astype(float) if norm == "true" else cm
        if norm == "true":
            cm_disp = cm_disp / cm_disp.sum(axis=1, keepdims=True)
        im = ax.imshow(cm_disp, cmap="Blues")
        ax.set_xticks([0, 1]); ax.set_yticks([0, 1])
        ax.set_xticklabels(["ADL", "Fall"]); ax.set_yticklabels(["ADL", "Fall"])
        ax.set_xlabel("Predicted"); ax.set_ylabel("True")
        ax.set_title(title)
        for r in range(2):
            for c in range(2):
                val = f"{cm_disp[r,c]:.2f}" if norm else str(cm[r, c])
                ax.text(c, r, val, ha="center", va="center", fontsize=12,
                        color="white" if cm_disp[r, c] > cm_disp.max() / 2 else "black")
        plt.colorbar(im, ax=ax)
    plt.tight_layout()
    fig.savefig(PLOTS_DIR / "02_confusion_matrix.png", dpi=120)
    plt.close(fig)

    # ── 03 ROC ──
    fpr, tpr, _ = roc_curve(labels, probs)
    roc_auc = auc(fpr, tpr)
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(fpr, tpr, color="#e74c3c", lw=2, label=f"AUC = {roc_auc:.4f}")
    ax.plot([0, 1], [0, 1], "k--", lw=1)
    ax.set_xlabel("False Positive Rate"); ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC Curve", fontsize=13)
    ax.legend(loc="lower right")
    plt.tight_layout()
    fig.savefig(PLOTS_DIR / "03_roc_curve.png", dpi=120)
    plt.close(fig)

    # ── 04 precision-recall ──
    prec, rec, _ = precision_recall_curve(labels, probs)
    ap = average_precision_score(labels, probs)
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(rec, prec, color="#3498db", lw=2, label=f"AP = {ap:.4f}")
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
    ax.set_title("Precision-Recall Curve", fontsize=13)
    ax.legend(loc="upper right")
    plt.tight_layout()
    fig.savefig(PLOTS_DIR / "04_precision_recall.png", dpi=120)
    plt.close(fig)

    print(f"  ROC AUC : {roc_auc:.4f}")
    print(f"  Avg Prec: {ap:.4f}")
    print(f"Plots saved to: {PLOTS_DIR}")
    return probs, labels


def plot_history(history: dict) -> None:
    PLOTS_DIR.mkdir(exist_ok=True)
    epochs = range(1, len(history["train_loss"]) + 1)

    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    fig.suptitle("Training History", fontsize=13, fontweight="bold")

    axes[0].plot(epochs, history["train_loss"], label="Train", color="#e74c3c")
    axes[0].plot(epochs, history["val_loss"],   label="Val",   color="#3498db")
    axes[0].set_title("Loss"); axes[0].set_xlabel("Epoch"); axes[0].legend()

    axes[1].plot(epochs, history["train_acc"], label="Train", color="#e74c3c")
    axes[1].plot(epochs, history["val_acc"],   label="Val",   color="#3498db")
    axes[1].set_title("Accuracy"); axes[1].set_xlabel("Epoch"); axes[1].legend()
    axes[1].set_ylim(0, 1)

    plt.tight_layout()
    fig.savefig(PLOTS_DIR / "01_loss_accuracy.png", dpi=120)
    plt.close(fig)
    print(f"  saved 01_loss_accuracy.png")


# ── ONNX export ───────────────────────────────────────────────────────────────

def export_onnx(model: FallCNN) -> None:
    import onnxruntime as ort

    MODELS_DIR.mkdir(exist_ok=True)
    out_path = MODELS_DIR / "fall_detection.onnx"
    model.eval().cpu()
    dummy = torch.zeros(1, 6, WINDOW)
    torch.onnx.export(
        model, dummy, str(out_path),
        input_names=["imu"],
        output_names=["logit"],
        dynamic_axes={"imu": {0: "batch"}, "logit": {0: "batch"}},
        opset_version=17,
    )
    print(f"\nExported: {out_path}  ({out_path.stat().st_size / 1024:.0f} KB)")

    sess = ort.InferenceSession(str(out_path), providers=["CPUExecutionProvider"])
    out  = sess.run(None, {"imu": dummy.numpy()})[0]
    print(f"ONNX verified: output shape {out.shape}  value: {out}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # 1. load
    print(f"\nLoading dataset from: {DATASET_DEFAULT}")
    records = load_dataset(DATASET_DEFAULT)
    print(f"Loaded {len(records)} recordings.")

    # 2. window
    print("Building sliding windows...")
    X, y, groups = make_windows(records)
    print(f"Total windows: {len(X)}  (shape {X.shape})")

    # 3. split
    X_tr, y_tr, X_te, y_te = subject_split(X, y, groups)
    print(f"Train windows: {len(X_tr)}  (fall={y_tr.sum():.0f}, ADL={( y_tr==0).sum():.0f})")
    print(f"Test  windows: {len(X_te)}  (fall={y_te.sum():.0f}, ADL={(y_te==0).sum():.0f})")

    # 4. normalise
    X_tr, X_te, mean, std = normalise(X_tr, X_te)
    MODELS_DIR.mkdir(exist_ok=True)
    np.savez(MODELS_DIR / "scaler.npz", mean=mean, std=std)
    print(f"Scaler saved → models/scaler.npz  (mean={mean.round(4)}, std={std.round(4)})")

    # 5. loaders
    tr_loader, te_loader = make_loaders(X_tr, y_tr, X_te, y_te)

    # 6. class weight (pos = fall)
    n_adl  = (y_tr == 0).sum()
    n_fall = (y_tr == 1).sum()
    pos_weight = n_adl / n_fall
    print(f"\npos_weight = {pos_weight:.3f}  (ADL:{n_adl} / Fall:{n_fall})\n")

    # 7. train
    model, history = train_model(tr_loader, te_loader, pos_weight, device)

    # 8. report
    plot_history(history)
    evaluate(model, te_loader, device)

    # 9. save weights + export
    ckpt = MODELS_DIR / "fall_detection.pt"
    torch.save(model.state_dict(), ckpt)
    print(f"Weights saved → {ckpt}")
    export_onnx(model)


if __name__ == "__main__":
    main()
