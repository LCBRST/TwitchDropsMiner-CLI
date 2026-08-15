"""
TwitchDropsMiner — CLI entry point.

The original `main.py` was tkinter-based; this version is purely terminal-driven.
Set the env var `TDM_GUI=1` to opt back into the original GUI build.
"""

from __future__ import annotations

import io
import os
import sys
import signal
import asyncio
import logging
import argparse
import warnings
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler


def _watchdog_supervise() -> int:
    """Supervise a worker process, restarting it after a crash.

    Runs only in the top-level launcher. The worker is spawned with
    ``TDM_WORKER=1`` in its environment so it skips this branch and runs the
    normal entry point. Returns the worker's final exit code.
    """
    import time
    import subprocess

    # Exit codes that mean "don't restart":
    #   0 = clean shutdown, 2 = argparse usage error, 3 = lock held
    #   (another instance running), 4 = settings load failure.
    no_restart = {0, 2, 3, 4}
    env = dict(os.environ)
    env["TDM_WORKER"] = "1"

    # Reconstruct argv so it works both from source (`python main.py`) and from
    # a frozen binary (`./TwitchDropsMiner-CLI`), where sys.argv[0] == sys.executable.
    if sys.argv and os.path.realpath(sys.argv[0]) == os.path.realpath(sys.executable):
        relaunch = [sys.executable, *sys.argv[1:]]
    else:
        relaunch = [sys.executable, *sys.argv]

    delay = 5.0
    while True:
        start = time.monotonic()
        proc = subprocess.Popen(relaunch, env=env)

        def _forward(signum, _frame):
            try:
                proc.send_signal(signum)
            except Exception:
                pass

        prev_int = signal.signal(signal.SIGINT, _forward)
        prev_term = signal.signal(signal.SIGTERM, _forward)
        try:
            code = proc.wait()
        finally:
            signal.signal(signal.SIGINT, prev_int)
            signal.signal(signal.SIGTERM, prev_term)

        if code in no_restart:
            return code

        ran = time.monotonic() - start
        try:
            from constants import LOG_DIR
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(LOG_DIR / "restart.log", "a", encoding="utf8") as fh:
                fh.write(
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\t"
                    f"worker exited (code={code}, ran={ran:.0f}s), "
                    f"restarting in {delay:.0f}s\n"
                )
        except Exception:
            pass
        time.sleep(delay)
        # Back off if the worker keeps crashing immediately after launch.
        delay = 5.0 if ran >= 10 else min(delay * 2, 60.0)


if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()

    # Crash auto-restart: unless we're already the supervised worker (or the
    # user opted out), re-launch ourselves under a supervisor that restarts us
    # whenever we die (including OOM kills, which the worker can't catch itself).
    if os.environ.get("TDM_WORKER") != "1" and "--no-watchdog" not in sys.argv:
        sys.exit(_watchdog_supervise())

    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10 or higher is required")

    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        pass

    from translate import _
    from twitch import Twitch
    from settings import Settings
    from version import __version__
    from exceptions import CaptchaRequired, ReloadRequest
    from utils import lock_file
    from constants import LOGGING_LEVELS, FILE_FORMATTER, LOG_DIR, LOCK_PATH

    warnings.simplefilter("default", ResourceWarning)

    class ParsedArgs(argparse.Namespace):
        _verbose: int
        _debug_ws: bool
        _debug_gql: bool
        log: bool
        tray: bool
        dump: bool
        shell_enabled: bool
        token: str | None

        @property
        def logging_level(self) -> int:
            return LOGGING_LEVELS[min(self._verbose, 4)]

        @property
        def debug_ws(self) -> int:
            if self._debug_ws:
                return logging.DEBUG
            elif self._verbose >= 4:
                return logging.INFO
            return logging.NOTSET

        @property
        def debug_gql(self) -> int:
            if self._debug_gql:
                return logging.DEBUG
            elif self._verbose >= 4:
                return logging.INFO
            return logging.NOTSET

    parser = argparse.ArgumentParser(
        prog="twitch-drops-miner",
        description="Mine timed Twitch drops from the terminal.",
    )
    parser.add_argument("--version", action="version", version=f"v{__version__} (CLI)")
    parser.add_argument("-v", dest="_verbose", action="count", default=0,
                        help="Increase log verbosity (repeat up to -vvvv)")
    parser.add_argument("--tray", action="store_true",
                        help="Ignored in CLI mode (kept for compatibility)")
    parser.add_argument("--log", action="store_true", help="Tee logs to log.txt")
    parser.add_argument("--dump", action="store_true", help="Dump GQL responses")
    parser.add_argument("--no-shell", dest="shell_enabled", action="store_false",
                        default=True, help="Run without an interactive command prompt")
    parser.add_argument("--no-watchdog", dest="no_watchdog", action="store_true",
                        help="Disable the crash auto-restart supervisor")
    parser.add_argument("--token", default=None,
                        help="Path to a file with an OAuth token to seed cookies.jar")
    parser.add_argument("--debug-ws", dest="_debug_ws", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--debug-gql", dest="_debug_gql", action="store_true",
                        help=argparse.SUPPRESS)
    args: ParsedArgs = parser.parse_args(namespace=ParsedArgs())

    try:
        settings = Settings(args)
    except Exception:
        sys.stderr.write("Failed to load settings:\n")
        sys.stderr.write(traceback.format_exc())
        sys.exit(4)

    def _seed_token(token_path: str) -> None:
        from constants import COOKIES_PATH, ClientType
        with open(token_path, "r", encoding="utf8") as fh:
            token = fh.read().strip()
        if not token:
            raise ValueError("token file is empty")
        if COOKIES_PATH.exists():
            return
        import aiohttp
        jar = aiohttp.CookieJar()
        jar.update_cookies({"auth-token": token}, ClientType.ANDROID_APP.CLIENT_URL)
        jar.save(COOKIES_PATH)

    async def main() -> int:
        try:
            _.set_language(settings.language)
        except ValueError:
            pass

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

        if settings.logging_level > logging.DEBUG:
            logging.getLogger().addHandler(logging.NullHandler())
        log = logging.getLogger("TwitchDrops")
        # Emit INFO+ at minimum so the file log always captures useful state;
        # the console handler is explicitly capped to settings.logging_level.
        log.setLevel(min(settings.logging_level, logging.INFO))
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf8"
        )
        file_handler.setFormatter(FILE_FORMATTER)
        file_handler.setLevel(logging.INFO)
        log.addHandler(file_handler)
        logging.getLogger("TwitchDrops.gql").setLevel(settings.debug_gql)
        logging.getLogger("TwitchDrops.websocket").setLevel(settings.debug_ws)

        if args.token:
            try:
                _seed_token(args.token)
            except Exception as exc:
                sys.stderr.write(f"warning: --token seed failed: {exc}\n")

        client = Twitch(settings)
        loop = asyncio.get_running_loop()

        # Route unhandled task exceptions and any escaped exception to the file log.
        def _loop_exc_handler(loop, context):
            log.critical(
                f"Event loop exception: {context.get('message', 'unknown')}",
                exc_info=context.get("exception"),
            )

        loop.set_exception_handler(_loop_exc_handler)

        def _sys_excepthook(exc_type, exc_value, exc_tb):
            log.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))

        sys.excepthook = _sys_excepthook

        if sys.platform != "win32":
            loop.add_signal_handler(signal.SIGINT, lambda *_a: client.gui.close())
            loop.add_signal_handler(signal.SIGTERM, lambda *_a: client.gui.close())

        exit_status = 0
        while True:
            try:
                await client.run()
            except ReloadRequest:
                client.print(_("gui", "status", "exiting"))
                await client.shutdown()
                client = Twitch(settings)
                continue
            except CaptchaRequired:
                exit_status = 1
                client.prevent_close()
                client.print(_("error", "captcha"))
            except Exception:
                exit_status = 1
                client.prevent_close()
                client.print("Fatal error encountered:\n")
                client.print(traceback.format_exc())
                log.critical("Fatal error encountered", exc_info=True)
            break

        if sys.platform != "win32":
            loop.remove_signal_handler(signal.SIGINT)
            loop.remove_signal_handler(signal.SIGTERM)

        client.print(_("gui", "status", "exiting"))
        await client.shutdown()

        if not client.gui.close_requested:
            client.gui.tray.change_icon("error")
            client.print(_("status", "terminated"))
            client.gui.status.update(_("gui", "status", "terminated"))
            client.gui.grab_attention(sound=True)

        await client.gui.wait_until_closed()
        client.save(force=True)
        client.gui.stop()
        client.gui.close_window()
        return exit_status

    file: io.TextIOWrapper | None = None
    try:
        success, file = lock_file(LOCK_PATH)
        if not success:
            sys.stderr.write(
                "Another instance is already running. "
                "Remove lock.file if you're sure that's wrong.\n"
            )
            sys.exit(3)
        try:
            sys.exit(asyncio.run(main()))
        except KeyboardInterrupt:
            sys.exit(0)
    finally:
        if file is not None:
            file.close()
