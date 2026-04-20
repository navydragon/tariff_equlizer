import os
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch


def draw():
    os.makedirs("diagrams", exist_ok=True)
    plt.rcParams["figure.figsize"] = (10, 6)
    fig, ax = plt.subplots()
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)

    def box(x, y, w, h, text):
        rect = FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.2",
            linewidth=1.5,
            edgecolor="#1f4b99",
            facecolor="#e8f0ff",
        )
        ax.add_patch(rect)
        ax.text(
            x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=9, wrap=True
        )

    def arrow(x1, y1, x2, y2, text=None):
        arr = FancyArrowPatch(
            (x1, y1),
            (x2, y2),
            arrowstyle="->",
            mutation_scale=12,
            linewidth=1.2,
            color="#444",
        )
        ax.add_patch(arr)
        if text:
            ax.text(
                (x1 + x2) / 2,
                (y1 + y2) / 2 + 0.2,
                text,
                ha="center",
                va="center",
                fontsize=8,
            )

    box(0.7, 7.5, 3.2, 1.3, "Источники данных\nSQLite, Excel (маршруты, цены)")
    box(
        0.7,
        5.4,
        3.2,
        1.2,
        "Подготовка и агрегирование\nнормализация, справочники,\nFeather full/small",
    )
    box(
        4.2,
        6.4,
        3.2,
        1.2,
        "Сценарная модель\nиндексация, надбавки,\nотдельные решения, эластичность",
    )
    box(
        4.2,
        4.6,
        3.2,
        1.2,
        "Расчёт KPI\nвклад мер (₽, %),\nсебестоимость, маржа",
    )
    box(7.3, 7.0, 2.4, 1.0, "Dash Pages\ncallbacks")
    box(
        7.3,
        5.2,
        2.4,
        2.4,
        "UI страницы:\n- Эффекты решений\n- Экономика грузов\n- Куб эффектов",
    )
    box(4.2, 2.6, 3.2, 1.2, "Визуализация\nграфики, таблицы, карточки")
    box(7.3, 2.6, 2.4, 1.2, "Экспорт отчётов\nCSV/Excel/PDF")

    arrow(2.3, 7.5, 2.3, 6.6)
    arrow(2.3, 5.4, 2.3, 3.5, text="Feather")
    arrow(2.3, 6.0, 4.2, 6.9)
    arrow(2.3, 3.5, 4.2, 5.2)
    arrow(5.8, 6.4, 5.8, 5.8)
    arrow(5.8, 4.6, 5.8, 3.8)
    arrow(7.4, 6.4, 8.5, 6.4)
    arrow(8.5, 6.4, 8.5, 5.2)
    arrow(5.8, 3.8, 5.8, 3.0)
    arrow(6.4, 3.2, 7.3, 3.2)

    plt.tight_layout()
    out_path = os.path.join("diagrams", "architecture.png")
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    print(f"saved {out_path}")


if __name__ == "__main__":
    draw()

