import xml.etree.ElementTree as ET


def parse_document(raw: str) -> list[str]:
    root = ET.fromstring(raw)
    return [child.tag for child in root]
