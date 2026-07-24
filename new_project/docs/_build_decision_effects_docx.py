#!/usr/bin/env python3
"""Build decision_effects_formulas.docx from structured content via officecli."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent
FILE = DOCS / "decision_effects_formulas.docx"
CHUNK = 10


def run(args: list[str]) -> None:
    print("+", " ".join(args[:6]), "..." if len(args) > 6 else "")
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.stdout.buffer.write((r.stdout or "").encode("utf-8", errors="replace"))
        sys.stderr.buffer.write((r.stderr or "").encode("utf-8", errors="replace"))
        raise SystemExit(f"FAILED: {args}")
    if r.stdout.strip():
        snippet = r.stdout.strip()[:300]
        sys.stdout.buffer.write((snippet + "\n").encode("utf-8", errors="replace"))


def batch(ops: list[dict]) -> None:
    for i in range(0, len(ops), CHUNK):
        chunk = ops[i : i + CHUNK]
        payload = DOCS / f"_batch_{i}.json"
        payload.write_text(json.dumps(chunk, ensure_ascii=False, indent=2), encoding="utf-8")
        run(["officecli", "batch", str(FILE), "--input", str(payload), "--json"])
        payload.unlink(missing_ok=True)


def p(text: str, **props) -> dict:
    props = {"text": text, "size": "11pt", "spaceAfter": "6pt", **props}
    return {"command": "add", "parent": "/body", "type": "paragraph", "props": props}


def h1(text: str) -> dict:
    return p(text, style="Heading1", size="18pt", bold="true", spaceBefore="18pt", spaceAfter="10pt")


def h2(text: str) -> dict:
    return p(text, style="Heading2", size="14pt", bold="true", spaceBefore="14pt", spaceAfter="8pt")


def h3(text: str) -> dict:
    return p(text, style="Heading3", size="12pt", bold="true", spaceBefore="10pt", spaceAfter="6pt")


def eq(formula: str) -> dict:
    return {
        "command": "add",
        "parent": "/body",
        "type": "equation",
        "props": {"formula": formula},
    }


def bullet(text: str) -> dict:
    return p(f"• {text}", spaceAfter="4pt")


def table(data: str, col_widths: str | None = None) -> dict:
    props: dict[str, str] = {
        "data": data,
        "border.all": "single;4;000000",
        "spaceAfter": "8pt",
    }
    if col_widths:
        props["colWidths"] = col_widths
    return {"command": "add", "parent": "/body", "type": "table", "props": props}


def main() -> None:
    if FILE.exists():
        FILE.unlink()

    run(["officecli", "create", str(FILE)])
    run(["officecli", "open", str(FILE)])

    # Drop blank starter paragraph from create (ignore failure)
    subprocess.run(
        ["officecli", "remove", str(FILE), "/body/p[1]"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    ops: list[dict] = []

    # Title
    ops.append(
        p(
            "Формулы расчёта на странице «Эффект от решений»",
            style="Title",
            size="22pt",
            bold="true",
            spaceAfter="12pt",
        )
    )
    ops.append(
        p(
            "Справочник для аналитиков и пользователей системы. Документ описывает, что считается и как, "
            "с привязкой к блокам страницы «Эффект от решений».",
            spaceAfter="12pt",
        )
    )

    # 1
    ops.append(h1("1. Введение"))
    ops.append(h2("Назначение страницы"))
    ops.append(
        p(
            "Страница оценивает эффект тарифных решений по провозной плате:"
        )
    )
    ops.append(
        bullet(
            "базовая индексация (коэффициенты BTD — базовые тарифные решения);"
        )
    )
    ops.append(
        bullet(
            "отдельные тарифные правила (индексация и прочие решения по условиям маршрута)."
        )
    )
    ops.append(
        p(
            "Дополнительно учитывается эластичность спроса (выпадение объёма и дохода при изменении тарифа), "
            "если в сценарии задан набор эластичности."
        )
    )

    ops.append(h2("Единицы измерения"))
    ops.append(
        table(
            "Уровень,Деньги,Объём;"
            "Внутренние расчёты,руб.,т;"
            "Отображение на экране,млрд руб. (деление на 10^9),млн т (деление на 10^6)",
            "2500,3500,3000",
        )
    )

    ops.append(h2("Входные данные"))
    ops.append(bullet("выбранный сценарий (горизонт лет, настройки BTD, правил, эластичности, оборота);"))
    ops.append(bullet("маршруты из витрины перевозок (начальная провозная плата, объём и др.);"))
    ops.append(bullet("коэффициенты BTD по годам и категориям;"))
    ops.append(bullet("тарифные правила с коэффициентами и долей применения;"))
    ops.append(
        bullet(
            "параметры эластичности (кривые, режим коэффициента удержания, загрузка предприятия) — если включены."
        )
    )

    # 2
    ops.append(h1("2. Общая логика расчёта"))
    ops.append(p("Сквозной поток данных:"))
    ops.append(bullet("Входные данные сценария → базовый коэффициент BTD и коэффициент отдельных правил;"))
    ops.append(bullet("Начальная провозная плата маршрута + коэффициент оборота → цепочка провозной платы по годам;"))
    ops.append(bullet("Из цепочки извлекаются эффект базовых решений и эффект отдельных решений → суммарный эффект;"))
    ops.append(bullet("Эластичность спроса + цепочка → выпадение объёма и дохода;"))
    ops.append(bullet("Суммарный эффект → KPI-карточки и таблица эффектов;"))
    ops.append(bullet("Цепочка и выпадение → абсолютные доходы и объёмы."))
    ops.append(
        p(
            "Кратко: по каждому маршруту строится цепочка провозной платы по годам, из неё извлекаются "
            "годовые приросты (эффект базовых и отдельных решений). Эти приросты агрегируются в KPI и таблицу "
            "эффектов. Абсолютные доходы и объёмы берутся из той же цепочки; при включённом «учёте выпадения» "
            "к ним добавляется коррекция по эластичности."
        )
    )

    # 3
    ops.append(h1("3. Базовые формулы"))
    ops.append(p("Формулы ниже используются во всех блоках страницы."))

    ops.append(h2("3.1. Эффективный коэффициент тарифного правила"))
    ops.append(p("Учитывает долю применения правила (base_percent, %):"))
    ops.append(
        eq(
            r"k_{\mathrm{eff}} = 1 + (k_{\mathrm{raw}} - 1) \times \frac{\mathrm{base\_percent}}{100}"
        )
    )
    ops.append(p("где k_raw — исходный коэффициент правила за год."))
    ops.append(
        p(
            "Пример: k_raw = 1,10; base_percent = 50 → k_eff = 1 + 0,10 × 0,5 = 1,05."
        )
    )

    ops.append(h2("3.2. Комбинированный коэффициент правил за год"))
    ops.append(
        p(
            "Произведение эффективных коэффициентов всех правил, подходящих к маршруту в году y:"
        )
    )
    ops.append(eq(r"K_{\mathrm{rules}}(y) = \prod_i k_{\mathrm{eff},i}(y)"))
    ops.append(p("Если подходящих правил нет, K_rules(y) = 1."))

    ops.append(h2("3.3. Базовый коэффициент BTD за год"))
    ops.append(eq(r"K_{\mathrm{base}}(y) = V_1(y) \times \prod_{i>1} \frac{V_i(y)}{V_i(y-1)}"))
    ops.append(
        p(
            "где V_1(y) — значение первой категории BTD за год y, V_i(y) — значения остальных категорий."
        )
    )
    ops.append(
        p(
            "Если в сценарии отключены «базовые тарифные решения», то K_base(y) = 1 для всех лет."
        )
    )

    ops.append(h2("3.4. Цепочка провозной платы"))
    ops.append(p("Для каждого маршрута, начиная с начальной провозной платы P_0:"))
    ops.append(
        bullet(
            "в первом году горизонта сценария: P(y_0) = P_0 (с учётом оборота — см. ниже);"
        )
    )
    ops.append(bullet("в последующих годах:"))
    ops.append(
        eq(
            r"P(y) = P(y-1) \times (K_{\mathrm{base}}(y) + K_{\mathrm{rules}}(y) - 1)"
        )
    )
    ops.append(
        p(
            "При включённом учёте изменений оборота провозная плата за год масштабируется "
            "коэффициентом оборота turnover(y):"
        )
    )
    ops.append(eq(r"P(y) = T(y) \times \mathrm{turnover}(y)"))
    ops.append(
        p(
            "где T(y) — значение цепочки индексации (тариф) без оборота, либо с накопленным тарифом "
            "предыдущего шага — в зависимости от настройки сценария."
        )
    )

    ops.append(h2("3.5. Годовой инкремент эффекта (ключевая формула)"))
    ops.append(p("Для года y, следующего за первым годом сценария y_0:"))
    ops.append(eq(r"\Delta P_{\mathrm{base}}(y) = P(y-1) \times (K_{\mathrm{base}}(y) - 1)"))
    ops.append(eq(r"\Delta P_{\mathrm{rules}}(y) = P(y-1) \times (K_{\mathrm{rules}}(y) - 1)"))
    ops.append(eq(r"\Delta P_{\mathrm{total}}(y) = \Delta P_{\mathrm{base}}(y) + \Delta P_{\mathrm{rules}}(y)"))
    ops.append(
        p(
            "При учёте оборота множитель turnover(y) входит в расчёт инкрементов вместе с P(y-1)."
        )
    )
    ops.append(
        p(
            "Важно: для первого года сценария эффект всегда равен нулю "
            "(карточки и таблица эффектов по нему не строятся / недоступны).",
            bold="true",
        )
    )
    ops.append(p("Разбивка по отдельному правилу r:"))
    ops.append(eq(r"\Delta P_r(y) = P(y-1) \times (k_{\mathrm{eff},r}(y) - 1)"))

    ops.append(h2("3.6. Процент эффекта"))
    ops.append(eq(r"\mathrm{pct} = \frac{\mathrm{part} \times 100}{\mathrm{denom}}"))
    ops.append(
        p(
            "где part — величина эффекта (базовый / правил / итого), denom — знаменатель:"
        )
    )
    ops.append(
        table(
            "Год,Знаменатель (denom);"
            "Второй год сценария,baseline — начальная провозная плата (с учётом оборота первого года);"
            "Последующие годы,P(y-1) — провозная плата предыдущего года",
            "3000,6000",
        )
    )
    ops.append(p("Если знаменатель ≤ 0, на экране показывается 0,0%."))

    # 4
    ops.append(h1("4. Блок «Оценка мер покрытия дефицита» (KPI-карточки)"))
    ops.append(
        p(
            "Карточки строятся по каждому году, начиная со второго года горизонта сценария."
        )
    )
    ops.append(
        table(
            "Показатель на экране,Формула;"
            "Итого млрд руб.,сумма по маршрутам ΔP_total(y) / 10^9;"
            "Итого % ,pct от знаменателя (см. п. 3.6);"
            "Базовые решения млрд руб.,сумма ΔP_base(y) / 10^9;"
            "Базовые решения % ,pct от знаменателя;"
            "Отдельные решения млрд руб.,сумма ΔP_rules(y) / 10^9;"
            "Отдельные решения % ,pct от знаменателя",
            "4000,5000",
        )
    )
    ops.append(
        p(
            "Суммирование — по всем маршрутам сценария (без фильтров блока таблицы эффектов)."
        )
    )

    # Key formulas for section 4 as real equations
    ops.append(p("Формулы KPI:"))
    ops.append(eq(r"\Delta P_{\mathrm{total}}^{\mathrm{bln}}(y) = \frac{1}{10^9}\sum \Delta P_{\mathrm{total}}(y)"))
    ops.append(eq(r"\Delta P_{\mathrm{base}}^{\mathrm{bln}}(y) = \frac{1}{10^9}\sum \Delta P_{\mathrm{base}}(y)"))
    ops.append(eq(r"\Delta P_{\mathrm{rules}}^{\mathrm{bln}}(y) = \frac{1}{10^9}\sum \Delta P_{\mathrm{rules}}(y)"))

    # 5
    ops.append(h1("5. Блок «Эффекты от применения индексации и отдельных решений»"))
    ops.append(
        p(
            "Таблица и диаграмма за выбранный год с фильтрами (группировка верхнего уровня / внутри, груз, холдинг)."
        )
    )
    ops.append(
        table(
            "Колонка,Смысл;"
            "Базовые решения (руб. / %),сумма ΔP_base по группе — % от P(y-1) группы;"
            "Отдельные решения (руб. / %),сумма ΔP_rules по группе — % от P(y-1) группы;"
            "Итого (руб. / %),сумма базовых и отдельных — % от P(y-1) группы;"
            "Выпадение (если показано),см. раздел 7",
            "3500,5500",
        )
    )
    ops.append(
        p(
            "Группировка — суммирование по выбранным измерениям (группа груза, холдинг, вид перевозки и т.д.). "
            "Диаграмма отображает те же агрегаты в разрезе групп."
        )
    )
    ops.append(p("Для первого года сценария блок недоступен: эффект равен нулю."))

    # 6
    ops.append(h1("6. Блоки «Доходы всего» и «Объём перевозок»"))
    ops.append(h2("6.1. Доходы всего (млрд руб.)"))
    ops.append(p("Абсолютная провозная плата (доход) за год y:"))
    ops.append(eq(r"R(y) = \frac{1}{10^9}\sum P(y)"))
    ops.append(p("(сумма по маршрутам, с учётом выбранной группировки и фильтров)."))

    ops.append(h2("6.2. Объём перевозок (млн т.)"))
    ops.append(eq(r"Q(y) = \frac{1}{10^6}\sum V \times \mathrm{turnover}(y)"))
    ops.append(
        p(
            "где V — базовый объём маршрута. При включённом учёте выпадения объём корректируется "
            "(см. п. 6.3 и раздел 7)."
        )
    )

    ops.append(h2("6.3. Переключатель «Учёт выпадения»"))
    ops.append(p("При включении показатели пересчитываются как нетто:"))
    ops.append(eq(r"\mathrm{Net}(y) = \mathrm{Gross}(y) + \mathrm{Fallout}(y)"))
    ops.append(bullet("Gross — брутто (доход или объём без выпадения);"))
    ops.append(
        bullet(
            "Fallout — выпадение (как правило отрицательная величина при k < 1), уменьшающее доход и объём."
        )
    )

    # 7
    ops.append(h1("7. Эластичное выпадение (Δ эласт.)"))
    ops.append(p("Применяется, если в сценарии задан набор эластичности."))

    ops.append(h2("7.1. Маржинальность маршрута"))
    ops.append(
        eq(
            r"\mathrm{margin} = \frac{P_{\mathrm{market}} - C - RZD - Op - Trans}{P_{\mathrm{market}}}"
        )
    )
    ops.append(p("где:"))
    ops.append(bullet("P_market — рыночная цена за тонну;"))
    ops.append(bullet("C — себестоимость производства (если > 0), иначе полная себестоимость;"))
    ops.append(bullet("RZD — затраты РЖД за тонну (масштабируются при изменении тарифа);"))
    ops.append(bullet("Op — операторские затраты;"))
    ops.append(bullet("Trans — затраты на перевалку."))
    ops.append(p("При P_market ≤ 0 маржинальность принимается равной 0."))

    ops.append(h2("7.2. Коэффициент удержания спроса k"))
    ops.append(
        p(
            "По кривой эластичности выполняется lookup коэффициента по маржинальности "
            "(ступенчатая интерполяция «вниз» по точкам кривой). Режим задаётся в сценарии:"
        )
    )
    ops.append(
        table(
            "Режим,Формула;"
            "Абсолютный,k = lookup(margin_cur);"
            "Относительно базы,k = 1 + lookup(margin_cur) - lookup(margin_base);"
            "Комбинированный,при росте тарифа: k = min(1 lookup(margin)) / при снижении — как относительно базы / при нулевом изменении: k = 1",
            "2500,6500",
        )
    )
    ops.append(eq(r"k = \mathrm{lookup}(\mathrm{margin}_{\mathrm{cur}})"))
    ops.append(
        eq(
            r"k = 1 + \mathrm{lookup}(\mathrm{margin}_{\mathrm{cur}}) - \mathrm{lookup}(\mathrm{margin}_{\mathrm{base}})"
        )
    )
    ops.append(eq(r"k = \min(1,\ \mathrm{lookup}(\mathrm{margin}))"))
    ops.append(
        p(
            "Если у маршрута задан фиксированный коэффициент удержания (> 0), используется он."
        )
    )
    ops.append(p("Ограничение по загрузке предприятия (если включено в сценарии):"))
    ops.append(eq(r"k = \min(k,\ 1 + (1 - \mathrm{enterprise\_load}))"))
    ops.append(
        p(
            "Если enterprise_load ≥ 1, рост объёма не допускается (k = 1 в соответствующих ветках). "
            "Итоговый k не бывает отрицательным (k ≥ 0)."
        )
    )

    ops.append(h2("7.3. Отношение тарифа (вход для выпадения)"))
    ops.append(p("Сначала сравнивают текущий тариф с начальным:"))
    ops.append(eq(r"\mathrm{charge\_ratio} = \frac{T_{\mathrm{cur}}}{T_{\mathrm{init}}}"))
    ops.append(
        p(
            "где T_cur = P(y) / turnover(y) (тариф без оборота), T_init — начальная провозная плата маршрута."
        )
    )
    ops.append(
        bullet(
            "если charge_ratio = 1 (тариф не изменился) → выпадение равно нулю;"
        )
    )
    ops.append(
        bullet(
            "иначе по маржинальности (п. 7.1–7.2) получают коэффициент удержания k."
        )
    )

    ops.append(h2("7.4. Выпадение объёма"))
    ops.append(eq(r"\Delta V = V \times \mathrm{turnover}(y) \times (k - 1)"))
    ops.append(
        p(
            "где V — базовый объём маршрута (т). При k < 1 величина ΔV отрицательная (потеря тоннажа)."
        )
    )

    ops.append(h2("7.5. Выпадение доходов"))
    ops.append(
        p(
            "Выпадение доходов — потеря (или прирост) провозной платы из‑за реакции спроса "
            "на изменение тарифа. Считается после построения цепочки P(y) и получения k.",
            bold="true",
        )
    )
    ops.append(eq(r"\Delta R = P(y) \times (k - 1)"))
    ops.append(
        table(
            "Обозначение,Смысл;"
            "P(y),провозная плата маршрута за год y (брутто руб.);"
            "k,коэффициент удержания спроса (доля сохранившегося объёма);"
            "k - 1,относительное изменение объёма/спроса;"
            "ΔR,выпадение дохода руб.",
            "2000,7000",
        )
    )
    ops.append(p("Смысл формулы:"))
    ops.append(bullet("при k = 1 спрос не меняется → ΔR = 0;"))
    ops.append(bullet("при k = 0.95 спрос падает на 5% → доход падает на 5% от P(y);"))
    ops.append(bullet("при k > 1 (рост спроса) → ΔR положительное."))
    ops.append(
        p(
            "Нетто-доход (блок «Доходы всего» при включённом «Учёт выпадения»):"
        )
    )
    ops.append(eq(r"R_{\mathrm{net}}(y) = P(y) + \Delta R = P(y) \times k"))
    ops.append(p("На экране ΔR показывается в млрд руб.: ΔR / 10^9."))
    ops.append(
        p(
            "Итог: выпадение доходов = текущая провозная плата × (удержание спроса − 1). "
            "Это не отдельная «скидка» к тарифу а коррекция дохода из‑за изменения перевозимого объёма.",
            bold="true",
        )
    )

    # 8
    ops.append(h1("8. Округление и особые случаи"))
    ops.append(
        table(
            "Что,Правило;"
            "Промежуточные денежные суммы,до копеек (0.01 руб.);"
            "KPI в млрд руб.,до 0.1 млрд;"
            "Абсолютные доходы в млрд руб.,до 0.01 млрд;"
            "Объёмы в млн т,до 0.01 млн т (в таблице эффектов выпадение объёма — до 0.1);"
            "Проценты,до 0.1%;"
            "Знаменатель процента ≤ 0,показывается 0.0%;"
            "Первый год сценария,эффект = 0 — KPI и таблица эффектов по нему не используются",
            "4000,5000",
        )
    )

    # 9
    ops.append(h1("9. Числовой пример"))
    ops.append(h2("9.1. Эффект базовых и отдельных решений"))
    ops.append(p("Исходные данные одного маршрута (второй год сценария):"))
    ops.append(bullet("начальная (предыдущая) провозная плата: 1 000 000 000 руб. (1 млрд);"))
    ops.append(bullet("BTD: K_base = 1,10 (+10%);"))
    ops.append(bullet("одно правило: k_raw = 1,05; base_percent = 100% → k_eff = 1,05;"))
    ops.append(bullet("оборот не меняется (turnover = 1)."))
    ops.append(p("Расчёт эффекта:"))
    ops.append(eq(r"\Delta P_{\mathrm{base}} = 1 \times (1.10 - 1) = 0.1\ \mathrm{bln}\ (10\%)"))
    ops.append(eq(r"\Delta P_{\mathrm{rules}} = 1 \times (1.05 - 1) = 0.05\ \mathrm{bln}\ (5\%)"))
    ops.append(eq(r"\Delta P_{\mathrm{total}} = 0.15\ \mathrm{bln}\ (15\%)"))
    ops.append(p("Провозная плата в текущем году (брутто):"))
    ops.append(eq(r"P(y) = 1 \times (1.10 + 1.05 - 1) = 1.15\ \mathrm{bln}"))
    ops.append(p("(здесь 1 = 1 млрд руб. начальной провозной платы)"))
    ops.append(
        p(
            "Пример с оборотом: начальный тариф 100 руб., turnover = 1,2, без индексации → "
            "отображаемая провозная плата 100 × 1,2 = 120."
        )
    )

    ops.append(h2("9.2. Выпадение доходов и объёма"))
    ops.append(
        p(
            "Продолжаем тот же маршрут: P(y) = 1,15 млрд руб. Тариф вырос (charge_ratio > 1), "
            "спрос частично «отваливается»."
        )
    )
    ops.append(p("Дополнительно зададим:"))
    ops.append(bullet("базовый объём V = 1 000 000 т (1 млн т);"))
    ops.append(bullet("turnover = 1;"))
    ops.append(
        bullet(
            "коэффициент удержания k = 0,96 (спрос сохраняется на 96% падает на 4%)."
        )
    )
    ops.append(p("Выпадение объёма:"))
    ops.append(
        eq(
            r"\Delta V = 1000000 \times 1 \times (0.96 - 1) = -40000\ \mathrm{t} = -0.04\ \mathrm{mln\ t}"
        )
    )
    ops.append(p("Выпадение доходов:", bold="true"))
    ops.append(eq(r"\Delta R = 1.15 \times (0.96 - 1) = -0.046\ \mathrm{bln}"))
    ops.append(p("то есть −46 млн руб."))
    ops.append(p("Нетто при включённом «Учёт выпадения»:"))
    ops.append(
        table(
            "Показатель,Брутто,Выпадение,Нетто;"
            "Доход млрд руб.,1.15,-0.046,1.104;"
            "Объём млн т,1.00,-0.04,0.96",
            "2500,2000,2000,2500",
        )
    )
    ops.append(
        p(
            "Проверка: R_net = P(y) × k = 1,15 × 0,96 = 1,104 млрд — совпадает."
        )
    )
    ops.append(
        p(
            "Если бы k = 1 (тариф не изменился или спрос неэластичен), оба выпадения "
            "были бы равны нулю а нетто = брутто."
        )
    )

    batch(ops)

    # Styles / footer
    run(
        [
            "officecli",
            "set",
            str(FILE),
            "/",
            "--prop",
            "docDefaults.font=Calibri",
            "--prop",
            "docDefaults.fontSize=11pt",
        ]
    )
    run(
        [
            "officecli",
            "add",
            str(FILE),
            "/",
            "--type",
            "footer",
            "--prop",
            "type=default",
            "--prop",
            "size=9pt",
            "--prop",
            "text=Эффект от решений — формулы · стр. ",
            "--prop",
            "field=page",
        ]
    )
    run(["officecli", "set", str(FILE), "/footer[1]/p[1]", "--prop", "align=center"])

    # TOC after title
    run(
        [
            "officecli",
            "add",
            str(FILE),
            "/body",
            "--type",
            "toc",
            "--prop",
            "levels=1-2",
            "--prop",
            "hyperlinks=true",
            "--index",
            "2",
        ]
    )

    run(["officecli", "close", str(FILE)])
    run(["officecli", "validate", str(FILE)])
    run(["officecli", "query", str(FILE), "equation"])
    print(f"\nOK: {FILE}")


if __name__ == "__main__":
    main()
