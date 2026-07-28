# Ассистент «Экономика грузов» + MCP

Общий слой **domain tools** используется:

1. UI-чатом на странице `/route-analysis/`
2. MCP-сервером для Cursor / других агентов

## UI-чат

Панель «Ассистент» на странице «Экономика грузов».

- Быстрые вопросы (presets) работают **без LLM**.
- Свободный текст — через **Pydantic AI** Agent + OpenAI-compatible API при `ASSISTANT_LLM_ENABLED=true`.

### Env (`.env`)

```env
ASSISTANT_LLM_ENABLED=false
ASSISTANT_LLM_API_KEY=
ASSISTANT_LLM_BASE_URL=https://api.openai.com/v1
ASSISTANT_LLM_MODEL=gpt-4o-mini
ASSISTANT_CHAT_RATE_LIMIT_PER_MIN=30
```

API:

- `POST /assistant/api/chat/`
- `GET /assistant/api/presets/`

### Архитектура LLM

- Domain handlers: `assistant/domain/tools/route_analysis.py` (общий registry для UI presets и MCP)
- Pydantic AI Agent: `assistant/domain/services/agent.py` (`RunContext[AssistantDeps]`, tools без ручного tool-calling loop)
- Клиент: `assistant/domain/services/llm.py`

Для what-if («цена ×2») агент должен вызывать `simulate_parameter_factor`.

## MCP для Cursor

Запуск:

```bash
cd new_project
python manage.py run_mcp_server
```

Пример `mcp.json` (Cursor, файл `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "tariff-equalizer": {
      "type": "stdio",
      "command": "C:/path/to/new_project/venv/Scripts/python.exe",
      "args": [
        "C:/path/to/new_project/manage.py",
        "run_mcp_server"
      ],
      "cwd": "C:/path/to/new_project",
      "env": {
        "DJANGO_SETTINGS_MODULE": "config.settings"
      }
    }
  }
}
```

На Windows с кириллицей в пути пользователя Cursor может ломать абсолютный путь —
тогда используйте 8.3 short path (`dir /x`) или относительные пути от корня репо.
Абсолютный путь к `manage.py` в `args` обязателен, если `cwd` не применяется.

### Tools

| Tool | Описание |
|------|----------|
| `get_route_summary` | Карточка маршрута/сценария |
| `compute_route_analysis` | Компактный расчёт экономики |
| `get_kpi_summary` | KPI по годам |
| `get_effects_breakdown` | Вклад решений и правил |
| `get_equalizer_state` | Эквалайзер + overrides |
| `get_margin_drivers` | Драйверы маржинальности |
| `get_tariff_coefficients` | Коэффициенты BTD/rules |
| `simulate_parameter_factor` | What-if: параметр × factor, сравнение маржи |
| `rank_routes` | Топ маршрутов по грузу и метрике (transport/rzd/price/total_cost) |
| `list_domain_tools` | Список tools |

Resource: `methodology://route-analysis`

Все tools **read-only**.
