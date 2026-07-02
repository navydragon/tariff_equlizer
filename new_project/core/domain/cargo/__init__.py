"""
Домен грузов (ETSNG).

Не импортируем здесь подмодули с Django-зависимостями (services, repositories),
чтобы standalone-скрипты могли использовать чистые модули вроде `formatting`.
Импортируйте напрямую:

- `core.domain.cargo.formatting`
- `core.domain.cargo.services`
- `core.domain.cargo.dto`
"""

__all__: list[str] = []
