"""Export our own architecture diagrams with matplotlib, without web assets."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


def box(axis, x, y, text, width=2.6, height=0.9, color="#e6f0fa"):
    axis.add_patch(FancyBboxPatch((x - width / 2, y - height / 2), width, height,
                                boxstyle="round,pad=0.10", facecolor=color,
                                edgecolor="#24476b", linewidth=1.3))
    axis.text(x, y, text, ha="center", va="center", fontsize=11)


def arrow(axis, start, end, text=""):
    axis.annotate("", xy=end, xytext=start,
                  arrowprops={"arrowstyle": "->", "color": "#444444", "lw": 1.3})
    if text:
        axis.text((start[0] + end[0]) / 2 + 0.1, (start[1] + end[1]) / 2,
                  text, fontsize=9, ha="left", va="center")


def main():
    target = Path("docs/figures")
    target.mkdir(parents=True, exist_ok=True)
    fig, axis = plt.subplots(figsize=(10, 6))
    axis.set(xlim=(0, 12), ylim=(0, 7))
    axis.axis("off")
    axis.set_title("Parallel decomposition in one process", fontsize=17, pad=16)
    box(axis, 6, 6, "Main thread\nread UTF-8 and partition", 3.4)
    for x, label in [(2, "Worker 1\nlines 1-2 | partial 2"),
                     (6, "Worker 2\nlines 3-4 | partial 3"),
                     (10, "Worker 3\nlines 5-6 | partial 2")]:
        box(axis, x, 3.7, label)
        arrow(axis, (6, 5.45), (x, 4.25))
        arrow(axis, (x, 3.15), (6, 1.85))
    axis.text(6, 4.75, "Shared line list (read only); each worker owns a range",
              fontsize=11, ha="center", bbox={"facecolor": "white", "edgecolor": "none"})
    box(axis, 6, 1.3, "Lock-protected total OR private slots + join\n2 + 3 + 2 = 7", 7, 1)
    axis.text(6, 0.25, "OS threads are concurrent; the tested CPython GIL serializes Python bytecode.",
              ha="center", fontsize=10)
    fig.savefig(target / "parallel.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(10, 6))
    axis.set(xlim=(0, 12), ylim=(0, 7))
    axis.axis("off")
    axis.set_title("Distributed decomposition across networked machines", fontsize=17, pad=16)
    box(axis, 6, 6, "Coordinator\nassign task IDs and input shards", 4)
    for x, label in [(2, "Machine A\nlocal data and memory"),
                     (6, "Machine B\nlocal data and memory"),
                     (10, "Machine C\nlocal data and memory")]:
        box(axis, x, 3.6, label, 3)
        arrow(axis, (6, 5.45), (x, 4.15))
        arrow(axis, (x, 3.05), (6, 1.85))
    axis.text(6, 4.75, "Network messages: task assignment and data/location",
              fontsize=11, ha="center", bbox={"facecolor": "white", "edgecolor": "none"})
    axis.text(6, 2.55, "Network messages: task ID and partial count",
              fontsize=11, ha="center", bbox={"facecolor": "white", "edgecolor": "none"})
    box(axis, 6, 1.3, "Accept one result per task ID\ncombine accepted partials", 5, 1)
    axis.text(6, 0.25, "Conceptual design: a slow or failed worker can be retried without counting it twice.",
              ha="center", fontsize=10)
    fig.savefig(target / "distributed.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
