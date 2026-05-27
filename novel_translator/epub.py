from __future__ import annotations

import html
import mimetypes
import re
import uuid
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from . import settings
from .chapters import cover_path, list_chapters, safe_segment, split_chapter, translated_path
from .errors import AppError


def build_translated_epub(
    novel: str,
    output_root: Path | None = None,
    translated_root: Path | None = None,
) -> tuple[bytes, str]:
    output_root = output_root or settings.OUTPUT_ROOT
    translated_root = translated_root or settings.TRANSLATED_ROOT
    safe_novel = safe_segment(novel, "novel")
    chapters = [
        chapter
        for chapter in list_chapters(safe_novel, output_root, translated_root)
        if chapter["translated"]
    ]
    if not chapters:
        raise AppError("No translated chapters found to export.", 404)

    cover = cover_path(safe_novel, output_root)
    chapter_docs = [
        _chapter_doc(safe_novel, chapter, index, translated_root)
        for index, chapter in enumerate(chapters, start=1)
    ]
    book_id = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, safe_novel)}"

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            zipfile.ZipInfo("mimetype", (1980, 1, 1, 0, 0, 0)),
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        )
        archive.writestr("OEBPS/content.opf", _content_opf(safe_novel, book_id, chapter_docs, cover))
        archive.writestr("OEBPS/toc.ncx", _toc_ncx(safe_novel, book_id, chapter_docs))
        archive.writestr("OEBPS/nav.xhtml", _nav_xhtml(safe_novel, chapter_docs))
        archive.writestr("OEBPS/styles.css", _styles_css())
        if cover:
            archive.write(cover, f"OEBPS/images/{cover.name}")
        for doc in chapter_docs:
            archive.writestr(f"OEBPS/{doc['href']}", doc["content"])

    return buffer.getvalue(), f"{_download_stem(safe_novel)}.epub"


def _chapter_doc(
    novel: str,
    chapter: dict[str, Any],
    index: int,
    translated_root: Path,
) -> dict[str, str]:
    path = translated_path(novel, str(chapter["filename"]), translated_root)
    title, body = split_chapter(path.read_text(encoding="utf-8"))
    display_title = title or str(chapter["title"])
    href = f"chapters/chapter-{index:04d}.xhtml"
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", body) if part.strip()]
    paragraph_html = "\n".join(
        f"    <p>{html.escape(paragraph).replace(chr(10), '<br/>')}</p>" for paragraph in paragraphs
    )
    if not paragraph_html:
        paragraph_html = "    <p></p>"
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
  <title>{html.escape(display_title)}</title>
  <link rel="stylesheet" type="text/css" href="../styles.css"/>
</head>
<body>
  <section epub:type="chapter" xmlns:epub="http://www.idpf.org/2007/ops">
    <h1>{html.escape(display_title)}</h1>
{paragraph_html}
  </section>
</body>
</html>
"""
    return {"id": f"chapter-{index:04d}", "href": href, "title": display_title, "content": content}


def _content_opf(
    novel: str,
    book_id: str,
    chapter_docs: list[dict[str, str]],
    cover: Path | None,
) -> str:
    modified = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    cover_item = ""
    cover_meta = ""
    if cover:
        cover_item = (
            f'    <item id="cover-image" href="images/{html.escape(cover.name)}" '
            f'media-type="{_media_type(cover)}" properties="cover-image"/>\n'
        )
        cover_meta = '    <meta name="cover" content="cover-image"/>\n'
    chapter_items = "\n".join(
        f'    <item id="{doc["id"]}" href="{doc["href"]}" media-type="application/xhtml+xml"/>'
        for doc in chapter_docs
    )
    spine_items = "\n".join(f'    <itemref idref="{doc["id"]}"/>' for doc in chapter_docs)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="book-id" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">{html.escape(book_id)}</dc:identifier>
    <dc:title>{html.escape(novel)}</dc:title>
    <dc:language>en</dc:language>
    <meta property="dcterms:modified">{modified}</meta>
{cover_meta}  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="style" href="styles.css" media-type="text/css"/>
{cover_item}{chapter_items}
  </manifest>
  <spine toc="toc">
{spine_items}
  </spine>
</package>
"""


def _toc_ncx(novel: str, book_id: str, chapter_docs: list[dict[str, str]]) -> str:
    nav_points = "\n".join(
        f"""    <navPoint id="{doc['id']}" playOrder="{index}">
      <navLabel><text>{html.escape(doc['title'])}</text></navLabel>
      <content src="{doc['href']}"/>
    </navPoint>"""
        for index, doc in enumerate(chapter_docs, start=1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{html.escape(book_id)}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{html.escape(novel)}</text></docTitle>
  <navMap>
{nav_points}
  </navMap>
</ncx>
"""


def _nav_xhtml(novel: str, chapter_docs: list[dict[str, str]]) -> str:
    items = "\n".join(
        f'      <li><a href="{doc["href"]}">{html.escape(doc["title"])}</a></li>'
        for doc in chapter_docs
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en" lang="en">
<head>
  <title>Table of Contents</title>
  <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>{html.escape(novel)}</h1>
    <ol>
{items}
    </ol>
  </nav>
</body>
</html>
"""


def _styles_css() -> str:
    return """body {
  font-family: serif;
  line-height: 1.6;
  margin: 5%;
}
h1 {
  font-family: sans-serif;
  font-size: 1.6em;
  line-height: 1.25;
}
p {
  margin: 0 0 1em;
}
"""


def _media_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _download_stem(novel: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", novel).strip(" ._")
    return stem or "translated-novel"
