def infer_schema(obj):
    if isinstance(obj, dict):
        properties = {key: infer_schema(value) for key, value in obj.items()}
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties.keys()),
        }
    if isinstance(obj, list):
        if obj:
            return {
                "type": "array",
                "items": infer_schema(obj[0]),
            }
        return {
            "type": "array",
            "items": {"type": "unknown"},
        }
    if isinstance(obj, bool):
        return {"type": "boolean"}
    if isinstance(obj, int):
        return {"type": "integer"}
    if isinstance(obj, float):
        return {"type": "number"}
    if isinstance(obj, str):
        return {"type": "string"}
    if obj is None:
        return {"type": "null"}
    return {"type": "unknown"}
