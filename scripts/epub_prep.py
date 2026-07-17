"""Extract an epub and prepare its content files for pandoc.

Parses the OPF directly for metadata and spine order (rather than handing
pandoc the raw .epub), and strips Project Gutenberg's standardized
boilerplate when present:

- Elements with class="pg-boilerplate ..." (their legal-notice header and
  footer divs) are removed wherever they appear in a file.
- Spine files that, after that removal, contain no real prose (no <p> with
  text) are dropped entirely -- this catches Gutenberg's machine-generated
  "CONTENTS" link-table pages and redundant title-page-only files, both of
  which duplicate metadata/structure pandoc/LaTeX already generate for us.

This is a no-op on non-Gutenberg epubs: they simply won't have any
pg-boilerplate-classed elements or contentless spine files.
"""

import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF_NS = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
XHTML_NS = "http://www.w3.org/1999/xhtml"


def extract_epub(epub_path: Path, dest_dir: Path) -> Path:
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True)
    with zipfile.ZipFile(epub_path) as zf:
        zf.extractall(dest_dir)
    return dest_dir


def _find_opf_path(extracted_dir: Path) -> Path:
    container = ET.parse(extracted_dir / "META-INF" / "container.xml")
    rootfile = container.find(f".//{{{CONTAINER_NS}}}rootfile")
    return extracted_dir / rootfile.get("full-path")


def parse_book(extracted_dir: Path):
    """Returns (metadata dict, list of absolute spine file paths in order)."""
    opf_path = _find_opf_path(extracted_dir)
    opf_dir = opf_path.parent
    root = ET.parse(opf_path).getroot()

    metadata_el = root.find("opf:metadata", OPF_NS)
    title = metadata_el.findtext("dc:title", default="", namespaces=OPF_NS)
    authors = [e.text for e in metadata_el.findall("dc:creator", OPF_NS) if e.text]
    language = metadata_el.findtext("dc:language", default="", namespaces=OPF_NS)

    manifest = {
        item.get("id"): item.get("href")
        for item in root.find("opf:manifest", OPF_NS)
    }
    spine_els = root.find("opf:spine", OPF_NS)
    spine_paths = [
        opf_dir / manifest[itemref.get("idref")]
        for itemref in spine_els
        if itemref.get("idref") in manifest
    ]

    metadata = {"title": title, "authors": authors, "language": language}
    return metadata, spine_paths, opf_dir


def _strip_boilerplate_divs(body: ET.Element) -> None:
    while True:
        removed = False
        for parent in body.iter():
            for child in list(parent):
                if "pg-boilerplate" in child.get("class", "").split():
                    parent.remove(child)
                    removed = True
                    break
            if removed:
                break
        if not removed:
            break


def _strip_head_title(root: ET.Element) -> None:
    # Each spine file's own <title> would otherwise leak into pandoc's
    # combined document metadata (the last file's title wins), clobbering
    # our real book title -- we set title/author ourselves, so drop these.
    head = root.find(f"{{{XHTML_NS}}}head")
    if head is None:
        return
    title_el = head.find(f"{{{XHTML_NS}}}title")
    if title_el is not None:
        head.remove(title_el)


def clean_spine_file(html_path: Path) -> bool:
    """Cleans a spine file in place. Returns True if the file should be
    dropped from the book entirely (no real prose content remains)."""
    tree = ET.parse(html_path)
    root = tree.getroot()
    _strip_head_title(root)
    body = root.find(f".//{{{XHTML_NS}}}body")
    if body is None:
        tree.write(html_path, encoding="utf-8", xml_declaration=True)
        return False

    _strip_boilerplate_divs(body)

    paragraphs = body.findall(f".//{{{XHTML_NS}}}p")
    has_prose = any((p.text and p.text.strip()) or len(list(p)) for p in paragraphs)
    if not has_prose:
        return True

    tree.write(html_path, encoding="utf-8", xml_declaration=True)
    return False


def prepare(epub_path: Path, work_dir: Path):
    """Extracts and cleans an epub. Returns (metadata, ordered list of
    kept spine file paths, opf directory) ready to hand to pandoc."""
    extracted = extract_epub(epub_path, work_dir)
    metadata, spine_paths, opf_dir = parse_book(extracted)

    kept = []
    for path in spine_paths:
        if not path.exists():
            continue
        drop = clean_spine_file(path)
        if not drop:
            kept.append(path)

    return metadata, kept, opf_dir
