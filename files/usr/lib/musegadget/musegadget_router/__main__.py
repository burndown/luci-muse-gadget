"""musegadget with router capabilities added.

    python3 -m musegadget_router run --run-as muse     same as `musegadget run`
    python3 -m musegadget_router catalog               print the capability list as JSON

The SDK is left untouched: this wraps it, adds the enabled router commands to
the list it registers with Muse, and answers them before the SDK's own
command handling.
"""

from __future__ import annotations

import json
import logging
import sys

from musegadget import executor

from . import capabilities

log = logging.getLogger("musegadget.router")


class RouterExecutor(executor.Executor):
    def __init__(self, account) -> None:
        super().__init__(account)
        enabled = capabilities.enabled_ids()
        disabled = capabilities.disabled_generic()
        for name in disabled:
            executor.COMMAND_SPECS.pop(name, None)
        for cap_id in enabled:
            executor.COMMAND_SPECS[cap_id] = capabilities.BY_ID[cap_id]["spec"]
        self._enabled = frozenset(enabled)
        self._disabled = frozenset(disabled)
        log.info("advertising commands: %s", ", ".join(sorted(executor.COMMAND_SPECS)))

    def run(self, command, params, timeout_ms=None):
        if command in self._disabled:
            return executor.error(f"{command} is turned off on this router")
        handler = capabilities.HANDLERS.get(command)
        if handler is None:
            return super().run(command, params, timeout_ms)
        if command not in self._enabled:
            return executor.error(f"{command} is turned off on this router")
        try:
            return handler(params if isinstance(params, dict) else {})
        except ValueError as exc:
            return executor.error(str(exc))
        except Exception as exc:  # a broken handler must not take the session down
            log.exception("%s failed", command)
            return executor.error(f"{type(exc).__name__}: {exc}")


def main() -> int:
    if sys.argv[1:2] == ["catalog"]:
        print(json.dumps(capabilities.catalog()))
        return 0
    # cli.cmd_run imports Executor from this module when it starts, so swapping it
    # here is enough to put ours in charge.
    executor.Executor = RouterExecutor
    from musegadget.cli import main as sdk_main
    return sdk_main()


sys.exit(main())
