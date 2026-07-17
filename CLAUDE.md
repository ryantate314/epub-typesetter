# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Converts epubs into typeset PDFs at 5.5×8.5in trim size — half of a US
Letter sheet — meant to be printed on letter paper and folded/bound into a
small book (a "folded folio"). Built with pandoc, Python, and LaTeX
(XeLaTeX + KOMA-Script). No pip packages are used — `scripts/` is stdlib
Python only.

**Status:** the epub → trim-size-PDF pipeline works end to end (tested on
*Frankenstein*, Project Gutenberg #84). Booklet imposition — arranging
trim-size pages 2-up onto letter sheets in the correct folded page order —
is not built yet; that's the next milestone.

## Commands

Convert an epub (expects `books/<slug>/source.epub` to already exist):

```
python3 scripts/convert.py <slug>
python3 scripts/convert.py <slug> --dropcaps   # opt-in chapter drop caps, see Known bugs below
```

Output lands at `books/<slug>/build/book.pdf`. `build/` is fully regenerated
(deleted and recreated) on every run — never hand-edit files under it.

There is no test suite, linter, or build step beyond this script; verifying
a change means running `convert.py` against `books/frankenstein` (already
present as the reference test case) and visually inspecting the resulting
PDF, e.g.:

```
pdftoppm -png -r 150 -f <page> -l <page> books/frankenstein/build/book.pdf /tmp/out
```

`books/` is gitignored (epubs and generated PDFs are large binaries) except
for a tracked `.gitkeep`, so test epubs placed there won't accidentally get
committed.

## Architecture

The pipeline is intentionally two-stage and inspectable, not a single
pandoc invocation straight to PDF:

1. **`scripts/epub_prep.py`** unzips the epub and parses `content.opf`
   directly (stdlib `xml.etree.ElementTree`, no epub/HTML libraries) to get
   metadata and the spine (ordered list of HTML files). It then cleans each
   spine file in place before pandoc ever sees it:
   - Strips elements with `class="pg-boilerplate ..."` — Project
     Gutenberg's `ebookmaker` tool embeds its legal-notice header/footer as
     literal body content, not just metadata, in every epub it produces.
   - Strips each file's own `<title>` tag — pandoc extracts a `title`
     metadata field per input HTML file, and when combining multiple files
     the *last* file's title silently wins over `--metadata-file`. Since
     title/author are set explicitly (see below), no per-file `<title>`
     should survive into the mix.
   - Drops a spine file entirely if, after boilerplate removal, it has no
     `<p>` tags with real text — this catches Gutenberg's machine-generated
     "CONTENTS" link-table page and a redundant title-page file, both of
     which duplicate what `\maketitle`/`\tableofcontents` already produce.
   - This is Gutenberg-specific but a no-op (safe) on any other epub, since
     those markers simply won't be present.

2. **`scripts/convert.py`** takes the *cleaned* spine files (not the
   original `.epub`) and:
   - Runs `pandoc` with `--shift-heading-level-by=-1 --top-level-division=chapter`
     — epub chapter titles are usually `<h2>` (with `<h1>` reserved for the
     book title, which gets stripped as boilerplate). `--top-level-division`
     only remaps *level-1* headers, so without the shift, `<h2>` becomes
     `\section` instead of `\chapter` — which also silently breaks the
     running headers, since KOMA's `\automark{chapter}` only fires on
     `\chapter` calls.
   - Passes `-M babel-lang=` unconditionally. This works around a package
     conflict where KOMA's own English string translations collide with
     `babel`'s (`\englishdate already defined`) whenever `lang` metadata is
     set. Blanking just `babel-lang` skips the conflicting part of pandoc's
     template while keeping `\otherlanguage` support, which some epub
     content needs (inline `lang="en"` spans).
   - Writes/uses `books/<slug>/metadata.yaml` for title/author/lang. If that
     file exists next to `source.epub`, it's used as-is (hand-editable
     override for garbled dates/odd casing from the source); otherwise it's
     generated from the OPF.
   - Runs `xelatex` twice (second pass resolves TOC/cross-references), with
     `TEXINPUTS` pointed at `template/` so `\documentclass{halfletter-book}`
     resolves without installing anything into the system TeX tree.

3. **`template/halfletter-book.cls`** is the actual book design, built on
   KOMA-Script's `scrbook` rather than from scratch (chapter styling, TOC,
   front-matter conventions come for free). Notable non-obvious bit:
   headers use `\automark[chapter]{chapter}` — the *bracketed* argument
   form. Plain `\automark{chapter}` (single argument) tells KOMA "this is
   the low-level mark, something else will fill the high-level/right-hand
   mark," and leaves the right-hand mark permanently blank when nothing
   else does (this book has only one heading level, no sections). The
   bracketed form `[chapter]{chapter}` mirrors the same chapter title to
   both sides.

4. **`template/dropcap.lua`** (opt-in via `--dropcaps`, off by default) is a
   pandoc Lua filter adding `\lettrine` drop caps to chapter-opening
   paragraphs. Two non-obvious things if touching it:
   - It hooks `Blocks`, not the top-level-only `Pandoc` function — epub
     chapter content is often nested inside a `<div class="chapter">`
     wrapper, so a top-level-only filter would never see the Header/Para
     pair.
   - It uses `pandoc.text.sub`/`pandoc.text.len` (UTF-8 codepoint aware),
     not Lua's built-in `string.sub` (byte-based) — the first character of
     a paragraph is often a multi-byte curly quote, and byte-slicing
     corrupts it.

## Known bugs

- `--dropcaps`: when a chapter opens with a quotation mark, the filter
  peels the quote off to keep it normal-sized in front of the drop cap, but
  it currently renders on its own orphaned line above the paragraph instead
  of staying inline. Root cause not yet found — suspect `lettrine` requires
  being the first thing in its paragraph. This is why drop caps default to
  off.
- Illustrated Gutenberg editions (e.g. the "images" edition of *Pride and
  Prejudice*) bury a caption and an image inside the `<h2>` chapter-heading
  markup itself, not just prose after it. `epub_prep.py` does not handle
  this yet — pick a cleanly-transcribed edition instead when adding new
  test books, or expect to extend the cleanup logic.
