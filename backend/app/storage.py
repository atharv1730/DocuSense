import os
import shutil
from pathlib import Path
from typing import Protocol, BinaryIO

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


class Storage(Protocol):
    def save(self, file_id: str, data: BinaryIO) -> str: ...
    def open(self, path: str) -> BinaryIO: ...
    def delete(self, path: str) -> None: ...


class LocalStorage:
    def __init__(self, base_dir: Path = UPLOAD_DIR):
        self.base_dir = base_dir
        self.base_dir.mkdir(exist_ok=True)

    def save(self, file_id: str, data: BinaryIO) -> str:
        path = self.base_dir / file_id
        with open(path, "wb") as f:
            shutil.copyfileobj(data, f)
        return str(path)

    def open(self, path: str) -> BinaryIO:
        return open(path, "rb")

    def delete(self, path: str) -> None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


storage = LocalStorage()