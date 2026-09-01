from __future__ import annotations

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
