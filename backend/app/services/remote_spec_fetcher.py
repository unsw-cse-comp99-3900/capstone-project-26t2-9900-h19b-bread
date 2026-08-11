import ipaddress
import socket
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_SPEC_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_PORTS = {80, 443}


class RemoteSpecFetchError(ValueError):
    pass


Resolver = Callable[..., list[tuple]]


def validate_public_http_url(url: str, resolver: Resolver = socket.getaddrinfo) -> str:
    """Reject URLs that can reach local, private, or special-purpose networks."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise RemoteSpecFetchError("Specification URL must use http or https.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise RemoteSpecFetchError("Specification URL must contain a public host.")

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise RemoteSpecFetchError("Specification URL contains an invalid port.") from exc
    if port not in ALLOWED_PORTS:
        raise RemoteSpecFetchError("Specification URL must use port 80 or 443.")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise RemoteSpecFetchError("Specification URL must contain a public host.")

    try:
        addresses = {item[4][0] for item in resolver(hostname, port, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise RemoteSpecFetchError("Specification host could not be resolved.") from exc
    if not addresses:
        raise RemoteSpecFetchError("Specification host could not be resolved.")

    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError as exc:
            raise RemoteSpecFetchError("Specification host resolved to an invalid address.") from exc
        if not ip.is_global:
            raise RemoteSpecFetchError("Specification URL must not target a private or local address.")

    return url


class PublicOnlyRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute_url = urljoin(req.full_url, newurl)
        validate_public_http_url(absolute_url)
        return super().redirect_request(req, fp, code, msg, headers, absolute_url)


def fetch_remote_spec(url: str, *, timeout: float = 10) -> str:
    validate_public_http_url(url)
    opener = build_opener(PublicOnlyRedirectHandler())
    request = Request(url, headers={"User-Agent": "BREAD-Spec-Importer/1.0"})

    try:
        with opener.open(request, timeout=timeout) as response:
            validate_public_http_url(response.geturl())
            content = response.read(MAX_SPEC_SIZE_BYTES + 1)
    except RemoteSpecFetchError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RemoteSpecFetchError("Specification could not be downloaded.") from exc

    if len(content) > MAX_SPEC_SIZE_BYTES:
        raise RemoteSpecFetchError("Specification file is too large. Maximum size is 5MB.")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RemoteSpecFetchError("Specification content must be valid UTF-8 text.") from exc
