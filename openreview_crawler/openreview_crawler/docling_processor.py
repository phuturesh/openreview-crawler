from __future__ import annotations

import logging
import mimetypes
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from docling.backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, granite_picture_description
from docling.document_converter import DocumentConverter, FormatOption
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
from docling_core.types.doc.base import ImageRefMode
from docling_core.types.doc.document import SectionHeaderItem, TextItem

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DoclingOptions:
    """Options that control Docling conversion."""

    use_granite: bool = False


class DoclingProcessor:
    """Convert PDFs into Markdown, images, and table extracts via Docling."""

    def __init__(self, options: Optional[DoclingOptions] = None) -> None:
        self.options = options or DoclingOptions()
        self._converter: Optional[DocumentConverter] = None

    def process_pdf(self, pdf_path: Path, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        try:
            document = self._convert(pdf_path)
        except Exception as exc:  # pragma: no cover - defensive, docling raises many types
            LOGGER.warning("Docling conversion failed for %s: %s", pdf_path, exc)
            return
        if document is None:
            LOGGER.warning("Docling conversion returned no document for %s", pdf_path)
            return

        figures_dir = destination / "figures"
        tables_dir = destination / "tables"
        page_images_dir = destination / "page_images"
        figures_dir.mkdir(parents=True, exist_ok=True)
        tables_dir.mkdir(parents=True, exist_ok=True)

        md_path = destination / "paper.md"
        document.save_as_markdown(
            md_path,
            artifacts_dir=Path("figures"),
            image_mode=ImageRefMode.REFERENCED,
        )

        rename_map = _renumber_prefixed_files(figures_dir, prefix="figure")
        if rename_map:
            _apply_rename_map(md_path, rename_map)

        _export_tables(document, tables_dir)
        _save_page_images(document, page_images_dir)
        _extract_references(document, destination / "references.md")
        _copy_pdf(pdf_path, destination)

    def _build_converter(self) -> DocumentConverter:
        pdf_options = PdfPipelineOptions(
            generate_picture_images=True,
            generate_table_images=True,
            generate_page_images=True,
            do_picture_description=self.options.use_granite,
            do_picture_classification=False,
            images_scale=2.0,
            do_code_enrichment=True,
            do_formula_enrichment=True,
        )
        if self.options.use_granite:
            pdf_options.picture_description_options = granite_picture_description
        format_options = {
            InputFormat.PDF: FormatOption(
                pipeline_cls=StandardPdfPipeline,
                backend=DoclingParseV4DocumentBackend,
                pipeline_options=pdf_options,
            )
        }
        return DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options=format_options,
        )

    def _convert(self, pdf_path: Path):  # type: ignore[override]
        if self._converter is None:
            self._converter = self._build_converter()
        conversion = self._converter.convert(str(pdf_path))
        status = getattr(conversion, "status", None)
        name = getattr(status, "name", "").lower()
        if name != "success":
            raise RuntimeError(f"docling conversion failed with status: {status}")
        document = getattr(conversion, "document", None)
        if document is None:
            raise RuntimeError("docling conversion did not return a document")
        return document


def _copy_pdf(pdf_path: Path, destination: Path) -> None:
    target = destination / pdf_path.name
    try:
        shutil.copy2(pdf_path, target)
    except OSError as exc:
        LOGGER.debug("Failed to copy %s to %s: %s", pdf_path, target, exc)


def _apply_rename_map(md_path: Path, rename_map: dict[str, str]) -> None:
    try:
        md_text = md_path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - filesystem race
        LOGGER.debug("Unable to read %s for rename: %s", md_path, exc)
        return
    pattern = re.compile(r"(!?\[[^\]]*\]\((?:\./)?figures/)([^)]+)(\))")

    def _replace(match: re.Match[str]) -> str:
        prefix, filename, suffix = match.groups()
        new_name = rename_map.get(filename)
        if new_name is None:
            return match.group(0)
        return f"{prefix}{new_name}{suffix}"

    md_text = pattern.sub(_replace, md_text)
    try:
        md_path.write_text(md_text, encoding="utf-8")
    except OSError as exc:  # pragma: no cover
        LOGGER.debug("Unable to write %s after rename: %s", md_path, exc)


def _renumber_prefixed_files(directory: Path, prefix: str) -> dict[str, str]:
    rename_map: dict[str, str] = {}
    for index, path in enumerate(sorted(directory.glob("image_*")), start=1):
        stem_parts = path.stem.rsplit("_", 2)
        if not stem_parts:
            continue
        new_name = f"{prefix}_{index}{path.suffix}"
        new_path = path.with_name(new_name)
        if new_path == path:
            continue
        if new_path.exists():
            new_path.unlink()
        path.rename(new_path)
        rename_map[path.name] = new_path.name
    return rename_map


def _export_tables(document, tables_dir: Path) -> None:
    for idx, table in enumerate(getattr(document, "tables", []), start=1):
        table_md = table.export_to_markdown(doc=document)
        table_path = tables_dir / f"table_{idx}.md"
        table_path.write_text(table_md, encoding="utf-8")


def _save_page_images(document, destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    image_paths: list[Path] = []
    mime_extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/tiff": ".tiff",
    }
    pages = getattr(document, "pages", {})
    if not isinstance(pages, dict):
        return image_paths
    for index, page_number in enumerate(sorted(pages.keys()), start=1):
        page = pages[page_number]
        image_ref = getattr(page, "image", None)
        if image_ref is None:
            continue
        pil_image = getattr(image_ref, "pil_image", None)
        if pil_image is None:
            continue
        mimetype = getattr(image_ref, "mimetype", None)
        suffix = mime_extension.get(mimetype)
        if not suffix:
            suffix = mimetypes.guess_extension(mimetype or "") or ".png"
        out_path = destination / f"page_{index}{suffix}"
        pil_image.save(out_path)
        image_paths.append(out_path)
    if not image_paths:
        try:
            destination.rmdir()
        except OSError:
            pass
    return image_paths


def _extract_references(document, references_path: Path) -> None:
    references: list[str] = []
    capturing = False
    for item, _ in document.iterate_items(with_groups=False):
        if isinstance(item, SectionHeaderItem):
            title = (item.text or "").strip().lower()
            if capturing and title:
                break
            if title.startswith("references"):
                capturing = True
                continue
        if capturing and isinstance(item, TextItem):
            entry = (item.text or "").strip()
            if entry:
                references.append(entry)
    if not references:
        return
    lines = [f"{idx + 1}. {ref}" for idx, ref in enumerate(references)]
    references_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "document"

