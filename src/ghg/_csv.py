"""CSV reading hardened for files a human actually produced.

Excel and hand-edited exports differ from a clean test fixture in three ways that
used to reach the parser and produce either a `None` crash or a silently wrong
number:

- a header with surrounding spaces (`" site "`), which then looks like a missing
  column;
- a duplicated column name, where `csv.DictReader` keeps the last value and the
  first is silently discarded;
- a short or ragged row (an unclosed quote, a dropped trailing comma), which
  yields `None` for the missing cells and raises `AttributeError` deep in a
  validator instead of naming the line.

Both loaders go through this so the behaviour cannot drift between them.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path


# A row shorter than the header is padded with empty strings so the validators
# report "blank field" with a line number, rather than crashing on None. A row
# longer than the header is a real malformation and is rejected, because the
# surplus cell means the file's columns do not line up with its header.
class CsvFormatError(ValueError):
    """A structural problem with the CSV itself, distinct from a bad value."""


def read_rows(path: Path, required: tuple[str, ...]) -> Iterator[tuple[int, dict[str, str]]]:
    """Yield (line number, normalised row) for a CSV whose header carries `required`.

    Line numbers count from 1 at the header so they match an editor's gutter.
    """
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            raw_header = next(reader)
        except StopIteration:
            raise CsvFormatError(f"{path.name}: file is empty") from None

        header = [name.strip() for name in raw_header]

        duplicates = sorted({name for name in header if header.count(name) > 1} - {""})
        if duplicates:
            # Whichever copy DictReader keeps, the file is ambiguous: two columns
            # claim the same field and the user cannot tell which one won.
            raise CsvFormatError(
                f"{path.name}: duplicate column(s) {duplicates} in header {header}"
            )

        missing = [name for name in required if name not in header]
        if missing:
            raise CsvFormatError(
                f"{path.name}: missing required columns {missing}; got {header}"
            )

        for line, cells in enumerate(reader, start=2):
            if not any(cell.strip() for cell in cells):
                continue  # a blank line is not a row
            if len(cells) > len(header):
                raise CsvFormatError(
                    f"{path.name} line {line}: {len(cells)} cells for {len(header)} "
                    f"columns; check for an unescaped comma or a stray quote"
                )
            padded = cells + [""] * (len(header) - len(cells))
            yield line, dict(zip(header, padded, strict=True))
