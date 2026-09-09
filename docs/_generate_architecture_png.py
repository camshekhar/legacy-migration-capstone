"""One-off script used to generate docs/architecture.png. Not part of the
runtime pipeline -- kept for reproducibility if the diagram needs updating."""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

nodes = [
    ("Legacy MySQL\n(source)", 0, "#e2e8f0"),
    ("schema_profiler\n(SQLAlchemy)", 1, "#93c5fd"),
    ("ai_mapper\n(LangChain + Claude)", 2, "#a78bfa"),
    ("human_review_gate\n(LangGraph pause/resume)", 3, "#fca5a5"),
    ("rule_generator\n(LangChain)", 4, "#a78bfa"),
    ("migration_executor\n(retry + backoff)", 5, "#93c5fd"),
    ("validator\n(Great Expectations + dbt)", 6, "#86efac"),
    ("doc_generator\n(LangChain)", 7, "#a78bfa"),
    ("Snowflake\n(target)", 8, "#e2e8f0"),
]

fig, ax = plt.subplots(figsize=(6, 13))
ax.set_xlim(0, 6)
ax.set_ylim(-1, len(nodes))
ax.axis("off")

box_w, box_h = 4, 0.7
for label, i, color in nodes:
    y = len(nodes) - i - 1
    box = FancyBboxPatch((1, y - box_h / 2), box_w, box_h,
                          boxstyle="round,pad=0.08,rounding_size=0.1",
                          linewidth=1.5, edgecolor="#1e293b", facecolor=color)
    ax.add_patch(box)
    ax.text(3, y, label, ha="center", va="center", fontsize=10, fontweight="bold", color="#0f172a")
    if i > 0:
        prev_y = len(nodes) - (i - 1) - 1
        arrow = FancyArrowPatch((3, prev_y - box_h / 2), (3, y + box_h / 2),
                                 arrowstyle="-|>", mutation_scale=15, color="#334155", linewidth=1.5)
        ax.add_patch(arrow)

ax.text(3, len(nodes), "AI-Assisted Legacy Migration — Pipeline Architecture",
        ha="center", va="bottom", fontsize=13, fontweight="bold")

# Side annotation for the audit log + LangFuse, which touch every node
ax.annotate("Every node writes to\naudit/migration_audit_log.json\n(immutable, append-only)",
            xy=(1, 3.5), xytext=(-1.9, 3.5), fontsize=8.5, color="#475569",
            ha="left", va="center",
            arrowprops=dict(arrowstyle="-", color="#94a3b8", lw=1, linestyle="dashed"))

ax.annotate("Every LLM call traced to\nLangFuse with a prompt_id",
            xy=(5, 5.5), xytext=(5.1, 5.5), fontsize=8.5, color="#475569",
            ha="left", va="center")

plt.tight_layout()
plt.savefig("docs/architecture.png", dpi=150, bbox_inches="tight")
print("Saved docs/architecture.png")
