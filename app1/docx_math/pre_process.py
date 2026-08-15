"""
DOCX文件中的OMML公式预处理工具
将DOCX中的OMML（Office Math Markup Language）公式替换为LaTeX格式的文本，
使得python-docx等工具可以读取到公式内容。

改编自markitdown项目 (Microsoft)
"""

import zipfile
import os
import tempfile
import shutil
from io import BytesIO
from typing import BinaryIO
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup, Tag

from .omml import OMML_NS, oMath2Latex

MATH_ROOT_TEMPLATE = "".join(
    (
        "<w:document ",
        'xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" ',
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" ',
        'xmlns:o="urn:schemas-microsoft-com:office:office" ',
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ',
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" ',
        'xmlns:v="urn:schemas-microsoft-com:vml" ',
        'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" ',
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" ',
        'xmlns:w10="urn:schemas-microsoft-com:office:word" ',
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ',
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" ',
        'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" ',
        'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" ',
        'xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" ',
        'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" mc:Ignorable="w14 wp14">',
        "{0}</w:document>",
    )
)


def _convert_omath_to_latex(tag: Tag) -> str:
    """
    Converts an OMML tag to LaTeX format.

    Args:
        tag: A BeautifulSoup Tag object representing the OMML element.

    Returns:
        str: The LaTeX representation.
    """
    math_root = ET.fromstring(MATH_ROOT_TEMPLATE.format(str(tag)))
    math_element = math_root.find(OMML_NS + "oMath")
    latex = oMath2Latex(math_element).latex
    return latex


def _get_omath_tag_replacement(tag: Tag, block: bool = False) -> Tag:
    """
    Creates a replacement tag for an OMML element, wraps LaTeX in $...$ or $$...$$.

    Args:
        tag: A BeautifulSoup Tag object representing the "oMath" element.
        block: If True, wrap in $$ for block mode.

    Returns:
        Tag: A BeautifulSoup Tag representing the replacement w:r/w:t element.
    """
    t_tag = Tag(name="w:t")
    t_tag.string = (
        f"$${_convert_omath_to_latex(tag)}$$"
        if block
        else f"${_convert_omath_to_latex(tag)}$"
    )
    r_tag = Tag(name="w:r")
    r_tag.append(t_tag)
    return r_tag


def _replace_equations(tag: Tag):
    """
    Replaces OMML elements with LaTeX equivalents.

    Args:
        tag: A BeautifulSoup Tag - either "oMathPara" or "oMath".
    """
    if tag.name == "oMathPara":
        p_tag = Tag(name="w:p")
        for child_tag in tag.find_all("oMath"):
            p_tag.append(_get_omath_tag_replacement(child_tag, block=True))
        tag.replace_with(p_tag)
    elif tag.name == "oMath":
        tag.replace_with(_get_omath_tag_replacement(tag, block=False))
    else:
        raise ValueError(f"Not supported tag: {tag.name}")


def _pre_process_math(content: bytes) -> bytes:
    """
    Pre-processes math content by converting OMML elements to LaTeX.

    Args:
        content: XML content bytes from within a DOCX file.

    Returns:
        bytes: Processed content with OMML replaced by LaTeX.
    """
    soup = BeautifulSoup(content.decode(), features="xml")
    for tag in soup.find_all("oMathPara"):
        _replace_equations(tag)
    for tag in soup.find_all("oMath"):
        _replace_equations(tag)
    return str(soup).encode()


def pre_process_docx_stream(input_docx: BinaryIO) -> BinaryIO:
    """
    Pre-processes a DOCX stream, converting OMML formulas to LaTeX text.

    Args:
        input_docx: A binary input stream representing the DOCX file.

    Returns:
        BinaryIO: A binary output stream with formulas replaced by LaTeX.
    """
    output_docx = BytesIO()
    pre_process_enable_files = [
        "word/document.xml",
        "word/footnotes.xml",
        "word/endnotes.xml",
    ]
    with zipfile.ZipFile(input_docx, mode="r") as zip_input:
        files = {name: zip_input.read(name) for name in zip_input.namelist()}
        with zipfile.ZipFile(output_docx, mode="w") as zip_output:
            zip_output.comment = zip_input.comment
            for name, content in files.items():
                if name in pre_process_enable_files:
                    try:
                        updated_content = _pre_process_math(content)
                        zip_output.writestr(name, updated_content)
                    except Exception:
                        zip_output.writestr(name, content)
                else:
                    zip_output.writestr(name, content)
    output_docx.seek(0)
    return output_docx


def pre_process_docx_file(file_path: str) -> str:
    """
    Pre-processes a DOCX file on disk, replacing OMML formulas with LaTeX.
    Creates a temporary processed file and returns its path.

    Args:
        file_path: Path to the .docx file.

    Returns:
        str: Path to the processed .docx file (a temp file).
    """
    with open(file_path, "rb") as f:
        processed_stream = pre_process_docx_stream(f)

    # 写入临时文件
    fd, tmp_path = tempfile.mkstemp(suffix=".docx")
    os.close(fd)
    with open(tmp_path, "wb") as f:
        f.write(processed_stream.read())

    return tmp_path
