"""Classification metrics with no third-party dependencies.

precision(c) = TP / (TP + FP)  -> of everything predicted as c, how much really was c
recall(c)    = TP / (TP + FN)  -> of everything that really was c, how much we caught
f1(c)        = harmonic mean of precision and recall
"""

from __future__ import annotations

from collections import Counter


def accuracy(gold: list[str], pred: list[str]) -> float:
    if not gold:
        return 0.0
    return sum(g == p for g, p in zip(gold, pred)) / len(gold)


def confusion_matrix(gold: list[str], pred: list[str]) -> dict[str, dict[str, int]]:
    """matrix[gold_label][pred_label] = count. Rows and columns cover every label seen."""
    labels = sorted(set(gold) | set(pred))
    matrix = {g: dict.fromkeys(labels, 0) for g in labels}
    for g, p in zip(gold, pred):
        matrix[g][p] += 1
    return matrix


def per_class_report(gold: list[str], pred: list[str]) -> dict[str, dict[str, float]]:
    """precision / recall / f1 / support for each gold label."""
    tp, fp, fn = Counter(), Counter(), Counter()
    for g, p in zip(gold, pred):
        if g == p:
            tp[g] += 1
        else:
            fp[p] += 1
            fn[g] += 1
    report = {}
    for label in sorted(set(gold)):
        prec_den = tp[label] + fp[label]
        rec_den = tp[label] + fn[label]
        precision = tp[label] / prec_den if prec_den else 0.0
        recall = tp[label] / rec_den if rec_den else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        report[label] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "support": rec_den,
        }
    return report


def format_confusion(matrix: dict[str, dict[str, int]], short: dict[str, str] | None = None) -> str:
    """Plain-text confusion matrix (rows = expected, columns = predicted)."""
    labels = list(matrix)
    names = [(short or {}).get(label, label) for label in labels]
    width = max([len(n) for n in names] + [8])
    header = "expected\\pred".ljust(width) + " " + " ".join(n[:6].rjust(6) for n in names)
    rows = [header]
    for label, name in zip(labels, names):
        cells = " ".join(str(matrix[label][col] or ".").rjust(6) for col in labels)
        rows.append(name.ljust(width) + " " + cells)
    return "\n".join(rows)


def format_report(report: dict[str, dict[str, float]]) -> str:
    lines = [f"{'class':<28} {'prec':>6} {'recall':>6} {'f1':>6} {'n':>4}"]
    for label, r in report.items():
        lines.append(f"{label:<28} {r['precision']:>6.2f} {r['recall']:>6.2f} {r['f1']:>6.2f} {r['support']:>4}")
    return "\n".join(lines)
