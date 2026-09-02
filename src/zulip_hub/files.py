from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import tempfile


BEGIN = "-- BEGIN omarchy-zulip-hub (managed)"
END = "-- END omarchy-zulip-hub (managed)"
HYPR_BLOCK = f'\n{BEGIN}\nrequire("hypr.zulip_hub")\n{END}\n'
MODULE_HEADER = "-- Omarchy Zulip Hub"


def is_managed_module(path: Path) -> bool:
    """True quand rien n’occupe *path*, ou quand Zulip Hub a écrit ce qui s’y trouve.

    L’examen porte sur le lien lui-même, jamais sur sa cible : un lien
    symbolique, fût-il pointé vers un fichier portant notre en-tête, ferait
    écrire ailleurs et n’est donc jamais reconnu comme géré. Un lien cassé
    n’est pas non plus un fichier absent, alors que ``exists()`` les confond.

    Toute version publiée du module commence par MODULE_HEADER : une mise à
    niveau reconnaît ainsi le fichier qu’elle a elle-même installé.
    """
    try:
        status = os.lstat(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    if not stat.S_ISREG(status.st_mode):
        return False
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(len(MODULE_HEADER)) == MODULE_HEADER
    except OSError:
        return False


def write_no_follow(path: Path, data: bytes, mode: int = 0o644) -> None:
    """Écrit *path* sans jamais suivre un lien symbolique au dernier segment."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    try:
        os.write(descriptor, data)
    finally:
        os.close(descriptor)


def write_exclusive(path: Path, data: bytes, mode: int = 0o600) -> None:
    """Crée *path*, en échouant s’il existe déjà, fût-ce sous forme de lien."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode,
    )
    try:
        os.write(descriptor, data)
    finally:
        os.close(descriptor)


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
