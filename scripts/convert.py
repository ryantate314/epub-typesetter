#!/usr/bin/env python3
"""Convert an epub into a trim-size (5.5x8.5in) LaTeX/PDF book.

Usage:
    python3 scripts/convert.py <book-slug>

Expects books/<book-slug>/source.epub to exist. Writes book.tex and
book.pdf into books/<book-slug>/build/.

Optionally, books/<book-slug>/metadata.yaml can override the title/author/
lang pandoc metadata extracted from the epub's OPF (useful for fixing
odd casing, garbled dates, etc. from the source file).
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

import epub_prep

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "template"


def run(cmd, cwd, env=None):
    print(f"$ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout[-4000:])
        print(result.stderr[-4000:])
        raise SystemExit(f"Command failed with exit code {result.returncode}")
    return result


def build_metadata_yaml(metadata: dict, build_dir: Path, override_path: Path) -> Path:
    if override_path.exists():
        return override_path

    def esc(s):
        return s.replace('"', '\\"')

    lines = [f'title: "{esc(metadata["title"])}"']
    if metadata["authors"]:
        lines.append("author:")
        for author in metadata["authors"]:
            lines.append(f'  - "{esc(author)}"')
    if metadata["language"]:
        lines.append(f'lang: {metadata["language"]}')

    yaml_path = build_dir / "metadata.yaml"
    yaml_path.write_text("\n".join(lines) + "\n")
    return yaml_path


def convert_to_tex(
    spine_files, opf_dir: Path, metadata_yaml: Path, build_dir: Path, dropcaps: bool = False
) -> Path:
    tex_path = build_dir / "book.tex"
    cmd = [
        "pandoc",
        *[str(p.resolve()) for p in spine_files],
        "-o",
        "book.tex",
        "--standalone",
        f"--resource-path={opf_dir.resolve()}",
        "--extract-media=media",
        "--shift-heading-level-by=-1",
        "--top-level-division=chapter",
        "--toc",
        f"--metadata-file={metadata_yaml.resolve()}",
        "-V",
        "documentclass=halfletter-book",
        "-V",
        "has-frontmatter=true",
        "-V",
        "has-chapters=true",
        "-M",
        "babel-lang=",
    ]
    if dropcaps:
        cmd.append(f"--lua-filter={(TEMPLATE_DIR / 'dropcap.lua').resolve()}")
    run(cmd, cwd=build_dir)
    return tex_path


def compile_tex_to_pdf(tex_path: Path, build_dir: Path) -> Path:
    env = os.environ.copy()
    env["TEXINPUTS"] = f"{TEMPLATE_DIR.resolve()}//:{env.get('TEXINPUTS', '')}"

    for pass_num in (1, 2):
        print(f"--- xelatex pass {pass_num} ---")
        run(
            [
                "xelatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                tex_path.name,
            ],
            cwd=build_dir,
            env=env,
        )
    return build_dir / (tex_path.stem + ".pdf")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="Book directory name under books/")
    parser.add_argument(
        "--dropcaps",
        action="store_true",
        default=False,
        help="Add lettrine drop caps to chapter-opening paragraphs (default: off)",
    )
    args = parser.parse_args()

    book_dir = REPO_ROOT / "books" / args.slug
    source_epub = book_dir / "source.epub"
    if not source_epub.exists():
        raise SystemExit(f"No source.epub found at {source_epub}")

    build_dir = book_dir / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)

    metadata, spine_files, opf_dir = epub_prep.prepare(source_epub, build_dir / "extracted")
    print(f"Kept {len(spine_files)} spine files after Gutenberg boilerplate cleanup")

    metadata_yaml = build_metadata_yaml(metadata, build_dir, book_dir / "metadata.yaml")
    tex_path = convert_to_tex(spine_files, opf_dir, metadata_yaml, build_dir, dropcaps=args.dropcaps)
    pdf_path = compile_tex_to_pdf(tex_path, build_dir)

    print(f"\nDone: {pdf_path}")


if __name__ == "__main__":
    main()
