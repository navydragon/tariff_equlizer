TASK_STATUSES = [
    ("backlog", "Бэклог"),
    ("open", "Открыта"),
    ("in_progress", "В работе"),
    ("review", "На проверке"),
    ("done", "Выполнена"),
    ("cancelled", "Отменена"),
]

TASK_PRIORITIES = [
    ("low", "Низкий"),
    ("medium", "Средний"),
    ("high", "Высокий"),
    ("urgent", "Срочный"),
]

TASK_TYPES = [
    ("bug", "Ошибка"),
    ("feature", "Функция"),
    ("question", "Вопрос"),
    ("improvement", "Улучшение"),
]

KANBAN_STATUSES = ["backlog", "open", "in_progress", "review", "done"]

STATUS_LABELS = dict(TASK_STATUSES)
PRIORITY_LABELS = dict(TASK_PRIORITIES)
TYPE_LABELS = dict(TASK_TYPES)
