"""Markdown -> PDF.

The report is authored once, in Markdown, because that is what a reviewer reads
in the repo. The PDF is a rendering of the same text, so the two can never
disagree. Deliberately a small subset renderer (headings, tables, images,
bold/inline code, paragraphs) rather than a full CommonMark implementation: the
generator only ever emits this subset, and a renderer that accepts more than its
generator produces is a false promise.
"""

from __future__ import annotations

import re
from pathlib import Path

from fpdf import FPDF

_FONT_CANDIDATES = {
    "DejaVuSans": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans-Bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSansMono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
}

BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
CODE_RE = re.compile(r"`([^`]+)`")
# A superscript-digit run in a chemical formula, kept as text but rendered upright.
SUB_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


class _PDF(FPDF):
    def footer(self) -> None:
        self.set_y(-13)
        self.set_font("DejaVuSans", size=7.5)
        self.set_text_color(120)
        self.cell(0, 6, f"GHG Emissions Inventory  ·  page {self.page_no()}", align="C")


def _available_fonts() -> dict[str, str]:
    return {name: path for name, path in _FONT_CANDIDATES.items() if Path(path).exists()}


def _setup(pdf: _PDF) -> None:
    fonts = _available_fonts()
    if "DejaVuSans" not in fonts:
        raise RuntimeError(
            "DejaVu fonts not found at /usr/share/fonts/truetype/dejavu; "
            "the PDF needs them for the CO₂ subscript and the table glyphs. "
            "Install fonts-dejavu-core."
        )
    for name, path in fonts.items():
        pdf.add_font(name, "", path)
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_page()
    pdf.set_margins(16, 16, 16)


def _snippet_to_cell(text: str) -> str:
    """Strip the markdown the PDF font cannot render, keeping the words."""
    text = BOLD_RE.sub(r"\1", text)
    text = CODE_RE.sub(r"\1", text)
    return text.replace("₂", "2").replace("₃", "3").replace("₄", "4")


def _write_table(pdf: _PDF, rows: list[str], available_width: float) -> None:
    """Render a pipe table with content-proportional column widths."""
    cells = [[c.strip() for c in row.strip().strip("|").split("|")] for row in rows]
    if len(cells) < 3:
        return
    header, body = cells[0], cells[2:]  # index 1 is the --- separator
    ncols = len(header)
    body = [row for row in body if len(row) == ncols]
    if not body:
        return

    # Width from content, not the column count: a 9-column ledger with one long
    # source name and eight short numbers reads as garbage in equal columns.
    # The sqrt keeps one long cell from stealing the page.
    def longest(index: int) -> float:
        values = [len(_snippet_to_cell(row[index])) for row in body]
        # The header gets a bonus: a wrapped header ("GWP10 / 0") is worse than a
        # slightly wide column, so it should win width against short numbers.
        values.append(len(_snippet_to_cell(header[index])) * 1.25)
        return max(values)

    lengths = [longest(i) for i in range(ncols)]
    weights = [max(3.0, min(length, 40.0)) ** 0.8 for length in lengths]
    total_weight = sum(weights)
    widths = [available_width * w / total_weight for w in weights]
    scale = available_width / sum(widths)
    widths = [w * scale for w in widths]

    # Right-align a column whose body is mostly numbers.
    numeric = []
    for i in range(ncols):
        values = [row[i].strip() for row in body]
        numbers = sum(1 for v in values if re.fullmatch(r"[-+]?[\d,.%—]+", v))
        numeric.append(numbers >= 0.7 * len(values))

    font_size = 6.4 if ncols >= 8 else 7.2
    line_h = font_size * 0.72 + 1.4
    padding = 1.2
    bottom = pdf.h - 18

    def draw_row(row_cells: list[str], *, is_header: bool) -> None:
        nonlocal pdf
        face = "DejaVuSans-Bold" if is_header else "DejaVuSans"
        pdf.set_font(face, size=font_size)
        heights = [
            pdf.multi_cell(
                widths[i] - padding, line_h, _snippet_to_cell(row_cells[i]),
                align="L", dry_run=True, output="HEIGHT",
            )
            for i in range(ncols)
        ]
        row_h = max(heights) + 2.2
        if pdf.get_y() + row_h > bottom:
            pdf.add_page()
            pdf.set_font(face, size=font_size)
        y0 = pdf.get_y() + 0.6
        pdf.set_fill_color(238, 240, 243) if is_header else pdf.set_fill_color(255, 255, 255)
        x = pdf.l_margin
        for i in range(ncols):
            pdf.set_xy(x, y0)
            pdf.multi_cell(
                widths[i] - padding,
                line_h,
                _snippet_to_cell(row_cells[i]),
                align="R" if numeric[i] and not is_header else "L",
                fill=True,
                border=0,
            )
            x += widths[i]
        # Set the baseline explicitly. Leaving y wherever the last (possibly
        # short) cell ended is what made rows overlap.
        pdf.set_y(y0 + row_h)
        pdf.set_draw_color(215, 218, 222)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + available_width, pdf.get_y())

    draw_row(header, is_header=True)
    for row in body:
        draw_row(row, is_header=False)
    pdf.set_y(pdf.get_y() + 1.0)
    pdf.set_font("DejaVuSans", size=9.2)


def markdown_to_pdf(markdown: str, path: str | Path, *, base_dir: str | Path | None = None) -> Path:
    base = Path(base_dir) if base_dir else Path.cwd()
    pdf = _PDF(format="A4")
    _setup(pdf)
    width = pdf.w - pdf.l_margin - pdf.r_margin

    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()

        if not line.strip():
            pdf.ln(2.0)
            i += 1
            continue

        # image
        image = re.fullmatch(r"!\[[^\]]*\]\(([^)]+)\)", line.strip())
        if image:
            candidate = Path(image.group(1))
            if not candidate.is_absolute():
                candidate = base / candidate
            if candidate.exists():
                if pdf.get_y() + 60 > pdf.h - 20:
                    pdf.add_page()
                pdf.image(str(candidate), w=min(width, 168))
                pdf.ln(2)
            i += 1
            continue

        # table
        if line.lstrip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            _write_table(pdf, block, width)
            pdf.ln(1.5)
            continue

        # heading
        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            text = _snippet_to_cell(heading.group(2))
            sizes = {1: 15.0, 2: 11.5, 3: 9.8, 4: 9.0}
            pdf.ln(4.0 if level <= 2 else 2.5)
            if pdf.get_y() > pdf.h - 45:
                pdf.add_page()
            pdf.set_font("DejaVuSans-Bold", size=sizes.get(level, 9.0))
            pdf.set_text_color(17, 24, 39)
            pdf.multi_cell(width, 6.2, text)
            if level == 1:
                pdf.set_draw_color(192, 57, 43)
                pdf.set_line_width(0.7)
                pdf.line(pdf.l_margin, pdf.get_y() + 1, pdf.l_margin + width, pdf.get_y() + 1)
                pdf.set_line_width(0.2)
                pdf.ln(3)
            else:
                pdf.ln(1.2)
            pdf.set_font("DejaVuSans", size=9.2)
            i += 1
            continue

        # paragraph (consume consecutive non-special lines)
        para = [raw]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
            r"^(#{1,4}\s|\||!\[)", lines[i].lstrip()
        ):
            para.append(lines[i])  # keep trailing spaces: they signal a hard break
            i += 1
        text = ""
        for index, piece in enumerate(para):
            hard_break = piece.endswith("  ")  # check before rstrip eats it
            text += piece.rstrip().strip()
            if index < len(para) - 1:
                # Markdown hard break: two trailing spaces means a new line, not a
                # wrapped run-on. The generator uses it for the metadata block.
                text += "\n" if hard_break else " "
        pdf.set_font("DejaVuSans", size=9.2)
        pdf.set_text_color(31, 41, 55)
        pdf.multi_cell(width, 5.2, _snippet_to_cell(text), align="L")
        pdf.ln(1.0)

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    return out
