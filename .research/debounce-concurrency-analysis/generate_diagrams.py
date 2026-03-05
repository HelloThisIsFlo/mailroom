"""Generate timing diagrams for Mailroom debounce & concurrency analysis."""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

# ─── Style ───
plt.rcParams.update({
    "figure.facecolor": "#0f1219",
    "axes.facecolor": "#0f1219",
    "text.color": "#c8d0dd",
    "axes.labelcolor": "#8892a4",
    "xtick.color": "#6b7588",
    "ytick.color": "#6b7588",
    "font.family": "monospace",
    "font.size": 10,
    "axes.edgecolor": "#2a3040",
    "grid.color": "#1e2535",
    "grid.alpha": 0.5,
})

C = {
    "bg": "#0f1219",
    "surface": "#181e2a",
    "border": "#2a3040",
    "text": "#c8d0dd",
    "dim": "#6b7588",
    "green": "#3dd68c",
    "red": "#f07070",
    "amber": "#f0b840",
    "blue": "#5a9cf0",
    "cyan": "#30c8e0",
    "purple": "#9880e0",
    "green_bg": "#153028",
    "red_bg": "#301818",
    "amber_bg": "#302810",
    "blue_bg": "#152840",
    "cyan_bg": "#103038",
    "purple_bg": "#201838",
}

LANES = {
    "User":      0,
    "SSE":       1,
    "Queue":     2,
    "Debounce":  3,
    "poll()":    4,
}

def draw_block(ax, lane, t_start, t_end, label, color, bg, text_color=None, alpha=0.9, fontsize=8.5):
    """Draw a rounded block on a swim lane."""
    y = lane
    h = 0.55
    w = t_end - t_start
    rect = FancyBboxPatch(
        (t_start, y - h/2), w, h,
        boxstyle="round,pad=0.06",
        facecolor=bg, edgecolor=color, linewidth=1.2, alpha=alpha,
        zorder=3,
    )
    ax.add_patch(rect)
    ax.text(
        t_start + w/2, y, label,
        ha="center", va="center",
        fontsize=fontsize, color=text_color or color,
        fontweight="medium", zorder=4,
    )

def draw_event(ax, lane, t, color, symbol="▼", size=11):
    """Draw a point event marker."""
    ax.plot(t, lane, marker="v", color=color, markersize=size, zorder=5)

def draw_arrow_down(ax, t, y_from, y_to, color, style="->"):
    """Draw a vertical arrow between lanes."""
    ax.annotate(
        "", xy=(t, y_to + 0.3), xytext=(t, y_from - 0.3),
        arrowprops=dict(arrowstyle=style, color=color, lw=1, alpha=0.5),
        zorder=2,
    )

def setup_axes(ax, lanes, t_max, title):
    """Configure axes for swim-lane diagram."""
    ax.set_xlim(-0.5, t_max + 0.5)
    ax.set_ylim(-0.8, len(lanes) - 0.2)
    ax.invert_yaxis()
    ax.set_xlabel("Time (seconds)", fontsize=9, labelpad=10)
    ax.set_yticks(list(range(len(lanes))))
    ax.set_yticklabels(list(lanes.keys()), fontsize=10, fontweight="medium")
    ax.set_xticks(range(0, t_max + 1))
    ax.tick_params(axis="y", length=0, pad=12)
    ax.grid(axis="x", linestyle=":", alpha=0.3)
    for spine in ax.spines.values():
        spine.set_visible(False)
    # Lane separators
    for i in range(len(lanes)):
        ax.axhline(y=i, color=C["border"], linewidth=0.5, alpha=0.3, zorder=1)
    ax.set_title(title, fontsize=13, fontweight="bold", color=C["text"], pad=18, loc="left")


def add_outcome_box(ax, x, y, text, color, bg):
    """Add an outcome annotation box."""
    ax.text(
        x, y, text,
        fontsize=9, color=color, fontweight="bold",
        ha="left", va="center",
        bbox=dict(boxstyle="round,pad=0.4", facecolor=bg, edgecolor=color, alpha=0.9, linewidth=1),
        zorder=6,
    )


# ═══════════════════════════════════════════════════════════════════
# FIGURE 1: Scenario A — Two labels within debounce window
# ═══════════════════════════════════════════════════════════════════
def make_scenario_a():
    fig, ax = plt.subplots(figsize=(14, 5))
    setup_axes(ax, LANES, 14, "Scenario A — Two Labels Within Debounce Window (10s)")

    # User applies labels
    draw_event(ax, LANES["User"], 0, C["green"])
    ax.text(0, LANES["User"] - 0.38, "Label X\n(@ToFeed)", ha="center", fontsize=7.5, color=C["green"])
    draw_event(ax, LANES["User"], 5, C["blue"])
    ax.text(5, LANES["User"] - 0.38, "Label Y\n(@ToImbox)", ha="center", fontsize=7.5, color=C["blue"])

    # SSE events
    draw_event(ax, LANES["SSE"], 0.2, C["green"], size=8)
    draw_event(ax, LANES["SSE"], 5.2, C["blue"], size=8)
    draw_arrow_down(ax, 0.2, LANES["User"], LANES["SSE"], C["dim"])
    draw_arrow_down(ax, 5.2, LANES["User"], LANES["SSE"], C["dim"])

    # Queue
    draw_event(ax, LANES["Queue"], 0.3, C["amber"], size=8)
    ax.text(0.3, LANES["Queue"] + 0.38, "consumed\nimmediately", ha="center", fontsize=6.5, color=C["dim"])
    draw_block(ax, LANES["Queue"], 5.3, 10, "● buffered", C["amber"], C["amber_bg"], fontsize=7.5)
    ax.text(10.3, LANES["Queue"], "drained", ha="left", fontsize=7, color=C["dim"])
    draw_arrow_down(ax, 0.3, LANES["SSE"], LANES["Queue"], C["dim"])
    draw_arrow_down(ax, 5.3, LANES["SSE"], LANES["Queue"], C["dim"])

    # Debounce window
    draw_block(ax, LANES["Debounce"], 0.4, 10, "debounce window (10s)", C["cyan"], C["cyan_bg"])

    # poll() sees both
    draw_block(ax, LANES["poll()"], 10.1, 13, "poll()  — sees BOTH X and Y", C["purple"], C["purple_bg"])
    draw_arrow_down(ax, 10.1, LANES["Debounce"], LANES["poll()"], C["dim"])

    # Annotations
    ax.annotate(
        "All events collapsed into single trigger",
        xy=(5.5, LANES["Debounce"] + 0.3), xytext=(5.5, LANES["Debounce"] + 0.75),
        fontsize=8, color=C["cyan"], ha="center",
        arrowprops=dict(arrowstyle="->", color=C["cyan"], lw=0.8, alpha=0.4),
    )

    fig.tight_layout()
    fig.savefig(".research/debounce-concurrency-analysis/scenario_a_timeline.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════
# FIGURE 2: Scenario A sub-scenarios — what poll() does with BOTH
# ═══════════════════════════════════════════════════════════════════
def make_scenario_a_outcomes():
    fig, axes = plt.subplots(3, 1, figsize=(14, 9), gridspec_kw={"hspace": 0.55})

    # ─── A1: Same sender, same label ───
    ax = axes[0]
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.3, 1.8)
    ax.invert_yaxis()
    ax.set_title("A1 — Same Sender, Same Label", fontsize=11, fontweight="bold", color=C["text"], pad=12, loc="left")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    # Emails
    draw_block(ax, 0.3, 0.2, 2.5, "✉ alice@  @ToFeed", C["green"], C["green_bg"], fontsize=9)
    draw_block(ax, 0.7, 0.2, 2.5, "✉ alice@  @ToFeed", C["green"], C["green_bg"], fontsize=9)

    # Flow
    ax.annotate("", xy=(3.3, 0.5), xytext=(2.7, 0.5),
                arrowprops=dict(arrowstyle="->", color=C["dim"], lw=1.5))
    draw_block(ax, 0.5, 3.3, 5.5, "_detect_conflicts()\n1 label → CLEAN ✓", C["green"], C["green_bg"], fontsize=8.5)
    ax.annotate("", xy=(6.3, 0.5), xytext=(5.7, 0.5),
                arrowprops=dict(arrowstyle="->", color=C["dim"], lw=1.5))
    draw_block(ax, 0.5, 6.3, 8.3, "_process_sender()\nbatched together", C["blue"], C["blue_bg"], fontsize=8.5)
    add_outcome_box(ax, 8.6, 0.5, "✓ OK", C["green"], C["green_bg"])

    # Explanation
    ax.text(5, 1.4, "Same sender + same label = grouped into one batch. Processed once. No issues.",
            fontsize=8.5, color=C["dim"], ha="center", style="italic")

    # ─── A2: Same sender, different labels ───
    ax = axes[1]
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.3, 2.0)
    ax.invert_yaxis()
    ax.set_title("A2 — Same Sender, Different Labels", fontsize=11, fontweight="bold", color=C["text"], pad=12, loc="left")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    draw_block(ax, 0.3, 0.2, 2.5, "✉ alice@  @ToFeed", C["green"], C["green_bg"], fontsize=9)
    draw_block(ax, 0.7, 0.2, 2.5, "✉ alice@  @ToImbox", C["blue"], C["blue_bg"], fontsize=9)

    ax.annotate("", xy=(3.3, 0.5), xytext=(2.7, 0.5),
                arrowprops=dict(arrowstyle="->", color=C["dim"], lw=1.5))
    draw_block(ax, 0.5, 3.3, 5.8, "_detect_conflicts()\n2 labels → CONFLICT!", C["red"], C["red_bg"], fontsize=8.5)
    ax.annotate("", xy=(6.5, 0.5), xytext=(6.0, 0.5),
                arrowprops=dict(arrowstyle="->", color=C["dim"], lw=1.5))
    draw_block(ax, 0.5, 6.5, 8.8, "@MailroomError\nadded to both", C["red"], C["red_bg"], fontsize=8.5)
    add_outcome_box(ax, 0.2, 1.4, "⚠ CONFLICT", C["red"], C["red_bg"])

    ax.text(5, 1.6, "Same sender + different labels in same poll = conflict. User must resolve manually.",
            fontsize=8.5, color=C["dim"], ha="center", style="italic")

    # ─── A3: Different senders ───
    ax = axes[2]
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.3, 1.8)
    ax.invert_yaxis()
    ax.set_title("A3 — Different Senders", fontsize=11, fontweight="bold", color=C["text"], pad=12, loc="left")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    draw_block(ax, 0.3, 0.2, 3.0, "✉ alice@  @ToFeed", C["green"], C["green_bg"], fontsize=9)
    draw_block(ax, 0.7, 0.2, 3.0, "✉ bob@  @ToImbox", C["blue"], C["blue_bg"], fontsize=9)

    ax.annotate("", xy=(3.8, 0.3), xytext=(3.2, 0.3),
                arrowprops=dict(arrowstyle="->", color=C["dim"], lw=1.5))
    ax.annotate("", xy=(3.8, 0.7), xytext=(3.2, 0.7),
                arrowprops=dict(arrowstyle="->", color=C["dim"], lw=1.5))
    draw_block(ax, 0.3, 3.8, 6.5, "alice@ → Feed ✓", C["green"], C["green_bg"], fontsize=9)
    draw_block(ax, 0.7, 3.8, 6.5, "bob@ → Imbox ✓", C["blue"], C["blue_bg"], fontsize=9)
    add_outcome_box(ax, 7.0, 0.3, "✓ OK", C["green"], C["green_bg"])
    add_outcome_box(ax, 7.0, 0.7, "✓ OK", C["green"], C["green_bg"])

    ax.text(5, 1.4, "Different senders are always independent. No interaction.",
            fontsize=8.5, color=C["dim"], ha="center", style="italic")

    fig.tight_layout()
    fig.savefig(".research/debounce-concurrency-analysis/scenario_a_outcomes.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════
# FIGURE 3: Scenario B — Label during active processing
# ═══════════════════════════════════════════════════════════════════
def make_scenario_b():
    fig, ax = plt.subplots(figsize=(14, 5))
    setup_axes(ax, LANES, 13, "Scenario B — Label Applied During Active Processing (3s debounce)")

    # User applies labels
    draw_event(ax, LANES["User"], 0, C["green"])
    ax.text(0, LANES["User"] - 0.38, "Label X", ha="center", fontsize=8, color=C["green"])
    draw_event(ax, LANES["User"], 4, C["amber"])
    ax.text(4, LANES["User"] - 0.38, "Label Z", ha="center", fontsize=8, color=C["amber"])

    # SSE events
    draw_event(ax, LANES["SSE"], 0.2, C["green"], size=8)
    draw_event(ax, LANES["SSE"], 4.2, C["amber"], size=8)
    draw_arrow_down(ax, 0.2, LANES["User"], LANES["SSE"], C["dim"])
    draw_arrow_down(ax, 4.2, LANES["User"], LANES["SSE"], C["dim"])

    # Queue
    draw_event(ax, LANES["Queue"], 0.3, C["green"], size=7)
    ax.text(0.6, LANES["Queue"] + 0.35, "consumed", fontsize=6.5, color=C["dim"])
    draw_block(ax, LANES["Queue"], 4.3, 6, "● waiting", C["amber"], C["amber_bg"], fontsize=7.5)
    ax.text(6.1, LANES["Queue"], "→", fontsize=10, color=C["dim"], va="center")
    draw_event(ax, LANES["Queue"], 6.3, C["amber"], size=7)
    ax.text(6.6, LANES["Queue"] + 0.35, "consumed", fontsize=6.5, color=C["dim"])
    draw_arrow_down(ax, 0.3, LANES["SSE"], LANES["Queue"], C["dim"])
    draw_arrow_down(ax, 4.3, LANES["SSE"], LANES["Queue"], C["dim"])

    # Debounce windows
    draw_block(ax, LANES["Debounce"], 0.4, 3, "debounce (3s)", C["cyan"], C["cyan_bg"], fontsize=8)
    draw_block(ax, LANES["Debounce"], 6.4, 9, "debounce (3s)", C["cyan"], C["cyan_bg"], fontsize=8)

    # poll() cycles
    draw_block(ax, LANES["poll()"], 3.1, 6, "poll() #1 — Label X", C["purple"], C["purple_bg"], fontsize=8.5)
    draw_block(ax, LANES["poll()"], 9.1, 12, "poll() #2 — Label Z", C["purple"], C["purple_bg"], fontsize=8.5)
    draw_arrow_down(ax, 3.1, LANES["Debounce"], LANES["poll()"], C["dim"])
    draw_arrow_down(ax, 9.1, LANES["Debounce"], LANES["poll()"], C["dim"])

    # Key annotation: queue buffers during poll
    ax.annotate(
        "SSE event buffered\nin queue while\npoll() #1 runs",
        xy=(4.5, LANES["Queue"]), xytext=(4.5, LANES["Queue"] - 1.1),
        fontsize=7.5, color=C["amber"], ha="center",
        arrowprops=dict(arrowstyle="->", color=C["amber"], lw=0.8, alpha=0.5),
    )

    # Key annotation: immediate pickup
    ax.annotate(
        "queue.get() returns\nimmediately (event\nalready waiting)",
        xy=(6.4, LANES["Debounce"]), xytext=(7.5, LANES["Debounce"] - 1.5),
        fontsize=7.5, color=C["cyan"], ha="center",
        arrowprops=dict(arrowstyle="->", color=C["cyan"], lw=0.8, alpha=0.5),
    )

    # Emphasize: no concurrent polls
    ax.annotate(
        "",
        xy=(6, LANES["poll()"] + 0.35), xytext=(9.1, LANES["poll()"] + 0.35),
        arrowprops=dict(arrowstyle="<->", color=C["dim"], lw=1, alpha=0.4),
    )
    ax.text(7.55, LANES["poll()"] + 0.5, "gap — never concurrent", fontsize=7, color=C["dim"], ha="center")

    fig.tight_layout()
    fig.savefig(".research/debounce-concurrency-analysis/scenario_b_timeline.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════
# FIGURE 4: Scenario B sub-scenarios
# ═══════════════════════════════════════════════════════════════════
def make_scenario_b_outcomes():
    fig, axes = plt.subplots(3, 1, figsize=(14, 12), gridspec_kw={"hspace": 0.6})

    # ─── B1: Same sender, same label ───
    ax = axes[0]
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.3, 2.8)
    ax.invert_yaxis()
    ax.set_title("B1 — Same Sender, Same Label (across poll boundaries)", fontsize=11, fontweight="bold", color=C["text"], pad=12, loc="left")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    # Poll 1
    ax.text(2.3, -0.05, "Poll #1", fontsize=9, color=C["purple"], fontweight="bold", ha="center")
    draw_block(ax, 0.4, 0.3, 4.3, "alice@ → Feed group\nreconcile all emails\nremove @ToFeed", C["green"], C["green_bg"], fontsize=8)

    ax.annotate("", xy=(5.0, 0.4), xytext=(4.5, 0.4),
                arrowprops=dict(arrowstyle="->", color=C["dim"], lw=1.5))

    # Poll 2
    ax.text(7.3, -0.05, "Poll #2", fontsize=9, color=C["purple"], fontweight="bold", ha="center")
    draw_block(ax, 0.4, 5.0, 9.3, "alice@ — re-triage detected\nsame_group = True → no-op\nre-reconcile (idempotent)", C["cyan"], C["cyan_bg"], fontsize=8)

    add_outcome_box(ax, 0.3, 1.3, "✓ Correct final state", C["green"], C["green_bg"])

    # Transient state callout
    rect = FancyBboxPatch((0.3, 1.7), 9.0, 0.7, boxstyle="round,pad=0.15",
                          facecolor=C["amber_bg"], edgecolor=C["amber"], linewidth=0.8, alpha=0.7, zorder=3)
    ax.add_patch(rect)
    ax.text(4.8, 2.05, "NOTE: Brief transient state: new email has both @ToFeed + Feed destinations. Cleaned up by poll #2.",
            fontsize=7.5, color=C["amber"], ha="center", va="center")

    # ─── B2: Same sender, different labels — THE STAR ───
    ax = axes[1]
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.3, 2.8)
    ax.invert_yaxis()
    ax.set_title("B2 — Same Sender, Different Labels ★ THE EDGE CASE", fontsize=11, fontweight="bold", color=C["amber"], pad=12, loc="left")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    ax.text(2.3, -0.05, "Poll #1 (@ToFeed)", fontsize=9, color=C["green"], fontweight="bold", ha="center")
    draw_block(ax, 0.4, 0.3, 4.3, "alice@ → Feed group\nall emails → Feed labels\nremove @ToFeed", C["green"], C["green_bg"], fontsize=8)

    ax.annotate("", xy=(5.0, 0.4), xytext=(4.5, 0.4),
                arrowprops=dict(arrowstyle="->", color=C["dim"], lw=1.5))

    ax.text(7.3, -0.05, "Poll #2 (@ToImbox)", fontsize=9, color=C["blue"], fontweight="bold", ha="center")
    draw_block(ax, 0.4, 5.0, 9.5, "re-triage! Feed → Imbox\nall emails re-reconciled\nremove @ToImbox", C["blue"], C["blue_bg"], fontsize=8)

    add_outcome_box(ax, 0.3, 1.3, "⚠ Last label wins — silently", C["amber"], C["amber_bg"])

    # Comparison callout
    rect = FancyBboxPatch((0.3, 1.7), 9.2, 0.8, boxstyle="round,pad=0.15",
                          facecolor=C["red_bg"], edgecolor=C["red"], linewidth=0.8, alpha=0.7, zorder=3)
    ax.add_patch(rect)
    ax.text(4.9, 2.1,
            "Compare with A2: same sender + different labels within debounce = CONFLICT (@MailroomError)\n"
            "But across polls = sequential re-triage. No conflict detected. The debounce window is the only boundary.",
            fontsize=7.5, color=C["red"], ha="center", va="center")

    # ─── B3: Different senders ───
    ax = axes[2]
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.3, 1.8)
    ax.invert_yaxis()
    ax.set_title("B3 — Different Senders (across poll boundaries)", fontsize=11, fontweight="bold", color=C["text"], pad=12, loc="left")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    ax.text(2.3, -0.05, "Poll #1", fontsize=9, color=C["purple"], fontweight="bold", ha="center")
    draw_block(ax, 0.5, 0.3, 4.3, "alice@ → Feed ✓", C["green"], C["green_bg"], fontsize=9)

    ax.text(7.3, -0.05, "Poll #2", fontsize=9, color=C["purple"], fontweight="bold", ha="center")
    draw_block(ax, 0.5, 5.0, 9.5, "bob@ → Imbox ✓", C["blue"], C["blue_bg"], fontsize=9)

    add_outcome_box(ax, 0.3, 1.2, "✓ Independent — no interaction", C["green"], C["green_bg"])

    fig.tight_layout()
    fig.savefig(".research/debounce-concurrency-analysis/scenario_b_outcomes.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════
# FIGURE 5: The key comparison — timing determines outcome
# ═══════════════════════════════════════════════════════════════════
def make_comparison():
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.5), gridspec_kw={"wspace": 0.3})

    fig.suptitle("Same Action, Different Outcome — Timing Is the Only Difference",
                 fontsize=13, fontweight="bold", color=C["amber"], y=0.98)

    # ─── Left: Within debounce ───
    ax = axes[0]
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.2, 3.2)
    ax.invert_yaxis()
    ax.set_title("Within Debounce Window", fontsize=11, color=C["red"], fontweight="bold", pad=10, loc="left")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    draw_block(ax, 0.3, 0.5, 4.0, "✉ alice@ @ToFeed", C["green"], C["green_bg"], fontsize=8.5)
    ax.text(4.5, 0.3, "+", fontsize=14, color=C["dim"], ha="center", va="center")
    draw_block(ax, 0.3, 5.0, 9.0, "✉ alice@ @ToImbox", C["blue"], C["blue_bg"], fontsize=8.5)

    ax.text(5.0, 1.0, "▼  same poll", fontsize=9, color=C["dim"], ha="center")

    draw_block(ax, 1.5, 1.5, 8.5, "_detect_conflicts() → 2 labels", C["red"], C["red_bg"], fontsize=9)

    add_outcome_box(ax, 2.5, 2.4, "CONFLICT → @MailroomError", C["red"], C["red_bg"])

    # ─── Right: Across polls ───
    ax = axes[1]
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.2, 3.2)
    ax.invert_yaxis()
    ax.set_title("Across Poll Boundaries", fontsize=11, color=C["amber"], fontweight="bold", pad=10, loc="left")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    draw_block(ax, 0.3, 0.3, 4.0, "Poll #1: @ToFeed", C["green"], C["green_bg"], fontsize=8.5)
    ax.text(4.5, 0.3, "then", fontsize=9, color=C["dim"], ha="center", va="center")
    draw_block(ax, 0.3, 5.2, 9.5, "Poll #2: @ToImbox", C["blue"], C["blue_bg"], fontsize=8.5)

    ax.text(5.0, 1.0, "▼  separate polls", fontsize=9, color=C["dim"], ha="center")

    draw_block(ax, 1.5, 1.5, 8.5, "_detect_retriage() → re-triage", C["amber"], C["amber_bg"], fontsize=9)

    add_outcome_box(ax, 2.0, 2.4, "LAST LABEL WINS (silently)", C["amber"], C["amber_bg"])

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(".research/debounce-concurrency-analysis/comparison.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════
# Generate all
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    make_scenario_a()
    print("✓ scenario_a_timeline.png")
    make_scenario_a_outcomes()
    print("✓ scenario_a_outcomes.png")
    make_scenario_b()
    print("✓ scenario_b_timeline.png")
    make_scenario_b_outcomes()
    print("✓ scenario_b_outcomes.png")
    make_comparison()
    print("✓ comparison.png")
    print("\nAll diagrams generated in .research/debounce-concurrency-analysis/")
