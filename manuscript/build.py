"""Build the JEET submission: anonymized manuscript (.docx) and separate title page (.docx).

Steps: resolve [#key] citations in order of first appearance -> numbered [n] with ranges;
append the APA 7 reference list; pandoc -> docx (native Word equations, decimal headings);
post-process: 10-pt Times New Roman, table borders, bold caption labels, page numbers, NO line numbers.
"""
import os, re, subprocess
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from references import REFS

HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
FONT = "Times New Roman"; SIZE = 10


def resolve_citations(md):
    order = []
    for m in re.finditer(r"\[(#[a-z0-9]+(?:\s*,\s*#[a-z0-9]+)*)\]", md):
        for k in re.findall(r"#([a-z0-9]+)", m.group(1)):
            if k not in order:
                order.append(k)
    num = {k: i + 1 for i, k in enumerate(order)}
    missing = [k for k in order if k not in REFS]
    assert not missing, missing

    def fmt(m):
        ns = sorted(num[k] for k in re.findall(r"#([a-z0-9]+)", m.group(1)))
        parts, i = [], 0
        while i < len(ns):
            j = i
            while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
                j += 1
            parts.append(f"{ns[i]}–{ns[j]}" if j - i >= 2 else ", ".join(str(x) for x in ns[i:j + 1]))
            i = j + 1
        return "[" + ", ".join(parts) + "]"
    md = re.sub(r"\[(#[a-z0-9]+(?:\s*,\s*#[a-z0-9]+)*)\]", fmt, md)
    reflist = "\n".join(f"{num[k]}. {REFS[k]}" for k in order)
    unused = [k for k in REFS if k not in num]
    return md.replace("[[REFERENCES]]", reflist), order, unused


def reference_doc(path):
    with open("ref_tmp.docx", "wb") as fh:
        fh.write(subprocess.run(["pandoc", "--print-default-data-file", "reference.docx"], check=True,
                                capture_output=True).stdout)
    ref = Document("ref_tmp.docx")
    get = lambda n: next((x for x in ref.styles if x.name == n), None)
    for st in ref.styles:
        try:
            if st.type in (WD_STYLE_TYPE.PARAGRAPH, WD_STYLE_TYPE.CHARACTER):
                st.font.name = FONT; st.font.color.rgb = RGBColor(0, 0, 0)
                rpr = st.element.get_or_add_rPr(); rf = rpr.find(qn("w:rFonts"))
                if rf is None:
                    rf = OxmlElement("w:rFonts"); rpr.append(rf)
                for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                    rf.set(qn(a), FONT)
                for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
                    if rf.get(qn(a)) is not None: del rf.attrib[qn(a)]
        except Exception:
            pass
    def style(n, size, bold=None, italic=None, align=None, before=None, after=None, spacing=None):
        s = get(n)
        if s is None: return
        s.font.size = Pt(size)
        if bold is not None: s.font.bold = bold
        if italic is not None: s.font.italic = italic
        pf = s.paragraph_format
        if align is not None: pf.alignment = align
        if before is not None: pf.space_before = Pt(before)
        if after is not None: pf.space_after = Pt(after)
        if spacing is not None: pf.line_spacing = spacing
    for n in ["Normal", "Body Text", "First Paragraph", "Compact"]:
        style(n, SIZE, spacing=1.5, after=4, before=0, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    style("Title", 14, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=12, before=0, spacing=1.15)
    style("Heading 1", 11, bold=True, italic=False, before=14, after=6, spacing=1.15)
    style("Heading 2", 10, bold=True, italic=False, before=10, after=4, spacing=1.15)
    style("Heading 3", 10, bold=False, italic=True, before=8, after=4, spacing=1.15)
    for n in ["Table Caption", "Image Caption", "Caption"]:
        style(n, 9, italic=False, align=WD_ALIGN_PARAGRAPH.LEFT, spacing=1.15, after=6, before=4)
    sec = ref.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.5); sec.top_margin = sec.bottom_margin = Cm(2.5)
    ref.save(path); os.remove("ref_tmp.docx")


def page_numbers(doc):
    for s in doc.sections:
        for ln in s._sectPr.findall(qn("w:lnNumType")):      # make sure there are NO line numbers
            s._sectPr.remove(ln)
        p = s.footer.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(); r.font.size = Pt(9); r.font.name = FONT
        for tag, txt in [("begin", None), (None, "PAGE"), ("end", None)]:
            if tag:
                f = OxmlElement("w:fldChar"); f.set(qn("w:fldCharType"), tag); r._r.append(f)
            else:
                it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = txt; r._r.append(it)


def tables(doc):
    for t in doc.tables:
        tblPr = t._tbl.tblPr
        b = OxmlElement("w:tblBorders")
        for edge in ["top", "left", "bottom", "right", "insideH", "insideV"]:
            e = OxmlElement(f"w:{edge}"); e.set(qn("w:val"), "single"); e.set(qn("w:sz"), "4"); e.set(qn("w:color"), "000000")
            b.append(e)
        tblPr.append(b)
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.line_spacing = 1.0; p.paragraph_format.space_after = Pt(1)
                    p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    for r in p.runs: r.font.size = Pt(8.5)
        if len(t.columns) > 1:
            for cell in t.rows[0].cells:
                for p in cell.paragraphs:
                    for r in p.runs: r.font.bold = True


def images(doc, width_cm=17.4):
    for shp in doc.inline_shapes:
        ratio = shp.height / shp.width
        shp.width = Cm(width_cm); shp.height = int(Cm(width_cm) * ratio)


def build_manuscript():
    md = open("manuscript.md", encoding="utf-8").read()
    md, order, unused = resolve_citations(md)
    open("manuscript_resolved.md", "w", encoding="utf-8").write(md)
    reference_doc("ref_jeet.docx")
    subprocess.run(["pandoc", "manuscript_resolved.md", "-o", "Manuscript_anonymized.docx", "--number-sections",
                    "--reference-doc=ref_jeet.docx", "--resource-path=."], check=True)
    doc = Document("Manuscript_anonymized.docx")
    tables(doc); images(doc); page_numbers(doc)
    doc.save("Manuscript_anonymized.docx")
    print("references cited:", len(order), "| unused:", unused)


def build_title_page():
    subprocess.run(["pandoc", "title_page.md", "-o", "Title_Page.docx", "--reference-doc=ref_jeet.docx"], check=True)
    doc = Document("Title_Page.docx"); tables(doc); page_numbers(doc); doc.save("Title_Page.docx")


AUTHORS_BLOCK = """
::: {custom-style="Author"}
Arul Dalton G^1,\\*^ · Marisargunam S^2^
:::

::: {custom-style="Affiliation"}
^1^ Department of Computer Science and Engineering, Saveetha Engineering College, Chennai, Tamil Nadu, India (ORCID 0000-0002-5981-7176)

^2^ Department of Electrical and Electronics Engineering, Saveetha Engineering College, Chennai, Tamil Nadu, India (ORCID 0009-0008-5157-2048; marisargunams@saveetha.ac.in)

\\*Correspondence: Arul Dalton G (aruldalton@saveetha.ac.in)
:::

"""


def build_full_paper():
    """Single, non-anonymized Word file: authors + manuscript + full declarations from the title page."""
    ms = open("manuscript_resolved.md", encoding="utf-8").read()
    tp = open("title_page.md", encoding="utf-8").read()
    front, body = ms.split("# Abstract {.unnumbered}", 1)
    decl = tp.split("# Declarations {.unnumbered}", 1)[1]
    ack = tp.split("# Acknowledgments {.unnumbered}", 1)[1].split("# Declarations", 1)[0]
    pre, post = body.split("# Statements and Declarations {.unnumbered}", 1)
    refs = post.split("# References {.unnumbered}", 1)[1]
    full = (front + AUTHORS_BLOCK + "# Abstract {.unnumbered}" + pre + "# Acknowledgments {.unnumbered}\n" + ack +
            "# Statements and Declarations {.unnumbered}\n" + decl + "\n# References {.unnumbered}" + refs)
    open("full_paper.md", "w", encoding="utf-8").write(full)
    subprocess.run(["pandoc", "full_paper.md", "-o", "Research_Paper_Complete.docx", "--number-sections",
                    "--reference-doc=ref_jeet.docx", "--resource-path=."], check=True)
    doc = Document("Research_Paper_Complete.docx"); tables(doc); images(doc); page_numbers(doc)
    doc.save("Research_Paper_Complete.docx")


def build_cover_letter():
    """Cover letter to the Editor-in-Chief (Word)."""
    subprocess.run(["pandoc", "cover_letter.md", "-o", "Cover_Letter.docx", "--reference-doc=ref_jeet.docx"], check=True)
    doc = Document("Cover_Letter.docx"); page_numbers(doc); doc.save("Cover_Letter.docx")


def build_submission():
    """Copy the journal submission set (anonymized manuscript, title page, Fig1-Fig9 TIFF) to submission/."""
    import shutil
    os.makedirs("submission", exist_ok=True)
    for f in ["Manuscript_anonymized.docx", "Title_Page.docx", "Cover_Letter.docx"]:
        shutil.copy(f, os.path.join("submission", f))
    for n in range(1, 10):
        src = os.path.join("..", "results", "figures", f"Fig{n}.tif")
        if os.path.exists(src):
            shutil.copy(src, os.path.join("submission", f"Fig{n}.tif"))


if __name__ == "__main__":
    build_manuscript(); build_title_page(); build_full_paper(); build_cover_letter(); build_submission()
    for tmp in ["ref_jeet.docx"]:
        if os.path.exists(tmp): os.remove(tmp)
    print("written Manuscript_anonymized.docx, Title_Page.docx, Research_Paper_Complete.docx, Cover_Letter.docx, submission/")
