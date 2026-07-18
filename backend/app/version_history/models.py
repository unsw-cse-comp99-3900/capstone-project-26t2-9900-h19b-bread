from dataclasses import dataclass


@dataclass(frozen=True)
class VersionWrite:
    version_number: str
    change_note: str | None
    api_name: str
    endpoint_url: str
    protocol_type: str
    input_format: str
    output_format: str
    capability_category: str
    description: str | None
    auth_method: str
    auth_description: str | None
    security_scheme_name: str | None
    spec_content: str
