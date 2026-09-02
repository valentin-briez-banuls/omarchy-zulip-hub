from __future__ import annotations

from dataclasses import dataclass
import os
import select
import shutil
import signal
import subprocess
import time


# Les exécutables auxiliaires sont cherchés ici et nulle part ailleurs : un
# PATH hérité laisserait un répertoire écrivable primer sur /usr/bin.
TRUSTED_PATH = "/usr/local/bin:/usr/bin:/bin"

# Sortie retenue avant que la commande soit coupée. La borne s’applique
# pendant la production, pas après : accumuler puis tronquer laisserait un
# producteur rapide épuiser la mémoire.
MAX_OUTPUT_BYTES = 1024 * 1024

# Seules ces variables traversent : les outils de session en ont besoin pour
# joindre le bus, le compositeur ou le trousseau. Tout le reste est écarté.
PASSED_THROUGH = (
    "DBUS_SESSION_BUS_ADDRESS",
    "DISPLAY",
    "HOME",
    "HYPRLAND_INSTANCE_SIGNATURE",
    "USER",
    "WAYLAND_DISPLAY",
    "XDG_CURRENT_DESKTOP",
    "XDG_RUNTIME_DIR",
    "XDG_SESSION_TYPE",
)

_CHUNK = 65536
_REAP_SECONDS = 2.0


class CommandError(RuntimeError):
    """Une commande auxiliaire est introuvable, a expiré, ou a trop parlé."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str


def available(name: str) -> bool:
    """Vrai si *name* existe dans le PATH de confiance."""
    try:
        resolve(name)
    except CommandError:
        return False
    return True


def spawn(argv: list[str]) -> None:
    """Lance une commande sans l’attendre : détachée, muette, sans héritage."""
    executable = resolve(argv[0])
    try:
        subprocess.Popen(
            [executable, *argv[1:]],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment(),
            start_new_session=True,
        )
    except OSError as exc:
        raise CommandError(f"exécution impossible: {argv[0]}") from exc


def resolve(name: str) -> str:
    """Chemin absolu d’un exécutable, cherché dans le seul PATH de confiance."""
    if os.path.isabs(name):
        return name
    found = shutil.which(name, path=TRUSTED_PATH)
    if found is None:
        raise CommandError(f"exécutable introuvable: {name}")
    return found


def environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    reduced = {"PATH": TRUSTED_PATH, "LC_ALL": "C.UTF-8"}
    for name in PASSED_THROUGH:
        value = os.environ.get(name)
        if value is not None:
            reduced[name] = value
    if extra:
        reduced.update(extra)
    return reduced


def _reap(process: subprocess.Popen) -> None:
    """Termine le groupe entier, puis s’assure qu’il a bien disparu.

    Signaler le seul chef de groupe laisserait vivre les enfants qu’il a
    détachés, et le tube resterait ouvert.
    """
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if process.poll() is not None:
            break
        try:
            os.killpg(process.pid, sig)
        except (ProcessLookupError, PermissionError):
            process.kill()
        try:
            process.wait(timeout=_REAP_SECONDS)
        except subprocess.TimeoutExpired:
            continue
    if process.stdout is not None:
        process.stdout.close()


def run(
    argv: list[str],
    *,
    stdin: str | None = None,
    timeout: float = 30.0,
    env_extra: dict[str, str] | None = None,
) -> CommandResult:
    """Exécute une commande de confiance, bornée en temps et en sortie."""
    executable = resolve(argv[0])
    try:
        process = subprocess.Popen(
            [executable, *argv[1:]],
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=environment(env_extra),
            start_new_session=True,
        )
    except OSError as exc:
        raise CommandError(f"exécution impossible: {argv[0]}") from exc

    collected = bytearray()
    deadline = time.monotonic() + timeout
    try:
        if stdin is not None and process.stdin is not None:
            process.stdin.write(stdin.encode("utf-8"))
            process.stdin.close()
        stream = process.stdout
        assert stream is not None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CommandError(f"délai dépassé: {argv[0]}")
            ready, _, _ = select.select([stream], [], [], min(remaining, 0.2))
            if not ready:
                continue
            chunk = os.read(stream.fileno(), _CHUNK)
            if not chunk:
                break
            collected.extend(chunk)
            if len(collected) > MAX_OUTPUT_BYTES:
                raise CommandError(f"sortie trop volumineuse: {argv[0]}")
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            time.sleep(0.02)
        else:
            raise CommandError(f"délai dépassé: {argv[0]}")
    except (BrokenPipeError, OSError) as exc:
        _reap(process)
        raise CommandError(f"communication interrompue: {argv[0]}") from exc
    except CommandError:
        _reap(process)
        raise
    finally:
        if process.poll() is None:
            _reap(process)
        elif process.stdout is not None:
            process.stdout.close()

    return CommandResult(
        returncode=process.returncode,
        stdout=collected.decode("utf-8", errors="replace"),
    )
