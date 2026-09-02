from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import tempfile


BEGIN = "-- BEGIN omarchy-zulip-hub (managed)"
END = "-- END omarchy-zulip-hub (managed)"
HYPR_BLOCK = f'\n{BEGIN}\nrequire("hypr.zulip_hub")\n{END}\n'
MODULE_HEADER = "-- Omarchy Zulip Hub"


def is_managed_module(path: Path) -> bool:
    """True when nothing occupies *path* or when Zulip Hub wrote what is there.

    Any released version of the module starts with MODULE_HEADER, so an upgrade
    recognises the file it installed previously while a foreign file is left alone.
    """
    if not path.exists():
        return True
    return path.read_text(encoding="utf-8", errors="replace").startswith(MODULE_HEADER)


@contextmanager
def single_instance(path: Path) -> Iterator[None]:
    """Ne laisse quun seul bridge travailler a la fois.

    Le shell peut tenir deux instances du service du plugin en vie a la fois :
    une mise a jour charge la nouvelle avant que lancienne ne soit detruite.
    Deux bridges ouvriraient deux files devenements Zulip et doubleraient les
    notifications. Le second attend ici, sans reseau ni etat, et prend le
    relais de lui-meme si le premier sarrete.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_atomic(path: Path, content: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
