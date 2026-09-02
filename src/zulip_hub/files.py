from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat


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


def open_directory(root: Path, *parts: str) -> int:
    """Descripteur d’un répertoire atteint sans jamais suivre de lien.

    Chaque segment est ouvert relativement au précédent avec ``O_NOFOLLOW`` :
    un répertoire intermédiaire remplacé par un lien fait échouer la descente
    au lieu de la détourner ailleurs.
    """
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts:
            nested = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = nested
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _write_relative(path: Path, data: bytes, flags: int, mode: int) -> None:
    """Écrit dans le répertoire parent ouvert lui-même sans suivre de lien.

    Protéger le seul dernier segment ne suffit pas : un parent remplacé par un
    lien détournerait l’écriture, ``O_NOFOLLOW`` ne s’appliquant qu’au segment
    final du chemin ouvert.
    """
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor = os.open(path.name, flags, mode, dir_fd=parent)
        try:
            os.write(descriptor, data)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)


def write_no_follow(path: Path, data: bytes, mode: int = 0o644) -> None:
    """Écrit *path* sans suivre de lien, ni au dernier segment ni au parent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_relative(
        path, data, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode,
    )


def write_exclusive(path: Path, data: bytes, mode: int = 0o600) -> None:
    """Crée *path*, en échouant s’il existe déjà, fût-ce sous forme de lien."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_relative(
        path, data, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode,
    )


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
    """Remplace *path* d’un seul tenant, sans suivre de lien.

    Le fichier temporaire est créé et publié relativement au répertoire parent,
    lui-même ouvert sans suivre de lien : un parent remplacé fait échouer
    l’écriture au lieu de la détourner vers sa cible.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = f".{path.name}.{os.getpid()}.{os.urandom(6).hex()}"
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600 if mode is None else mode,
            dir_fd=parent,
        )
        try:
            os.write(descriptor, content.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
    except BaseException:
        try:
            os.unlink(temporary, dir_fd=parent)
        except OSError:
            pass
        raise
    finally:
        os.close(parent)
