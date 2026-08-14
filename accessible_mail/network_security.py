from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request


class UnsafeRemoteUrl(ValueError):
    pass


def validate_public_http_url(value: object) -> str:
    url = str(value or "").strip()
    if not url or any(character.isspace() or ord(character) < 32 for character in url):
        raise UnsafeRemoteUrl("العنوان الخارجي غير صالح.")
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise UnsafeRemoteUrl("العنوان الخارجي غير صالح.") from exc
    if parsed.scheme.casefold() not in {"http", "https"}:
        raise UnsafeRemoteUrl("يسمح بتنزيل الصور عبر HTTP أو HTTPS فقط.")
    if not parsed.hostname or not parsed.netloc:
        raise UnsafeRemoteUrl("عنوان خادم الصورة غير صالح.")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeRemoteUrl("لا يسمح بعنوان صورة يحتوي على بيانات تسجيل دخول.")

    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        raise UnsafeRemoteUrl("تم منع تنزيل صورة من عنوان محلي.")
    if "." not in hostname and not _is_ip_literal(hostname):
        raise UnsafeRemoteUrl("تم منع تنزيل صورة من اسم جهاز محلي.")

    try:
        addresses = {
            item[4][0].split("%", 1)[0]
            for item in socket.getaddrinfo(
                hostname,
                port or (443 if parsed.scheme.casefold() == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except OSError as exc:
        raise UnsafeRemoteUrl("تعذر التحقق من عنوان خادم الصورة.") from exc
    if not addresses:
        raise UnsafeRemoteUrl("تعذر التحقق من عنوان خادم الصورة.")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeRemoteUrl("أعاد خادم الأسماء عنوانا غير صالح.") from exc
        if not ip.is_global:
            raise UnsafeRemoteUrl("تم منع تنزيل صورة من شبكة محلية أو خاصة.")
    return url


class PublicHttpRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        try:
            validated_url = validate_public_http_url(newurl)
        except UnsafeRemoteUrl as exc:
            raise urllib.error.HTTPError(
                req.full_url,
                code,
                str(exc),
                headers,  # type: ignore[arg-type]
                fp,  # type: ignore[arg-type]
            ) from exc
        return super().redirect_request(req, fp, code, msg, headers, validated_url)


def public_http_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(PublicHttpRedirectHandler())


def _is_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True
