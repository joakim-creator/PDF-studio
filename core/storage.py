"""
Fillagringen (F1-01; backend-grund 12).

Två sätt med samma gränssnitt:
- **local** (`STORAGE_MODE=local`, standard lokalt och i proven): filer i `STORAGE_FOLDER`.
- **azure** (`STORAGE_MODE=azure`, dev och prod): en privat behållare i Azure Blob Storage, Sweden Central
  (`AZURE_STORAGE_CONNECTION_STRING`, `AZURE_STORAGE_CONTAINER`). Provas mot Azurite, Microsofts emulator.

Nycklarna har formen `<bolag>/<område>/<uuid>.<ändelse>`; filnamnet användaren gav står bara i databasen. En fil
skrivs en gång och skrivs aldrig över (originalet rörs aldrig) — `put` vägrar en nyckel som redan finns.
"""

import contextlib
import os
import re
from pathlib import Path
from typing import Protocol

KEY_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}/[a-z]+/[0-9a-f]{32}\.[a-z0-9]{2,5}$')


class StorageError(RuntimeError):
    pass


def check_key(key: str) -> str:
    if not KEY_RE.match(key):
        raise StorageError(f'ogiltig lagringsnyckel: {key!r}')
    return key


class Storage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


class LocalStorage:
    def __init__(self, folder: str) -> None:
        self.root = Path(folder)

    def _path(self, key: str) -> Path:
        return self.root / check_key(key)

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open('xb') as f:   # x: aldrig skriva över
                f.write(data)
        except FileExistsError:
            raise StorageError(f'filen finns redan: {key}') from None

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            raise StorageError(f'filen finns inte: {key}') from None

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


class AzureBlobStorage:
    def __init__(self, connection_string: str, container: str) -> None:
        from azure.storage.blob import BlobServiceClient
        self.container = BlobServiceClient.from_connection_string(connection_string).get_container_client(container)

    def put(self, key: str, data: bytes) -> None:
        from azure.core.exceptions import ResourceExistsError
        try:
            self.container.upload_blob(check_key(key), data, overwrite=False)
        except ResourceExistsError:
            raise StorageError(f'filen finns redan: {key}') from None

    def get(self, key: str) -> bytes:
        from azure.core.exceptions import ResourceNotFoundError
        try:
            return bytes(self.container.download_blob(check_key(key)).readall())
        except ResourceNotFoundError:
            raise StorageError(f'filen finns inte: {key}') from None

    def delete(self, key: str) -> None:
        from azure.core.exceptions import ResourceNotFoundError
        with contextlib.suppress(ResourceNotFoundError):
            self.container.delete_blob(check_key(key))

    def exists(self, key: str) -> bool:
        return bool(self.container.get_blob_client(check_key(key)).exists())


def from_environment(default_folder: str) -> Storage:
    mode = os.environ.get('STORAGE_MODE', 'local')
    if mode == 'local':
        return LocalStorage(os.environ.get('STORAGE_FOLDER', default_folder))
    if mode == 'azure':
        conn = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
        container = os.environ.get('AZURE_STORAGE_CONTAINER')
        if not conn or not container:
            raise StorageError('STORAGE_MODE=azure kräver AZURE_STORAGE_CONNECTION_STRING och AZURE_STORAGE_CONTAINER')
        return AzureBlobStorage(conn, container)
    raise StorageError(f'okänt STORAGE_MODE: {mode}')
