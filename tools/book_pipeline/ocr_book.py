"""OCR scanned investment books into reusable page text.

The script keeps outputs simple on purpose:
- one JSON file per page for resumable OCR
- one combined Markdown file for reading and downstream summarization
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz
from PIL import Image
from rapidocr_onnxruntime import RapidOCR


@dataclass(frozen=True)
class OcrLine:
    text: str
    score: float
    box: list


def parse_pages(value: str | None, page_count: int) -> list[int]:
    if not value:
        return list(range(page_count))

    pages: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            pages.update(range(start - 1, end))
        else:
            pages.add(int(part) - 1)

    invalid = [page + 1 for page in pages if page < 0 or page >= page_count]
    if invalid:
        raise ValueError(f"Page numbers out of range: {invalid}")
    return sorted(pages)


def clean_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("／／", "//")
    return text


def sort_lines(result: Iterable) -> list[OcrLine]:
    lines: list[OcrLine] = []
    for item in result or []:
        box, text, score = item
        cleaned = clean_text(str(text))
        if cleaned:
            lines.append(OcrLine(text=cleaned, score=float(score), box=box))

    def key(line: OcrLine) -> tuple[float, float]:
        xs = [point[0] for point in line.box]
        ys = [point[1] for point in line.box]
        return (min(ys), min(xs))

    return sorted(lines, key=key)


def page_to_image(page: fitz.Page, zoom: float, output_path: Path) -> Path:
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    pix.save(output_path)
    return output_path


def page_json_path(pages_dir: Path, page_number: int) -> Path:
    return pages_dir / f"page_{page_number:04d}.json"


def ocr_page(
    engine: RapidOCR,
    doc: fitz.Document,
    page_index: int,
    pages_dir: Path,
    images_dir: Path,
    zoom: float,
    keep_images: bool,
) -> dict:
    page_number = page_index + 1
    json_path = page_json_path(pages_dir, page_number)
    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8"))

    image_path = images_dir / f"page_{page_number:04d}.png"
    page_to_image(doc[page_index], zoom, image_path)
    image = Image.open(image_path)
    result, elapsed = engine(image)
    lines = sort_lines(result)

    avg_score = (
        round(sum(line.score for line in lines) / len(lines), 4)
        if lines
        else 0
    )
    payload = {
        "page": page_number,
        "text": "\n".join(line.text for line in lines),
        "line_count": len(lines),
        "avg_score": avg_score,
        "elapsed": elapsed,
        "lines": [
            {"text": line.text, "score": round(line.score, 4), "box": line.box}
            for line in lines
        ],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not keep_images:
        image_path.unlink(missing_ok=True)
    return payload


def write_combined_markdown(
    output_path: Path,
    book_title: str,
    page_payloads: list[dict],
) -> None:
    parts = [f"# {book_title}", ""]
    for payload in page_payloads:
        parts.append(f"## Page {payload['page']}")
        parts.append("")
        parts.append(payload.get("text", ""))
        parts.append("")
    output_path.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCR a scanned PDF book into page JSON and Markdown."
    )
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--title", default=None)
    parser.add_argument("--out-dir", type=Path, default=Path("library/ocr"))
    parser.add_argument("--pages", default=None, help="1-based pages, e.g. 1,3,10-20")
    parser.add_argument("--zoom", type=float, default=2.0)
    parser.add_argument("--keep-images", action="store_true")
    args = parser.parse_args()

    pdf_path = args.pdf.expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    title = args.title or pdf_path.stem
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", title).strip("_")
    book_dir = args.out_dir / slug
    pages_dir = book_dir / "pages"
    images_dir = book_dir / "images"
    pages_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    selected_pages = parse_pages(args.pages, len(doc))
    engine = RapidOCR()

    payloads: list[dict] = []
    for page_index in selected_pages:
        payload = ocr_page(
            engine=engine,
            doc=doc,
            page_index=page_index,
            pages_dir=pages_dir,
            images_dir=images_dir,
            zoom=args.zoom,
            keep_images=args.keep_images,
        )
        payloads.append(payload)
        print(
            f"page {payload['page']}/{len(doc)}: "
            f"{payload['line_count']} lines, avg_score={payload['avg_score']}"
        )

    markdown_path = book_dir / f"{slug}.md"
    write_combined_markdown(markdown_path, title, payloads)
    print(f"wrote {markdown_path}")


if __name__ == "__main__":
    main()
