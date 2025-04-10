import pathlib
import shutil
import time
from functools import cached_property

from remember_me_mcp_server.errors import BackupError


class Backup:
    def __init__(self, target, path):
        self._target = target
        self._path = path

    @cached_property
    def path(self) -> pathlib.Path:
        path = pathlib.Path(self._path).expanduser()
        path.mkdir(exist_ok=True, parents=True)
        return path

    @cached_property
    def target_path(self) -> pathlib.Path:
        return pathlib.Path(self._target).expanduser()

    def clear(self) -> None:
        paths = [f for f in self.path.iterdir() if f.is_file()]
        if not paths:
            raise BackupError("No backups to clear")
        for path in paths:
            path.unlink()

    def create(self, name: str | None = None) -> None:
        name = name or time.time_ns()
        backup_path = self.path / f"{name}.{self.target_path.name}"
        if backup_path.exists():
            raise BackupError(f"Backup already exists: {name}")
        shutil.copy(self.target_path, backup_path)
        return name

    def list(self) -> list[str]:
        return [f.name[:-6] for f in self.path.iterdir() if f.is_file()]

    def remove(self, name: str) -> None:
        backup_path = self.path / f"{name}.{self.target_path.name}"
        if not backup_path.exists():
            raise BackupError(f"Backup does not exist: {name}")
        backup_path.unlink()

    def restore(self, name: str) -> None:
        backup_path = self.path / f"{name}.{self.target_path.name}"
        if not backup_path.exists():
            raise BackupError(f"Backup doesnt exist: {name}")
        shutil.copy(backup_path, self.target_path)
