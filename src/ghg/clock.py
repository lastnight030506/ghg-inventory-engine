"""One clock for the whole run.

A report that stamps `datetime.now()` into its own text cannot be diffed: two runs
over identical data differ, so the committed artifact can never be verified and a
"report is current" check can only compare the numbers. Honouring
`SOURCE_DATE_EPOCH` (the reproducible-builds convention) means CI and a developer
can pin the timestamp and get byte-identical output.

Resolution order:

1. `$SOURCE_DATE_EPOCH`, if set and valid — the reproducible-builds standard;
2. otherwise the wall clock.

`GHG_BUILD_EPOCH` is accepted as an alias because it reads better in a Makefile,
but `SOURCE_DATE_EPOCH` is the one other tools already understand.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

_ENV_VARS = ("SOURCE_DATE_EPOCH", "GHG_BUILD_EPOCH")


def generation_time() -> datetime:
    """The timestamp to stamp into a report, in UTC."""
    for name in _ENV_VARS:
        raw = os.environ.get(name)
        if raw is None or not raw.strip():
            continue
        try:
            return datetime.fromtimestamp(int(raw.strip()), tz=UTC)
        except (ValueError, OverflowError, OSError):
            raise ValueError(
                f"{name}={raw!r} is not a valid Unix timestamp; "
                "use an integer number of seconds since 1970-01-01 UTC"
            ) from None
    return datetime.now(UTC).replace(microsecond=0)


def generation_stamp() -> str:
    """The human-readable form used in the report header."""
    return generation_time().strftime("%Y-%m-%d %H:%M UTC")
