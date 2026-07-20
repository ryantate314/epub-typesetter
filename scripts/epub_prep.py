"""Extract an epub and prepare its content files for pandoc.

Parses the OPF directly for metadata and spine order (rather than handing
pandoc the raw .epub), and strips Project Gutenberg's standardized
boilerplate when present:

- Elements with class="pg-boilerplate ..." (their legal-notice header and
  footer divs) are removed wherever they appear in a file.
- Spine files that, after that removal, contain no real prose (no <p> with
  text, and no <p> other than ones that are themselves just a wrapped link
  to another spine file) are dropped entirely -- this catches Gutenberg's
  machine-generated "CONTENTS" link-table pages and redundant
  title-page-only files, both of which duplicate metadata/structure
  pandoc/LaTeX already generate for us.
- Footnote-marker links (`class="footnote-ref"`) nested inside a heading
  are stripped -- pandoc turns those into a hyperlink nested inside the
  heading's PDF-bookmark string, which crashes xelatex's hyperref
  sanitizer ("Undefined control sequence").
- A heading classed `bhead-chaptitle` is normalized to <h2>, even when the
  source has it as a lone <h1> (unnumbered front-matter sections like
  Foreword/Introduction lack the <h1 class="ahead-chapnum"> chapter-number
  kicker that numbered chapters pair it with) -- convert.py's
  --shift-heading-level-by=-1 expects the chapter title at <h2>, and a
  lone <h1> shifts below level 1 and gets silently demoted to a plain
  paragraph by pandoc, losing its chapter break entirely.
- A chapter-number kicker heading (`class="ahead-chapnum"`, e.g. "CHAPTER
  ONE") is folded into the following bhead-chaptitle heading's text (e.g.
  "CHAPTER ONE: TITLE") and dropped, rather than left as its own heading
  -- otherwise it degrades to a plain paragraph sitting just before the
  LaTeX \\chapter command and gets typeset as an orphaned line on the
  previous page instead of alongside its title.

This is a no-op on epubs that don't happen to share these markup
conventions: they simply won't have any matching classed elements.
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


HEADING_TAGS = {f"{{{XHTML_NS}}}h{n}" for n in range(1, 7)}


def _merge_chapter_kicker_into_title(body: ET.Element) -> None:
    # Numbered chapters carry their number as a separate heading right
    # before the title -- <h1 class="ahead-chapnum">CHAPTER ONE</h1><h2
    # class="bhead-chaptitle">TITLE</h2> -- rather than as part of the
    # title heading itself. Once shifted, the kicker's <h1> becomes a
    # plain paragraph (see _normalize_chapter_title_headings) that sits
    # just before the \chapter command, so it gets typeset as an orphaned
    # line at the bottom of the *previous* page instead of alongside the
    # title it belongs to. Fold its text into the following title heading
    # (e.g. "CHAPTER ONE: TITLE") and drop the kicker heading, so both
    # travel together as a single \chapter title.
    for parent in body.iter():
        children = list(parent)
        for i, child in enumerate(children[:-1]):
            if child.tag not in HEADING_TAGS or "ahead-chapnum" not in child.get("class", "").split():
                continue
            sibling = children[i + 1]
            if sibling.tag not in HEADING_TAGS or "bhead-chaptitle" not in sibling.get("class", "").split():
                continue
            kicker_text = "".join(child.itertext()).strip()
            if kicker_text:
                sep = " " if kicker_text.endswith(".") else ": "
                sibling.text = kicker_text + sep + (sibling.text or "")
            parent.remove(child)


def _normalize_chapter_title_headings(body: ET.Element) -> None:
    # convert.py shifts heading levels by -1 so that a chapter's <h2>
    # title becomes \chapter (--top-level-division=chapter expects
    # top-level, i.e. level-1-after-shift, headers). This epub marks the
    # actual chapter/section title with class="bhead-chaptitle" -- as an
    # <h2> when it's paired with a separate chapter-number kicker (<h1
    # class="ahead-chapnum">, e.g. "CHAPTER ONE"), but as a lone <h1> for
    # unnumbered front-matter sections (Foreword, Introduction, and other
    # section intros) that have no such kicker. A lone <h1> shifts to
    # level 0, which pandoc silently demotes to a plain paragraph instead
    # of a heading -- so those sections lose their chapter break and
    # their title, and their content runs on into whatever precedes them.
    # Normalize every bhead-chaptitle heading to <h2> so it always
    # survives the shift and becomes a \chapter.
    for heading in body.iter():
        if heading.tag in HEADING_TAGS and "bhead-chaptitle" in heading.get("class", "").split():
            heading.tag = f"{{{XHTML_NS}}}h2"


def _strip_footnote_refs_in_headings(body: ET.Element) -> None:
    # A footnote marker glued onto a heading (e.g. `<h3>Title<sup
    # class="footnote-ref"><a href="#fn-1">*</a></sup></h3>`) becomes a
    # \hyperlink/\hypertarget nested inside that heading's PDF-bookmark/TOC
    # string. hyperref's bookmark sanitizer can't expand nested hyperlinks
    # there and xelatex dies with "Undefined control sequence". Elsewhere
    # in the body footnote-ref markers are harmless, so only strip them
    # when they appear inside a heading.
    for heading in body.iter():
        if heading.tag not in HEADING_TAGS:
            continue
        while True:
            removed = False
            for parent in heading.iter():
                for child in list(parent):
                    if "footnote-ref" in child.get("class", "").split():
                        parent.remove(child)
                        removed = True
                        break
                if removed:
                    break
            if not removed:
                break


def _is_nav_link_paragraph(p: ET.Element) -> bool:
    # True for a paragraph that's nothing but a wrapped link to another
    # spine file, e.g. `<p class="toc1"><a href="chap2.xhtml"><b>Chapter
    # Two</b></a></p>` -- a table-of-contents entry, not real prose. Only
    # matches a <p> whose sole child is an <a> with no text/tail outside
    # it; a paragraph mixing free text and a link (e.g. "Website: <a>...")
    # still counts as prose.
    children = list(p)
    if (p.text and p.text.strip()) or len(children) != 1:
        return False
    a = children[0]
    return a.tag == f"{{{XHTML_NS}}}a" and not (a.tail and a.tail.strip())


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
    _strip_footnote_refs_in_headings(body)
    _merge_chapter_kicker_into_title(body)
    _normalize_chapter_title_headings(body)

    paragraphs = body.findall(f".//{{{XHTML_NS}}}p")
    has_prose = any(
        not _is_nav_link_paragraph(p) and ((p.text and p.text.strip()) or len(list(p)))
        for p in paragraphs
    )
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
