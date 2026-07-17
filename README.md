# typesetting

Converts epubs into typeset PDFs at 5.5×8.5in trim size — half of a US Letter
sheet — meant to be printed on letter paper and folded/bound into a small
book (a "folded folio"). Built with pandoc, Python, and LaTeX (XeLaTeX +
KOMA-Script).

**Status:** the epub-to-trim-size-PDF pipeline works end to end (tested on
*Frankenstein*, Project Gutenberg #84). The booklet imposition step —
arranging trim-size pages 2-up onto letter sheets in the correct folded
order — is not built yet.

## Requirements

- `pandoc` (3.x)
- `xelatex` (from TeX Live: `texlive-latex-base texlive-xetex
  texlive-fonts-recommended texlive-latex-extra texlive-latex-recommended`)
- `python3` (stdlib only — no pip packages required)

## Repo layout

```
books/<slug>/source.epub    epub source (gitignored — books/ isn't versioned)
books/<slug>/metadata.yaml  optional: hand-written title/author/lang override
books/<slug>/build/         generated output (gitignored)
  extracted/                 unzipped + cleaned epub contents
  media/                     images pandoc extracted for the PDF
  book.tex                   generated LaTeX
  book.pdf                   final trim-size PDF

template/halfletter-book.cls  the book's LaTeX class (page size, fonts, headers)
template/dropcap.lua          pandoc Lua filter: adds chapter drop caps

scripts/convert.py   orchestrates the whole pipeline
scripts/epub_prep.py  epub extraction + Gutenberg boilerplate cleanup
```

## Usage

Drop a book in and run the converter:

```
mkdir -p books/my-book
cp somewhere/my-book.epub books/my-book/source.epub
python3 scripts/convert.py my-book
```

Output: `books/my-book/build/book.pdf`.

If the epub's metadata is wrong or ugly (Gutenberg titles are sometimes odd
casing, or have garbled dates), write `books/my-book/metadata.yaml` by hand,
e.g.:

```yaml
title: "Frankenstein; or, The Modern Prometheus"
author:
  - "Mary Wollstonecraft Shelley"
lang: en
```

If that file exists, it's used as-is instead of the auto-extracted metadata.

Drop caps on chapter-opening paragraphs are off by default (see the known
limitation below). Turn them on with `--dropcaps`:

```
python3 scripts/convert.py my-book --dropcaps
```

## How it works

### 1. `epub_prep.py` — extract and clean

Rather than handing pandoc the raw `.epub` (pandoc has its own epub reader,
but we ran into metadata bugs relying on it — see below), `convert.py`:

1. Unzips the epub.
2. Parses `content.opf` directly (via stdlib `xml.etree.ElementTree`) to get
   the title, authors, language, and the spine — the ordered list of HTML
   files that make up the book.
3. Cleans each spine file:
   - Strips any element with `class="pg-boilerplate ..."`. This is Project
     Gutenberg's standardized marker for their legal-notice header/footer
     divs, which their `ebookmaker` tool embeds as literal body content in
     every epub they produce, not just as metadata.
   - Drops the `<title>` tag from each file's `<head>`. (Pandoc extracts a
     `title` metadata field per input file when given multiple HTML files;
     combining them, the *last* file's title silently wins over anything we
     pass via `--metadata-file`. Since we set title/author ourselves, we
     don't want per-file `<title>` tags in the mix at all.)
   - Drops any spine file entirely if, after boilerplate removal, it has no
     `<p>` tags with real text. This catches Gutenberg's machine-generated
     "CONTENTS" link-table page and a redundant title-page file — both
     duplicate what our own `\maketitle`/`\tableofcontents` already produce.

This is Gutenberg-specific but safe on any other epub: none of these
markers will be present, so nothing gets stripped.

### 2. `convert.py` — pandoc → LaTeX → PDF

- Runs `pandoc` on the cleaned spine files (not the original epub), with:
  - `--shift-heading-level-by=-1` + `--top-level-division=chapter`: epub
    chapter titles are usually `<h2>` (with `<h1>` reserved for the book
    title, which we've stripped as boilerplate/duplicate). Pandoc's
    `--top-level-division` only remaps *level-1* headers, so without the
    shift, `<h2>` headings become `\section` instead of `\chapter` — which
    also silently breaks the running headers (see below).
  - `--extract-media=media` + `--resource-path=<original OEBPS dir>`: so
    images referenced by the (now-relocated) HTML files still resolve.
  - `--lua-filter=template/dropcap.lua`, only when `--dropcaps` is passed
    (see below; off by default).
  - `--metadata-file=...`: title/author/lang, either auto-generated from the
    OPF or the hand-written override.
  - `-M babel-lang=`: works around a package conflict where KOMA-Script's
    own English string translations collide with `babel`'s
    (`\englishdate already defined`) when `lang` is set. Blanking
    `babel-lang` skips just the conflicting part of pandoc's template while
    keeping `\otherlanguage` support (some epub content has inline
    `lang="en"` spans that need it).
- Runs `xelatex` twice (second pass resolves the table of contents and
  cross-references) with `TEXINPUTS` pointed at `template/` so
  `\documentclass{halfletter-book}` resolves.

### 3. `template/halfletter-book.cls` — the book design

Built on KOMA-Script's `scrbook` rather than from scratch, so chapter
styling/TOC/front-matter conventions come for free:

- **Page size**: 5.5×8.5in trim, via the `geometry` package. Inner margin
  0.8in (room for the fold), outer margin 0.55in, page numbers live on the
  outer edge (easiest to find while flipping through a folded booklet).
- **Fonts**: TeX Gyre Pagella (a free Palatino clone) via `fontspec`
  (requires XeLaTeX/LuaLaTeX), plus `microtype` for better justification.
  Title page font overridden from KOMA's default sans-bold to match the
  serif body text.
- **Chapter opening headers**: `scrlayer-scrpage`, with
  `\automark[chapter]{chapter}` — note the *bracketed* argument. A plain
  `\automark{chapter}` (single argument) tells KOMA "this is the low-level
  mark, expect something else to fill the high-level/right-hand mark" and
  leaves the right-hand mark blank forever when nothing else does. With
  `[chapter]{chapter}` both sides mirror the same chapter title, which is
  what you want when chapters are the only heading level in the book.
- **Drop caps**: `lettrine`, 2-line default.

### 4. `template/dropcap.lua` — chapter drop caps (opt-in, `--dropcaps`)

Adds a `\lettrine{X}{yz}` around the first word of the first paragraph
after each chapter heading, for a traditional printed-book look. Off by
default — see known limitations below.

- Uses pandoc's `Blocks` filter hook (not the top-level-only `Pandoc` hook),
  because epub chapter content is often nested inside a
  `<div class="chapter">` wrapper — a top-level-only filter would never see
  the Header/Para pair at all.
- Uses `pandoc.text.sub`/`pandoc.text.len` (UTF-8 codepoint aware), not
  Lua's built-in `string.sub` (byte-based) — the first character of a
  paragraph is often a multi-byte curly quote, and byte-slicing it corrupts
  it.
- Peels off leading quotation marks/dashes before picking the drop-cap
  letter, keeping them as normal-sized text in front of the cap, so a
  chapter opening with dialogue doesn't drop-cap the quote mark itself.
- Skips (safely, silently) any paragraph that doesn't start with a plain
  word at all — e.g. one opening in italics (common for epistolary
  chapters, like the "Letter" sections of *Frankenstein*). This is a
  deliberate limitation: better to skip a drop cap than guess wrong.

## Known limitations / not yet handled

- **Imposition isn't built yet.** The output PDF is trim-size pages in
  reading order — not yet arranged 2-up on letter sheets in the folded
  booklet page order. That's the next step.
- **Gutenberg-specific cleanup** in `epub_prep.py` only knows about the
  `pg-boilerplate` class and the no-`<p>`-tags heuristic. A non-Gutenberg
  epub with its own front-matter cruft (different publisher boilerplate,
  etc.) would need its own handling if it comes up.
- **Drop caps are off by default (`--dropcaps` to enable) and still have a
  known bug**: when a chapter opens with a quotation mark, the peeled-off
  quote character renders on its own orphaned line above the paragraph
  instead of staying inline before the drop cap. Root cause not yet found —
  suspect `lettrine` requires being the first thing in its paragraph, and
  the preceding `pandoc.Str` for the quote mark is upsetting that. Needs
  more investigation before turning this back on by default.
- Illustrated Gutenberg editions with captions/images baked into the
  chapter heading markup (as seen in the "images" edition of *Pride and
  Prejudice*) aren't handled at all yet — that epub was set aside as a
  harder follow-on case.
- **Title page** is KOMA's plain default `\maketitle` layout (title, author,
  centered, lots of whitespace on a small trim size) — not yet customized.
