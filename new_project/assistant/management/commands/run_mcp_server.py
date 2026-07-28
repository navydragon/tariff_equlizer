from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Запускает MCP-сервер (stdio) с domain tools «Экономика грузов». "
        "Для подключения в Cursor см. assistant/README.md."
    )

    def handle(self, *args, **options):
        from assistant.mcp.server import run_stdio

        self.stdout.write(self.style.NOTICE("Starting tariff-equalizer MCP server (stdio)…"))
        run_stdio()
