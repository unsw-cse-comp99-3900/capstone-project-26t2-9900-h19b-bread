import xml.etree.ElementTree as ET

def infer_type(value):
    if value is None or value.strip() == "":
        return "string"

    value = value.strip()
    try:
        int(value)
        return "integer"
    except ValueError:
        pass

    try:
        float(value)
        return "number"
    except ValueError:
        pass

    if value.lower() in {"true", "false"}:
        return "boolean"
    return "string"

def analyze_element(element):
    schema = {
        "type": "object",
        "attributes": {},
        "properties": {},
        "required": [],
    }

    for attr, value in element.attrib.items():
        key = f"@{attr}"
        schema["properties"][key] = {"type": infer_type(value)}
        schema["required"].append(key)

    children = list(element)
    if not children:
        if element.text and element.text.strip():
            return {"type": infer_type(element.text)}
        return {"type": "string"}

    grouped_children = {}
    for child in children:
        tag = child.tag.split("}")[-1].split(":")[-1]
        grouped_children.setdefault(tag, []).append(analyze_element(child))
    for tag, child_schemas in grouped_children.items():
        schema["required"].append(tag)
        if len(child_schemas) > 1:
            schema["properties"][tag] = {
                "type": "array",
                "items": child_schemas[0],
            }
        else:
            schema["properties"][tag] = child_schemas[0]

    schema["required"] = sorted(set(schema["required"]))
    return schema

def extract_schema_from_xml(xml_string):
    root = ET.fromstring(xml_string)
    root_tag = root.tag.split("}")[-1].split(":")[-1]
    return {
        "root": root_tag,
        "schema": analyze_element(root),
    }
