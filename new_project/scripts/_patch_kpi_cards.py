from pathlib import Path

p = Path(__file__).resolve().parents[1] / "core/static/core/js/app/controllers/decision_effects_controller.js"
text = p.read_text(encoding="utf-8")

start = text.index('            <div class="decision-effects-kpi-card">')
end = text.index("          `;", start)
old = text[start:end]

new = """            <article class="decision-effects-kpi-card">
              <motion class="decision-effects-kpi-card__year">${escapeHtml(String(card.year))} год</div>
              <div class="decision-effects-kpi-card__body">
                <div class="decision-effects-kpi-card__info">
                  <div class="decision-effects-kpi-card__count">
                    <span class="decision-effects-kpi-card__total-value">${escapeHtml(card.total_bln)}</span>
                    <span class="decision-effects-kpi-card__total-unit">млрд</span>
                  </div>
                  <p class="decision-effects-kpi-card__total-caption">
                    Индексация<span class="decision-effects-kpi-card__total-caption-pct"> (${escapeHtml(totalPct)}%)</span>
                  </p>
                </div>
                <div class="decision-effects-kpi-card__split">
                  <div class="decision-effects-kpi-card__split-item">
                    <div class="decision-effects-kpi-card__count">
                      <span class="decision-effects-kpi-card__split-value">${escapeHtml(card.base_bln)}</span>
                      <span class="decision-effects-kpi-card__split-unit">млрд</span>
                    </div>
                    <div class="decision-effects-kpi-card__split-meta">
                      <span class="decision-effects-kpi-card__split-label">Базовые решения</span>
                      <span class="decision-effects-kpi-card__split-pct">(+${escapeHtml(basePct)}%)</span>
                    </div>
                  </div>
                  <div class="decision-effects-kpi-card__split-item">
                    <div class="decision-effects-kpi-card__count">
                      <span class="decision-effects-kpi-card__split-value">${escapeHtml(card.rules_bln)}</span>
                      <span class="decision-effects-kpi-card__split-unit">млрд</span>
                    </div>
                    <div class="decision-effects-kpi-card__split-meta">
                      <span class="decision-effects-kpi-card__split-label">Отдельные решения</span>
                      <span class="decision-effects-kpi-card__split-pct">(+${escapeHtml(rulesPct)}%)</span>
                    </div>
                  </div>
                </div>
              </div>
            </article>"""

new = new.replace("motion", "div")

if old not in text:
    raise SystemExit("old block not found")

p.write_text(text.replace(old, new, 1), encoding="utf-8")
print("patched")
