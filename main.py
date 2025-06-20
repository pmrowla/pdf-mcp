from base64 import b64encode
from io import BytesIO
from pathlib import Path
from typing import Any

import click
from fastmcp import Context, FastMCP
from fastmcp.resources import FileResource
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import LITERALS_FLATE_DECODE, PDFObjRef, PDFStream, resolve1


mcp = FastMCP(name="PDF-MCP")


def find_resources(datadir: Path) -> None:
    for path in datadir.glob("*.pdf"):
        resource = FileResource(
            uri=f"pdf://{path.stem}",
            path=path.resolve(),
            mime_type="application/pdf",
        )
        mcp.add_resource(resource)


@mcp.prompt
def inspect_page(uri: str, page: int) -> str:
    return (
        f"Run the MCP tool debug_page on resource {uri} and page {page}. "
        "Inspect the page contents and resources for any parameters or values "
        "that are undefined or invalid according to the PDF specification, and for any "
        "parameters or values that may be valid but are still uncommon in PDF. "
        "Output your findings and include references to the relevant parts of the PDF "
        "specification when possible."
    )


@mcp.tool
async def debug_page(uri: str, page: int, ctx: Context) -> dict[str, Any]:
    """Debug raw page contents in a PDF."""
    resource = await ctx.read_resource(uri)
    if not resource:
        raise FileNotFoundError(f"{uri} not found")
    data = resource[0].content
    return dump_page(data, page)


def dump_page(data: bytes, pagenum: int) -> Any:
    fp = BytesIO(data)
    parser = PDFParser(fp)
    doc = PDFDocument(parser)
    pages = PDFPage.create_pages(doc)
    for i, page in enumerate(pages):
        if i + 1 == pagenum:
            contents = {}
            for obj in page.contents:
                contents = dump_obj(obj)
            resources = {}
            for k, v in page.resources.items():
                resources[str(k)] = dump_obj(v)
            return {
                "contents": contents,
                "resources": resources,
            }
    raise ValueError("Page out of range")


def dump_obj(obj: object) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: dump_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [dump_obj(x) for x in obj]
    if isinstance(obj, str):
        return obj
    if isinstance(obj, bytes):
        return b64encode(obj).decode("ascii")
    if isinstance(obj, PDFStream):
        return dump_stream(obj)
    if isinstance(obj, PDFObjRef):
        return dump_obj(resolve1(obj))
    return repr(obj)


def dump_stream(stream: PDFStream) -> dict[str, Any]:
    filters = stream.get_filters()
    result = {}
    if filters:
        for f, params in filters:
            if f in LITERALS_FLATE_DECODE:
                result["stream"] = stream.get_data().decode("ascii")
            else:
                result["params"] = params
                result["stream"] = b64encode(stream.rawdata).decode("ascii")
    else:
        result["stream"] = stream.get_data().decode("ascii")
    return {f"{stream.objid} 0 obj": result}


@click.command()
@click.option("-d", "--datadir", type=click.Path(file_okay=False, path_type=Path))
def main(datadir: Path | None):
    find_resources(datadir or Path.cwd())
    mcp.run()


if __name__ == "__main__":
    main()
