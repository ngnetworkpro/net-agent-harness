from rich.console import Console
from .run_store import RunStore

console = Console()

class RunProgressReporter:
    STATUS_STYLES = {
        "running": ("cyan", "white"),
        "blocked": ("bold yellow", "yellow"),
        "failed": ("bold red", "red"),
        "completed": ("bold green", "green"),
    }

    def __init__(self, run_store: RunStore, run_id: str, console_obj: Console | None = None):
        self.run_store = run_store
        self.run_id = run_id
        self.console = console_obj or console

    def update(self, stage: str, status: str, message: str, **extra) -> None:
        text_style, spinner_style = self.STATUS_STYLES.get(status, ("white", "white"))
        self.console.print(f"[{text_style}]{stage}[/{text_style}]: {message}", style=spinner_style)
        self.run_store.update_stage(
            run_id=self.run_id,
            stage=stage,
            status=status,
            message=message,
            **extra,
        )