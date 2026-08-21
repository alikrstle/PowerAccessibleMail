from __future__ import annotations

import functools
import ipaddress
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

try:
    import truststore
except ImportError:  # pragma: no cover - retained for source-only recovery environments
    truststore = None


TLS_CERTIFICATE_ERROR_MESSAGE = (
    "تعذر التحقق من شهادة الاتصال الآمن. تأكد من صحة تاريخ ووقت Windows، "
    "ثم ثبّت تحديثات Windows وحدّث برنامج الحماية. لا يعطّل البرنامج التحقق "
    "من الشهادات لحماية تنزيل التحديث. يمكنك تنزيل أحدث إصدار يدويا من "
    "https://soljan-alsharq.com/downloads. رمز الخطأ: TLS-CERTIFICATE-VERIFY."
)


class UnsafeRemoteUrl(ValueError):
    pass


@functools.lru_cache(maxsize=1)
def trusted_https_context() -> ssl.SSLContext:
    """Build a verified TLS context backed by the native Windows trust engine."""
    if truststore is not None:
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        return context

    # Keep a verified recovery path for development/source environments where
    # dependencies have not been installed yet. Release builds include
    # ``truststore`` and therefore use Windows CryptoAPI, including automatic
    # intermediate-certificate retrieval and revocation checks.
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    enum_certificates = getattr(ssl, "enum_certificates", None)
    if sys.platform != "win32" or enum_certificates is None:
        return context
    for store_name in ("ROOT", "CA"):
        try:
            certificates = enum_certificates(store_name)
        except OSError:
            continue
        for certificate, encoding, _trust in certificates:
            if encoding != "x509_asn":
                continue
            try:
                context.load_verify_locations(cadata=certificate)
            except (ValueError, ssl.SSLError):
                continue
    return context


def certificate_verification_failed(error: BaseException) -> bool:
    """Return True when an exception chain represents a TLS certificate failure."""
    pending: list[object] = [error]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return True
        message = str(current).upper()
        if "CERTIFICATE_VERIFY_FAILED" in message or "CERT_HAS_EXPIRED" in message:
            return True
        if isinstance(current, urllib.error.URLError):
            pending.append(current.reason)
        if isinstance(current, BaseException):
            if current.__cause__ is not None:
                pending.append(current.__cause__)
            if current.__context__ is not None:
                pending.append(current.__context__)
    return False


def friendly_https_error(error: BaseException) -> str:
    """Translate certificate failures without ever disabling TLS verification."""
    return TLS_CERTIFICATE_ERROR_MESSAGE if certificate_verification_failed(error) else ""


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
