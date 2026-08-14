from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import rsa

from .i18n import get_language, is_rtl, tr
from .models import Account


LOCAL_CALLBACK_PORTS = range(8765, 8785)


OAUTH_PROVIDERS: dict[str, dict[str, Any]] = {
    "google_gmail_api": {
        "name": "Google / Gmail",
        "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_endpoint": "https://oauth2.googleapis.com/token",
        "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
        "scopes": [
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/gmail.modify",
        ],
        "extra_authorize": {
            "access_type": "offline",
            "prompt": "consent select_account",
        },
        "imap_server": "",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_server": "",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
        "spam_mailbox": "SPAM",
        "sent_mailbox": "SENT",
    },
    "microsoft": {
        "name": "Microsoft / Outlook",
        "authorization_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "jwks_uri": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
        "scopes": [
            "openid",
            "profile",
            "email",
            "offline_access",
            "https://outlook.office.com/IMAP.AccessAsUser.All",
            "https://outlook.office.com/SMTP.Send",
        ],
        "extra_authorize": {
            "prompt": "select_account",
        },
        "imap_server": "outlook.office365.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_server": "smtp-mail.outlook.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
        "spam_mailbox": "Junk Email",
    },
}
MAX_OAUTH_RESPONSE_BYTES = 1024 * 1024
OAUTH_CLOCK_SKEW_SECONDS = 120
JWKS_CACHE_SECONDS = 60 * 60
_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_JWKS_CACHE_LOCK = threading.Lock()


class OAuthError(RuntimeError):
    pass


class OAuthReauthenticationRequired(OAuthError):
    def __init__(self, message: str, account_id: str = "") -> None:
        super().__init__(message)
        self.account_id = account_id


@dataclass(slots=True)
class OAuthFlowResult:
    provider_id: str
    email_address: str
    display_name: str
    access_token: str
    refresh_token: str
    expires_at: float


def provider_display_names() -> list[str]:
    return [OAUTH_PROVIDERS[provider_id]["name"] for provider_id in available_provider_ids()]


def available_provider_ids() -> list[str]:
    return ["google_gmail_api", "microsoft"]


def provider_id_from_name(name: str) -> str:
    for provider_id in available_provider_ids():
        provider = OAUTH_PROVIDERS[provider_id]
        if provider["name"] == name:
            return provider_id
    raise OAuthError("مزود OAuth غير معروف.")


def google_provider_id() -> str:
    for provider_id in available_provider_ids():
        if provider_id.startswith("google"):
            return provider_id
    raise OAuthError("مزود Google غير متاح في هذه النسخة.")


def apply_provider_settings(account: Account, provider_id: str) -> None:
    provider = OAUTH_PROVIDERS[provider_id]
    for key in [
        "imap_server",
        "imap_port",
        "imap_ssl",
        "smtp_server",
        "smtp_port",
        "smtp_ssl",
        "smtp_starttls",
        "spam_mailbox",
        "sent_mailbox",
    ]:
        if key in provider:
            setattr(account, key, provider[key])


def run_browser_oauth_flow(
    provider_id: str,
    client_id: str,
    client_secret: str = "",
    timeout_seconds: int = 300,
    cancel_event: threading.Event | None = None,
) -> OAuthFlowResult:
    provider = OAUTH_PROVIDERS.get(provider_id)
    if not provider:
        raise OAuthError("مزود OAuth غير معروف.")
    if not client_id.strip():
        raise OAuthError(
            "تسجيل الدخول عبر المتصفح غير مجهز بعد. يحتاج مطور البرنامج إلى تجهيز "
            "OAuth مرة واحدة، وبعدها سيرى المستخدم صفحة اختيار الحساب والموافقة فقط."
        )

    code_verifier = _new_code_verifier()
    code_challenge = _code_challenge(code_verifier)
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    server = _make_callback_server(state)
    server_thread = threading.Thread(
        target=_serve_callback_until_done,
        args=(server, timeout_seconds),
        daemon=True,
    )
    server_thread.start()

    redirect_uri = f"http://localhost:{server.server_port}"
    auth_params: dict[str, str] = {
        "client_id": client_id.strip(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(provider["scopes"]),
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_params.update(provider.get("extra_authorize", {}))
    authorize_url = provider["authorization_endpoint"] + "?" + urllib.parse.urlencode(auth_params)

    if not webbrowser.open(authorize_url):
        server.server_close()
        raise OAuthError("تعذر فتح المتصفح لإكمال تسجيل الدخول.")
    deadline = time.monotonic() + timeout_seconds
    while not server.oauth_event.is_set():
        if cancel_event is not None and cancel_event.is_set():
            server.server_close()
            raise OAuthError("تم إلغاء تسجيل الدخول عبر المتصفح.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        server.oauth_event.wait(min(0.25, remaining))
    if not server.oauth_event.is_set():
        server.server_close()
        raise OAuthError(
            "انتهى وقت انتظار تسجيل الدخول عبر المتصفح. إذا بقيت صفحة Google على "
            "تحذير تطبيق غير موثق، فتأكد أن عنوان Gmail المستخدم مضاف إلى قائمة "
            "المختبرين في Google Cloud ثم أكمل خطوات الموافقة."
        )

    server.server_close()
    if server.oauth_error:
        raise OAuthError(server.oauth_error)
    if not server.oauth_code:
        raise OAuthError("لم يصل رمز الدخول من المتصفح.")

    token_payload = _exchange_code_for_token(
        provider,
        client_id.strip(),
        client_secret.strip(),
        server.oauth_code,
        redirect_uri,
        code_verifier,
    )
    access_token = str(token_payload.get("access_token") or "")
    if not access_token:
        raise OAuthError("لم يرسل مزود الخدمة رمز دخول صالحا.")

    profile = _validate_id_token(
        provider_id,
        str(token_payload.get("id_token") or ""),
        client_id.strip(),
        nonce,
    )
    email_address = _profile_email(profile)
    display_name = str(profile.get("name") or profile.get("given_name") or email_address)
    expires_at = time.time() + int(token_payload.get("expires_in") or 3600) - 60
    return OAuthFlowResult(
        provider_id=provider_id,
        email_address=email_address,
        display_name=display_name,
        access_token=access_token,
        refresh_token=str(token_payload.get("refresh_token") or ""),
        expires_at=expires_at,
    )


def ensure_access_token(account: Account) -> bool:
    if not account.uses_oauth:
        return False
    if account.oauth_access_token and account.oauth_token_expiry > time.time() + 90:
        return False
    if not account.oauth_refresh_token:
        raise OAuthReauthenticationRequired(
            "انتهت صلاحية تسجيل الدخول. افتح خيارات الحسابات وإدارتها ثم اختر إعادة تسجيل الدخول للحساب.",
            account.id,
        )

    provider = OAUTH_PROVIDERS.get(account.oauth_provider)
    if not provider:
        raise OAuthError("مزود OAuth غير معروف.")

    data: dict[str, str] = {
        "client_id": account.oauth_client_id,
        "refresh_token": account.oauth_refresh_token,
        "grant_type": "refresh_token",
    }
    if account.oauth_client_secret:
        data["client_secret"] = account.oauth_client_secret
    if account.oauth_provider == "microsoft":
        data["scope"] = " ".join(provider["scopes"])

    try:
        payload = _post_form(provider["token_endpoint"], data)
    except OAuthReauthenticationRequired as exc:
        exc.account_id = account.id
        raise
    access_token = str(payload.get("access_token") or "")
    if not access_token:
        raise OAuthError("تعذر تحديث رمز OAuth.")
    account.oauth_access_token = access_token
    refresh_token = str(payload.get("refresh_token") or "")
    if refresh_token:
        account.oauth_refresh_token = refresh_token
    account.oauth_token_expiry = time.time() + int(payload.get("expires_in") or 3600) - 60
    return True


def xoauth2_auth_string(username: str, access_token: str) -> bytes:
    return f"user={username}\x01auth=Bearer {access_token}\x01\x01".encode("utf-8")


def _make_callback_server(state: str) -> HTTPServer:
    last_error: OSError | None = None
    for port in LOCAL_CALLBACK_PORTS:
        try:
            server = HTTPServer(("localhost", port), _callback_handler(state))
            server.timeout = 0.5
            server.oauth_event = threading.Event()  # type: ignore[attr-defined]
            server.oauth_code = ""  # type: ignore[attr-defined]
            server.oauth_error = ""  # type: ignore[attr-defined]
            return server
        except OSError as exc:
            last_error = exc
    raise OAuthError(f"تعذر فتح منفذ محلي لاستقبال تسجيل الدخول: {last_error}")


def _callback_handler(expected_state: str) -> type[BaseHTTPRequestHandler]:
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            received_state = query.get("state", [""])[0]
            if parsed.path not in {"", "/", "/callback"}:
                self._finish("هذه الصفحة خاصة بتسجيل الدخول إلى برنامج البريد.")
                return
            if received_state != expected_state:
                self.server.oauth_error = "رفض تسجيل الدخول لأن رمز التحقق غير مطابق."  # type: ignore[attr-defined]
            elif query.get("error"):
                error_code = query.get("error", [""])[0]
                error_description = query.get("error_description", [""])[0]
                self.server.oauth_error = oauth_callback_error_message(  # type: ignore[attr-defined]
                    error_code,
                    error_description,
                )
            else:
                self.server.oauth_code = query.get("code", [""])[0]  # type: ignore[attr-defined]
            self.server.oauth_event.set()  # type: ignore[attr-defined]
            self._finish(
                "تم استلام موافقة تسجيل الدخول. عد الآن إلى برنامج Power Accessible Mail "
                "وانتظر رسالة نجاح إضافة الحساب. إذا بقيت نافذة تسجيل الدخول ظاهرة، "
                "فاقرأ رسالة الخطأ داخل البرنامج وأرسلها إلى المطور."
            )

        def _finish(self, message: str) -> None:
            localized_message = tr(message)
            language = get_language()
            direction = "rtl" if is_rtl() else "ltr"
            body = (
                f"<!doctype html><html lang='{language}' dir='{direction}'><head>"
                "<meta charset='utf-8'><title>Power Accessible Mail</title></head>"
                f"<body><h1>{html.escape(localized_message)}</h1></body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return CallbackHandler


def oauth_callback_error_message(error_code: str, error_description: str) -> str:
    code = urllib.parse.unquote_plus(error_code).strip().lower()
    description = urllib.parse.unquote_plus(error_description).strip()
    normalized_description = description.lower()
    if code == "access_denied":
        blocked_markers = (
            "access blocked",
            "not completed the google verification",
            "not a test user",
            "test user",
            "verification process",
        )
        if any(marker in normalized_description for marker in blocked_markers):
            return (
                "رفضت Google تسجيل الدخول إلى التطبيق. إذا كان التطبيق في وضع "
                "الاختبار، يجب أن يضيف المطور عنوان Gmail نفسه إلى قائمة المختبرين "
                "في Google Cloud. تأكد أيضا أن الحساب المختار في المتصفح هو الحساب المضاف."
            )
        return "ألغيت الموافقة على وصول Power Accessible Mail إلى الحساب."
    if code == "org_internal":
        return (
            "هذا المشروع يسمح بحسابات المؤسسة فقط، ولا يقبل حساب Gmail المختار. "
            "يجب على المطور جعل نوع المستخدم External أو استخدام حساب تابع للمؤسسة."
        )
    return description or code or "خطأ غير معروف"


def _serve_callback_until_done(server: HTTPServer, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not server.oauth_event.is_set() and time.monotonic() < deadline:  # type: ignore[attr-defined]
        server.handle_request()


def _exchange_code_for_token(
    provider: dict[str, Any],
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict[str, Any]:
    data = {
        "client_id": client_id,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    if client_secret:
        data["client_secret"] = client_secret
    return _post_form(provider["token_endpoint"], data)


def _post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme.lower() != "https" or not parsed_url.netloc:
        raise OAuthError("رفض البرنامج الاتصال بخدمة OAuth غير آمنة.")
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            final_url = str(response.geturl() or url)
            parsed_final_url = urllib.parse.urlparse(final_url)
            if (
                parsed_final_url.scheme.lower() != "https"
                or not parsed_final_url.netloc
            ):
                raise OAuthError(
                    "أعادت خدمة OAuth التوجيه إلى اتصال غير آمن."
                )
            payload = response.read(MAX_OAUTH_RESPONSE_BYTES + 1)
            if len(payload) > MAX_OAUTH_RESPONSE_BYTES:
                raise OAuthError("استجابة خدمة OAuth أكبر من الحجم المسموح.")
            decoded = json.loads(payload.decode("utf-8"))
            if not isinstance(decoded, dict):
                raise OAuthError("أرسلت خدمة OAuth استجابة غير صالحة.")
            return decoded
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        error_code = ""
        try:
            payload = json.loads(detail)
            error_code = str(payload.get("error") or "").lower()
            message = payload.get("error_description") or payload.get("error") or detail
        except json.JSONDecodeError:
            message = detail
        normalized = str(message).lower()
        if oauth_error_requires_reauthentication(error_code, normalized):
            raise OAuthReauthenticationRequired(
                "انتهت صلاحية تسجيل الدخول أو ألغيت من مزود البريد. "
                "افتح خيارات الحسابات وإدارتها ثم اختر إعادة تسجيل الدخول للحساب."
            ) from exc
        if error_code == "invalid_scope" or "invalid_scope" in normalized:
            message = (
                f"{message}\n\n"
                "الحل: احذف الحساب من البرنامج أو أعد إضافته عبر تسجيل الدخول بالمتصفح. "
                "لحساب Google تأكد أن مشروع Google Cloud يحتوي نطاق gmail.modify. "
                "ولحساب Microsoft تأكد من إضافة صلاحيات IMAP.AccessAsUser.All وSMTP.Send."
            )
        raise OAuthError(f"فشل طلب OAuth: {message}") from exc
    except urllib.error.URLError as exc:
        raise OAuthError(f"تعذر الاتصال بخدمة OAuth: {exc.reason}") from exc


def oauth_error_requires_reauthentication(error_code: str, message: str) -> bool:
    normalized_code = error_code.strip().lower()
    normalized_message = message.strip().lower()
    return normalized_code == "invalid_grant" or any(
        marker in normalized_message
        for marker in (
            "invalid_grant",
            "token has been expired",
            "token has expired",
            "token has been revoked",
            "expired or revoked",
        )
    )


def _new_code_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(48)).decode("ascii").rstrip("=")


def _code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _validate_id_token(
    provider_id: str,
    id_token: str,
    client_id: str,
    expected_nonce: str,
) -> dict[str, Any]:
    header, claims, signing_input, signature = _parse_id_token(id_token)
    if header.get("alg") != "RS256" or not str(header.get("kid") or ""):
        raise OAuthError("رمز هوية تسجيل الدخول لا يستخدم توقيعا آمنا مدعوما.")
    key_data = _find_signing_key(provider_id, str(header["kid"]))
    if (
        key_data.get("kty") != "RSA"
        or key_data.get("alg") not in {None, "", "RS256"}
        or key_data.get("use") not in {None, "", "sig"}
    ):
        raise OAuthError("مفتاح توقيع رمز الهوية غير صالح.")
    try:
        modulus = int.from_bytes(_base64url_bytes(str(key_data["n"])), "big")
        exponent = int.from_bytes(_base64url_bytes(str(key_data["e"])), "big")
        if modulus.bit_length() < 2048 or exponent < 3 or exponent % 2 == 0:
            raise ValueError("Weak RSA key")
        public_key = rsa.PublicKey(modulus, exponent)
        hash_name = rsa.verify(signing_input, signature, public_key)
    except (KeyError, ValueError, TypeError, rsa.VerificationError) as exc:
        raise OAuthError("فشل التحقق من التوقيع الرقمي لرمز الهوية.") from exc
    if hash_name != "SHA-256":
        raise OAuthError("خوارزمية توقيع رمز الهوية غير مدعومة.")
    _validate_id_token_claims(provider_id, claims, client_id, expected_nonce, key_data)
    return claims


def _parse_id_token(
    id_token: str,
) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    parts = id_token.split(".")
    if len(parts) != 3 or not all(parts):
        raise OAuthError("لم يرسل مزود الخدمة رمز هوية صالحا.")
    try:
        header = json.loads(_base64url_bytes(parts[0]).decode("utf-8"))
        claims = json.loads(_base64url_bytes(parts[1]).decode("utf-8"))
        signature = _base64url_bytes(parts[2])
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OAuthError("رمز هوية تسجيل الدخول تالف أو غير صالح.") from exc
    if not isinstance(header, dict) or not isinstance(claims, dict):
        raise OAuthError("رمز هوية تسجيل الدخول لا يحتوي على بيانات صالحة.")
    return header, claims, f"{parts[0]}.{parts[1]}".encode("ascii"), signature


def _validate_id_token_claims(
    provider_id: str,
    claims: dict[str, Any],
    client_id: str,
    expected_nonce: str,
    signing_key: dict[str, Any],
) -> None:
    now = time.time()
    try:
        expires_at = float(claims["exp"])
        issued_at = float(claims["iat"])
    except (KeyError, TypeError, ValueError) as exc:
        raise OAuthError("رمز الهوية لا يحتوي على أوقات صلاحية صحيحة.") from exc
    if expires_at < now - OAUTH_CLOCK_SKEW_SECONDS:
        raise OAuthError("انتهت صلاحية رمز هوية تسجيل الدخول.")
    if issued_at > now + OAUTH_CLOCK_SKEW_SECONDS:
        raise OAuthError("وقت إصدار رمز الهوية غير صالح.")
    if "nbf" in claims:
        try:
            not_before = float(claims["nbf"])
        except (TypeError, ValueError) as exc:
            raise OAuthError("وقت بدء صلاحية رمز الهوية غير صالح.") from exc
        if not_before > now + OAUTH_CLOCK_SKEW_SECONDS:
            raise OAuthError("رمز الهوية غير صالح للاستخدام بعد.")

    audience = claims.get("aud")
    valid_audience = audience == client_id or (
        isinstance(audience, list) and client_id in audience
    )
    if not valid_audience:
        raise OAuthError("رمز الهوية صادر لتطبيق آخر.")
    if isinstance(audience, list) and len(audience) > 1 and claims.get("azp") != client_id:
        raise OAuthError("مقدم رمز الهوية لا يطابق هذا التطبيق.")
    nonce = str(claims.get("nonce") or "")
    if not nonce or not hmac.compare_digest(nonce, expected_nonce):
        raise OAuthError("رفض رمز الهوية لأن رمز منع إعادة التشغيل غير مطابق.")
    if not str(claims.get("sub") or "").strip():
        raise OAuthError("رمز الهوية لا يحتوي على معرّف مستخدم صالح.")

    issuer = str(claims.get("iss") or "").rstrip("/")
    if provider_id == "google_gmail_api":
        if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
            raise OAuthError("رمز الهوية لم يصدر من Google.")
        if claims.get("email_verified") is not True:
            raise OAuthError("لم تؤكد Google ملكية عنوان البريد لهذا الحساب.")
    elif provider_id == "microsoft":
        tenant_id = str(claims.get("tid") or "").lower()
        if not _is_uuid(tenant_id):
            raise OAuthError("رمز هوية Microsoft لا يحتوي على مستأجر صالح.")
        expected_issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
        if issuer.casefold() != expected_issuer.casefold():
            raise OAuthError("مصدر رمز هوية Microsoft لا يطابق المستأجر.")
        key_issuer = str(signing_key.get("issuer") or "")
        if key_issuer:
            normalized_key_issuer = key_issuer.replace("{tenantid}", tenant_id)
            if normalized_key_issuer.rstrip("/").casefold() != expected_issuer.casefold():
                raise OAuthError("مفتاح Microsoft لا يطابق مستأجر رمز الهوية.")
    else:
        raise OAuthError("مزود OAuth غير معروف.")


def _find_signing_key(provider_id: str, key_id: str) -> dict[str, Any]:
    for force_refresh in (False, True):
        jwks = _load_jwks(provider_id, force_refresh=force_refresh)
        keys = jwks.get("keys")
        if isinstance(keys, list):
            for key in keys:
                if isinstance(key, dict) and hmac.compare_digest(
                    str(key.get("kid") or ""),
                    key_id,
                ):
                    return key
    raise OAuthError("لم يعثر البرنامج على مفتاح توقيع رمز الهوية.")


def _load_jwks(provider_id: str, *, force_refresh: bool) -> dict[str, Any]:
    provider = OAUTH_PROVIDERS.get(provider_id)
    if not provider:
        raise OAuthError("مزود OAuth غير معروف.")
    now = time.monotonic()
    with _JWKS_CACHE_LOCK:
        cached = _JWKS_CACHE.get(provider_id)
        if not force_refresh and cached and cached[0] > now:
            return cached[1]
    url = str(provider.get("jwks_uri") or "")
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        raise OAuthError("عنوان مفاتيح OAuth غير آمن.")
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Power Accessible Mail"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            final_url = urllib.parse.urlparse(str(response.geturl() or url))
            if (
                final_url.scheme != "https"
                or final_url.hostname != parsed_url.hostname
            ):
                raise OAuthError("أعيد توجيه مفاتيح OAuth إلى خادم غير موثوق.")
            payload = response.read(MAX_OAUTH_RESPONSE_BYTES + 1)
    except OAuthError:
        raise
    except (OSError, urllib.error.URLError) as exc:
        raise OAuthError("تعذر تنزيل مفاتيح التحقق من مزود تسجيل الدخول.") from exc
    if len(payload) > MAX_OAUTH_RESPONSE_BYTES:
        raise OAuthError("استجابة مفاتيح OAuth أكبر من الحجم المسموح.")
    try:
        jwks = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OAuthError("استجابة مفاتيح OAuth غير صالحة.") from exc
    if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
        raise OAuthError("استجابة مفاتيح OAuth لا تحتوي على مفاتيح صالحة.")
    with _JWKS_CACHE_LOCK:
        _JWKS_CACHE[provider_id] = (now + JWKS_CACHE_SECONDS, jwks)
    return jwks


def _base64url_bytes(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(
        (value + padding).encode("ascii"),
        altchars=b"-_",
        validate=True,
    )


def _is_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _profile_email(profile: dict[str, Any]) -> str:
    for key in ["email", "preferred_username", "upn", "unique_name"]:
        value = str(profile.get(key) or "").strip()
        if value:
            return value
    raise OAuthError("تم تسجيل الدخول، لكن لم أستطع معرفة عنوان البريد من الحساب.")
