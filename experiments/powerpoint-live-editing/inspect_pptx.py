"""Bounded independent inspection of the synthetic one-slide coauthoring fixture."""
import argparse
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main", "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


def inspect(file):
    file = Path(file)
    if file.stat().st_size > 1_000_000:
        raise ValueError("Fixture exceeds the download limit")
    with zipfile.ZipFile(file) as archive:
        entries = archive.infolist()
        if len(entries) > 200 or sum(e.file_size for e in entries) > 8_000_000 or len({e.filename for e in entries}) != len(entries):
            raise ValueError("Unsupported fixture package")

        def xml(name):
            data = archive.read(name)
            if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
                raise ValueError("Unsupported XML declarations")
            return ET.fromstring(data)

        slide_names = [e.filename for e in entries if e.filename.startswith("ppt/slides/slide") and e.filename.endswith(".xml")]
        if len(slide_names) != 1:
            raise ValueError("Expected one slide")
        slide = xml(slide_names[0])
        tree = slide.find("p:cSld/p:spTree", NS)
        if tree is None or any(child.tag.split("}")[-1] not in {"nvGrpSpPr", "grpSpPr", "sp"} for child in tree):
            raise ValueError("Unexpected objects in fixture")
        shapes = {}
        for shape in slide.findall("p:cSld/p:spTree/p:sp", NS):
            identity = shape.find("p:nvSpPr/p:cNvPr", NS)
            name = identity.get("name")
            if name in shapes:
                raise ValueError("Ambiguous shape name")
            paragraphs = shape.findall("p:txBody/a:p", NS)
            text = "\n".join("".join(t.text or "" for t in p.findall(".//a:t", NS)) for p in paragraphs)
            transform = shape.find("p:spPr/a:xfrm", NS)
            geometry = {} if transform is None else {e.tag.split("}")[-1]: dict(e.attrib) for e in transform}
            styles = []
            for properties in shape.findall("p:txBody/a:p/a:r/a:rPr", NS):
                attrs = {k: v for k, v in properties.attrib.items() if k in {"b", "i", "sz", "u", "baseline", "strike"}}
                for child in properties:
                    kind = child.tag.split("}")[-1]
                    if kind in {"latin", "ea", "cs", "solidFill"}:
                        attrs[kind] = [(n.tag.split("}")[-1], sorted(n.attrib.items())) for n in child.iter()]
                styles.append(json.dumps(attrs, sort_keys=True))
            shapes[name] = {"id": identity.get("id"), "text": text, "geometry": geometry, "styles": sorted(set(styles))}
        if set(shapes) != {"Title", "Description", "ALPHA", "BETA", "Preservation"}:
            raise ValueError("Not the expected disposable fixture")
        size = dict(xml("ppt/presentation.xml").find("p:sldSz", NS).attrib)
        return {"slide_size": size, "shapes": shapes}


def compare(reference, actual, alpha=None, beta=None):
    expected = json.loads(json.dumps(reference))
    if alpha is not None:
        expected["shapes"]["ALPHA"]["text"] = alpha
    if beta is not None:
        expected["shapes"]["BETA"]["text"] = beta
    differences = []
    if expected["slide_size"] != actual["slide_size"]:
        differences.append("slide_size")
    for name, shape in expected["shapes"].items():
        for key, value in shape.items():
            if actual["shapes"].get(name, {}).get(key) != value:
                differences.append(f"{name}.{key}")
    return differences


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("--reference")
    parser.add_argument("--alpha")
    parser.add_argument("--beta")
    args = parser.parse_args()
    actual = inspect(args.file)
    if args.reference:
        differences = compare(inspect(args.reference), actual, args.alpha, args.beta)
        print(json.dumps({"status": "cloud_fixture_verified" if not differences else "mismatch", "differences": differences, "shapes": actual["shapes"]}, indent=2))
        raise SystemExit(bool(differences))
    print(json.dumps(actual, indent=2))
