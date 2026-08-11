import socket

import pytest

from app.services.remote_spec_fetcher import (
    RemoteSpecFetchError,
    validate_public_http_url,
)


def resolver_for(*addresses: str):
    def resolve(_host: str, port: int, **_kwargs):
        return [
            (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))
            for address in addresses
        ]

    return resolve


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/spec.yaml",
        "http://user:password@example.com/spec.yaml",
        "http://example.com:8080/spec.yaml",
        "http://localhost/spec.yaml",
        "http://service.localhost/spec.yaml",
    ],
)
def test_non_public_url_shapes_are_rejected(url: str) -> None:
    with pytest.raises(RemoteSpecFetchError):
        validate_public_http_url(url, resolver=resolver_for("93.184.216.34"))


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.0.5",
        "192.168.1.5",
        "169.254.169.254",
        "0.0.0.0",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_private_and_special_addresses_are_rejected(address: str) -> None:
    with pytest.raises(RemoteSpecFetchError):
        validate_public_http_url(
            "https://example.com/spec.yaml",
            resolver=resolver_for(address),
        )


def test_all_resolved_addresses_must_be_public() -> None:
    with pytest.raises(RemoteSpecFetchError):
        validate_public_http_url(
            "https://example.com/spec.yaml",
            resolver=resolver_for("93.184.216.34", "127.0.0.1"),
        )


def test_public_http_url_is_accepted() -> None:
    assert validate_public_http_url(
        "https://example.com/spec.yaml",
        resolver=resolver_for("93.184.216.34"),
    ) == "https://example.com/spec.yaml"
