from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.ingest.local_snapshot import LocalSnapshotResult, prepare_local_snapshot


pytestmark = pytest.mark.unit


def _text_pdf_bytes(text: str, *, title: str | None = None) -> bytes:
    escaped_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = f"BT /F1 12 Tf 10 100 Td ({escaped_text}) Tj ET".encode("ascii")

    def stream(data: bytes) -> bytes:
        return f"<< /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream"

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        stream(content),
    ]
    info_ref = ""
    if title is not None:
        escaped_title = title.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        objects.append(f"<< /Title ({escaped_title}) >>".encode("ascii"))
        info_ref = f" /Info {len(objects)} 0 R"

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R{info_ref} >>\n"
            f"startxref\n{xref_offset}\n%%EOF"
        ).encode()
    )
    return bytes(pdf)


def _prepared(result: object) -> LocalSnapshotResult:
    assert isinstance(result, LocalSnapshotResult)
    return result


def test_local_text_html_and_pdf_use_their_owned_pure_extractors(tmp_path: Path) -> None:
    text_bytes = b"  local research note  \n"
    (tmp_path / "note.md").write_bytes(text_bytes)
    (tmp_path / "article.html").write_text(
        "<html><head><title>HK Water</title></head>"
        "<body><article><p>Dongjiang water agreement evidence.</p></article></body></html>",
        encoding="utf-8",
    )
    (tmp_path / "paper.pdf").write_bytes(
        _text_pdf_bytes("PDF body evidence", title="Primary PDF Title")
    )

    text = _prepared(
        prepare_local_snapshot(project_key="hk", source_root=tmp_path, locator="note.md")
    )
    html = _prepared(
        prepare_local_snapshot(project_key="hk", source_root=tmp_path, locator="article.html")
    )
    pdf = _prepared(
        prepare_local_snapshot(project_key="hk", source_root=tmp_path, locator="paper.pdf")
    )

    assert text.content == "local research note"
    assert text.raw_sha256 == sha256(text_bytes).hexdigest()
    assert text.extractor == "material_input.prepare_material"
    assert html.source_title == "HK Water"
    assert "Dongjiang water agreement evidence" in (html.content or "")
    assert pdf.source_title == "Primary PDF Title"
    assert "PDF body evidence" in (pdf.content or "")
    assert {text.extraction_status, html.extraction_status, pdf.extraction_status} == {"extracted"}


def test_local_snapshot_rejects_parent_and_outside_symlink_before_open(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("must not be opened", encoding="utf-8")
    (source_root / "escape.txt").symlink_to(outside)

    with patch.object(Path, "open", side_effect=AssertionError("outside file opened")):
        parent = _prepared(
            prepare_local_snapshot(
                project_key="hk",
                source_root=source_root,
                locator="../outside.txt",
            )
        )
        symlink = _prepared(
            prepare_local_snapshot(
                project_key="hk",
                source_root=source_root,
                locator="escape.txt",
            )
        )

    for result in (parent, symlink):
        assert result.extraction_status == "reference_only"
        assert result.reason == "outside_root"
        assert result.raw_sha256 is None
        assert result.mime_type is None


def test_oversized_pdf_text_is_explicitly_partial(tmp_path: Path) -> None:
    (tmp_path / "long.pdf").write_bytes(_text_pdf_bytes("A" * 50_020))

    result = _prepared(
        prepare_local_snapshot(project_key="hk", source_root=tmp_path, locator="long.pdf")
    )

    assert result.extraction_status == "partial"
    assert result.reason == "content_truncated"
    assert result.source_title is None
    assert result.content is not None
    assert len(result.content) == 50_000


@pytest.mark.parametrize(
    ("name", "raw", "reason"),
    [
        ("bad.txt", b"\xff", "invalid_encoding"),
        ("empty.md", b" \n\t", "empty"),
        ("blob.bin", b"opaque", "unsupported_mime"),
        ("broken.pdf", b"%PDF-1.4 broken", "no_extractable"),
    ],
)
def test_expected_local_extraction_gaps_remain_reference_only(
    tmp_path: Path,
    name: str,
    raw: bytes,
    reason: str,
) -> None:
    (tmp_path / name).write_bytes(raw)

    result = _prepared(
        prepare_local_snapshot(project_key="hk", source_root=tmp_path, locator=name)
    )

    assert result.extraction_status == "reference_only"
    assert result.reason == reason
    assert result.content is None
    assert result.raw_sha256 == sha256(raw).hexdigest()
