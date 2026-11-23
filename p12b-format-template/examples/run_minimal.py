"""Runnable text-only example: create a tiny DOCX, adapt it, and audit actual OOXML.

This is an EXAMPLE, not an official case or prepared result. Binary DOCX files
are created only inside a temporary directory and are deleted on exit.
"""
from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import formatfit as F  # noqa: E402

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""
RELS = """<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>"""
DOC_RELS = """<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>"""


def write_demo_docx(path: Path, margin_mm: int = 30, font: str = "Arial", size_pt: int = 10,
                    paragraphs=None, figure: bool = False, toc: bool = False,
                    page_number: bool = False) -> None:
    """Create a small, valid OOXML package for tests; no external dependency."""
    paragraphs = paragraphs or [("1 Introduction", None), ("We study it [a1].", None),
                                ("2 Methods", None), ("We use 3 mM [a2].", None)]
    twips = int(round(margin_mm * 1440 / 25.4))
    body = []
    for text, style in paragraphs:
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        body.append(f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>')
    if figure:
        body.append('<w:p><w:r><w:drawing/></w:r></w:p><w:p><w:r><w:t>Figure 1 Demo</w:t></w:r></w:p>')
    if toc:
        body.append('<w:p><w:r><w:instrText xml:space="preserve"> TOC \\o &quot;1-3&quot; </w:instrText></w:r></w:p>')
    footer_ref = '<w:footerReference w:type="default" r:id="rIdFooter"/>' if page_number else ''
    document = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{F.W}" xmlns:m="{F.M}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>{''.join(body)}
<w:sectPr>{footer_ref}<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="{twips}" w:right="{twips}" w:bottom="{twips}" w:left="{twips}" w:header="708" w:footer="708" w:gutter="0"/><w:cols w:num="1"/></w:sectPr>
</w:body></w:document>'''
    styles = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="{F.W}">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}"/><w:sz w:val="{size_pt * 2}"/></w:rPr></w:rPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}"/><w:sz w:val="{size_pt * 2}"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style></w:styles>'''
    path.parent.mkdir(parents=True, exist_ok=True)
    footer_type = '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>' if page_number else ''
    content_types = CONTENT_TYPES.replace('</Types>', footer_type + '</Types>')
    footer_rel = '<Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>' if page_number else ''
    doc_rels = DOC_RELS.replace('</Relationships>', footer_rel + '</Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        if page_number:
            z.writestr("word/footer1.xml", f'<?xml version="1.0" encoding="UTF-8"?><w:ftr xmlns:w="{F.W}"><w:p><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r></w:p></w:ftr>')


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        source = root / "source.docx"
        template = root / "template.json"
        write_demo_docx(source)
        template.write_text(json.dumps({"template": {"spec": {
            "font": "Liberation Serif", "size_pt": 11, "line_spacing": 1.5,
            "margin_mm": 25, "columns": 1, "heading_levels": 3,
            "export_format": "docx"}}}), encoding="utf-8")
        spec = {
            "case_id": "formatfit-example", "source_file": str(source),
            "template_file": str(template), "apply": True,
            "headings": [{"text": "1 Introduction", "level": 1},
                         {"text": "2 Methods", "level": 1}],
            "output_contract": {"case_id": "id", "revised_manuscript": "editable output",
                                "compliance": "item results", "unavailable_field": "unknown"},
        }
        sp = root / "spec.json"; sp.write_text(json.dumps(spec), encoding="utf-8")
        out = root / "out"
        result = F.build(F.load_spec(sp, None), out)
        print(json.dumps({"example": True, "status": result["status"],
                          "case_id": result["case_id"],
                          "applied_properties": len(result["applied_changes"]),
                          "text_identical": result["content_preservation"]["text_identical"],
                          "unavailable_field_is_null": result["unavailable_field"] is None,
                          "visual_inspection": result["rendering"]["visual_inspection"]},
                         ensure_ascii=False, indent=2))
        return 0 if result["status"] == "clean" else 1


if __name__ == "__main__":
    raise SystemExit(main())
