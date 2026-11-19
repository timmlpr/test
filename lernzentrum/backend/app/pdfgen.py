"""Minimal PDF writer (one text page per slide) for demo material – no extra dependency."""
from __future__ import annotations

import textwrap


def _esc(s: str) -> bytes:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("cp1252", errors="replace")


def slides_pdf(title: str, pages: list[str]) -> bytes:
    objs: list[bytes] = []
    page_ids = []
    objs.append(b"")  # 1 catalog placeholder
    objs.append(b"")  # 2 pages placeholder
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    for i, text in enumerate(pages, 1):
        head, _, body = text.partition(". ")
        lines = [(f"{i}  {head}", 20, True)] + [(l, 14, False) for l in textwrap.wrap(body, 78)]
        y = 540
        stream = b"BT 0.18 0.36 0.55 rg "
        for line, size, bold in lines:
            stream += b"/F%d %d Tf 1 0 0 1 48 %d Tm (" % (2 if bold else 1, size, y) + _esc(line) + b") Tj "
            y -= 34 if bold else 20
            stream += b"0.1 0.1 0.1 rg " if bold else b""
        stream += b"/F1 9 Tf 1 0 0 1 48 30 Tm 0.5 0.5 0.5 rg (" + _esc(title) + b") Tj ET"
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        content_id = len(objs)
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /Font << /F1 3 0 R "
                    b"/F2 4 0 R >> >> /Contents %d 0 R >>" % content_id)
        page_ids.append(len(objs))
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[1] = b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % p for p in page_ids) + b"] /Count %d >>" % len(page_ids)
    out = b"%PDF-1.4\n"
    offsets = []
    for n, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out
