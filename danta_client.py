"""
danta_client.py — Fudan DanTa (旦挞) API client.

Handles: Windows Credential Manager -> UIS (id.fudan.edu.cn) login ->
WebVPN session -> fduhole APIs (forum / danke).

Off-campus, *.fduhole.com resolves to 10.107.13.152 (campus-internal), so all
API traffic is rewritten through webvpn.fudan.edu.cn using the AES-CFB host
encoding that DanXi itself uses (key/iv = "wrdvpnisthebest!").

Safety: UIS login is attempted ONCE per session. Repeated failures trigger a
captcha on the university side that requires manual browser login to clear.
Sessions are cached on disk so normal use does not re-login.

Copyright (C) 2026  danta-mcp contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See <https://www.gnu.org/licenses/gpl-3.0.html>.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, quote

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from cryptography.hazmat.decrepit.ciphers.modes import CFB

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
ID_HOST = "id.fudan.edu.cn"
WEBVPN_HOST = "webvpn.fudan.edu.cn"
WEBVPN_KEY = b"wrdvpnisthebest!"
WEBVPN_SERVICE = "https://webvpn.fudan.edu.cn/login?cas_login=true"

AUTH_BASE = "https://auth.fduhole.com/api"
FORUM_BASE = "https://forum.fduhole.com/api"
DANKE_BASE = "https://danke.fduhole.com/api"

STATE_DIR = Path(os.environ.get("DANTA_STATE_DIR",
                                Path.home() / ".danta-mcp"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
TOKEN_FILE = STATE_DIR / "token.json"
COOKIE_FILE = STATE_DIR / "cookies.json"

CAPTCHA_MARKER = "验证码"
BAD_CRED_MARKER = "用户名或密码"

UIS_TARGET = "DanTaMCP_UIS"
HOLE_TARGET = "DanTaMCP_Hole"
_ENV_PREFIXES = {UIS_TARGET: "DANTA_UIS", HOLE_TARGET: "DANTA_HOLE"}


class DantaError(RuntimeError):
    pass


class CaptchaRequired(DantaError):
    """UIS demands a captcha. Manual browser login required to clear."""


class CredentialsInvalid(DantaError):
    pass


# --------------------------------------------------------------------------
# Windows Credential Manager
# --------------------------------------------------------------------------
_PS_READ = r'''
$sig=@"
using System;using System.Runtime.InteropServices;
public class CR{
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)]
 public struct CREDENTIAL{public UInt32 Flags;public UInt32 Type;public IntPtr TargetName;public IntPtr Comment;public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;public UInt32 CredentialBlobSize;public IntPtr CredentialBlob;public UInt32 Persist;public UInt32 AttributeCount;public IntPtr Attributes;public IntPtr TargetAlias;public IntPtr UserName;}
 [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
 public static extern bool CredReadW(string t,UInt32 ty,UInt32 f,out IntPtr c);
}
"@
Add-Type -TypeDefinition $sig -ErrorAction SilentlyContinue
$p=[IntPtr]::Zero
if([CR]::CredReadW("__TARGET__",1,0,[ref]$p)){
 $c=[Runtime.InteropServices.Marshal]::PtrToStructure($p,[Type][CR+CREDENTIAL])
 $u=[Runtime.InteropServices.Marshal]::PtrToStringUni($c.UserName)
 $pw=[Runtime.InteropServices.Marshal]::PtrToStringUni($c.CredentialBlob,$c.CredentialBlobSize/2)
 Write-Output ($u+"`t"+$pw)
}
'''


def read_credential(target: str) -> tuple[str, str]:
    """Read (username, password) for `target`.

    Resolution order:
      1. Environment variables (works everywhere, good for CI/containers):
         DANTA_UIS_USER / DANTA_UIS_PASS   for target 'DanTaMCP_UIS'
         DANTA_HOLE_USER / DANTA_HOLE_PASS for target 'DanTaMCP_Hole'
      2. Windows Credential Manager (DPAPI-backed) on Windows.
      3. `keyring` package, if installed (macOS Keychain / libsecret / etc).
    """
    env_prefix = _ENV_PREFIXES.get(target)
    if env_prefix:
        u = os.environ.get(f"{env_prefix}_USER")
        p = os.environ.get(f"{env_prefix}_PASS")
        if u and p:
            return u, p

    if sys.platform == "win32":
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", _PS_READ.replace("__TARGET__", target)],
            capture_output=True, text=True,
        )
        out = (r.stdout or "").strip()
        if "\t" in out:
            user, pw = out.split("\t", 1)
            return user.strip(), pw
    else:
        try:
            import keyring  # type: ignore
            cred = keyring.get_credential(target, None)
            if cred:
                return cred.username, cred.password
        except Exception:
            pass

    raise DantaError(
        f"Credential '{target}' not found.\n"
        f"  • Run `python setup_credentials.py`, or\n"
        f"  • set {env_prefix}_USER / {env_prefix}_PASS environment variables."
    )


# --------------------------------------------------------------------------
# WebVPN URL rewriting (mirrors DanXi's webvpn_proxy.dart)
# --------------------------------------------------------------------------
_host_cache: dict[str, str] = {}


def _encrypt_host(host: str) -> str:
    if host in _host_cache:
        return _host_cache[host]
    n = len(host)
    padded = host + "0" * ((16 - n % 16) % 16)
    enc = Cipher(algorithms.AES(WEBVPN_KEY), CFB(WEBVPN_KEY)).encryptor()
    ct = enc.update(padded.encode()) + enc.finalize()
    out = WEBVPN_KEY.hex() + ct.hex()[: 2 * n]
    _host_cache[host] = out
    return out


def webvpn_url(url: str) -> str:
    u = urlsplit(url)
    netloc = f"[{u.netloc}]" if ":" in u.netloc and "]" not in u.netloc else u.netloc
    seg = f"{u.scheme}-{u.port}" if u.port else u.scheme
    tail = u.path + (f"?{u.query}" if u.query else "") + (f"#{u.fragment}" if u.fragment else "")
    return f"https://{WEBVPN_HOST}/{seg}/{_encrypt_host(netloc)}{tail}"


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------
class DantaClient:
    def __init__(self, uis_target=UIS_TARGET, hole_target=HOLE_TARGET,
                 timeout=40, verbose=False):
        self.uis_target = uis_target
        self.hole_target = hole_target
        self.timeout = timeout
        self.verbose = verbose
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.token: str | None = None
        self._load_state()

    def _log(self, *a):
        if self.verbose:
            print("[danta]", *a, flush=True)

    # ---------- state ----------
    def _load_state(self):
        if COOKIE_FILE.exists():
            try:
                data = json.loads(COOKIE_FILE.read_text())
                fresh = data.get("saved_at", 0) + 6 * 3600 > time.time()
                if fresh:
                    for c in data.get("cookies", []):
                        self.s.cookies.set(
                            c["name"], c["value"],
                            domain=c.get("domain") or "",
                            path=c.get("path") or "/",
                        )
                    self._log("loaded cookies")
                else:
                    self._log("cached cookies stale, ignoring")
            except Exception:
                pass
        if TOKEN_FILE.exists():
            try:
                d = json.loads(TOKEN_FILE.read_text())
                if d.get("saved_at", 0) + 20 * 86400 > time.time():
                    self.token = d.get("access")
                    self._log("loaded cached token")
            except Exception:
                pass

    def _save_state(self):
        try:
            COOKIE_FILE.write_text(json.dumps({
                "saved_at": time.time(),
                "cookies": [
                    {"name": c.name, "value": c.value,
                     "domain": c.domain, "path": c.path}
                    for c in self.s.cookies
                ],
            }))
            if self.token:
                TOKEN_FILE.write_text(json.dumps(
                    {"access": self.token, "saved_at": time.time()}))
            for f in (COOKIE_FILE, TOKEN_FILE):
                if f.exists():
                    os.chmod(f, 0o600)
        except Exception as e:
            self._log("save state failed:", e)

    # ---------- HTTP with retry (WebVPN is flaky) ----------
    def _req(self, method, url, *, tries=3, **kw):
        kw.setdefault("timeout", self.timeout)
        last = None
        for i in range(tries):
            try:
                return self.s.request(method, url, **kw)
            except (requests.Timeout, requests.ConnectionError) as e:
                last = e
                self._log(f"{method} attempt {i+1}/{tries} failed: {type(e).__name__}")
                time.sleep(1.5 * (i + 1))
        raise DantaError(f"Network failure after {tries} tries: {url[:90]} :: {last}")

    # ---------- UIS / WebVPN ----------
    def ensure_webvpn(self, force=False) -> None:
        """Establish a WebVPN session. Logs in via UIS at most once."""
        if not force and self._webvpn_alive():
            self._log("webvpn session alive")
            return
        self._log("establishing webvpn session via UIS")
        self._uis_login()
        self._save_state()

    def _webvpn_alive(self) -> bool:
        if not any(c.name == "wengine_vpn_ticketwebvpn_fudan_edu_cn"
                   for c in self.s.cookies):
            return False
        try:
            r = self._req("GET", webvpn_url(f"{FORUM_BASE}/divisions"), tries=1, timeout=20)
            return "json" in r.headers.get("content-type", "")
        except Exception:
            return False

    @staticmethod
    def _extract_ticket_target(html: str) -> str | None:
        """Pull the service-redirect URL (with CAS ticket) out of an IDP page."""
        m = re.search(r'locationValue\s*=\s*"([^"]+)"', html)
        if m:
            return m.group(1).replace("&amp;", "&")
        tk = re.search(r'id="ticket"[^>]*value="([^"]+)"', html)
        ac = re.search(r'id="logon"[^>]*action="([^"]+)"', html)
        if tk and ac:
            tgt = ac.group(1).replace("&amp;", "&")
            return tgt + ("&" if "?" in tgt else "?") + "ticket=" + tk.group(1)
        return None

    def _uis_login(self) -> None:
        start = (f"https://{ID_HOST}/idp/authCenter/authenticate"
                 f"?service={quote(WEBVPN_SERVICE, safe='')}")
        r = self._req("GET", start, allow_redirects=True)

        # Fast path: an existing IDP session (usk cookie) means the server skips
        # the login UI and hands back the ticket page immediately.
        tgt = self._extract_ticket_target(r.text)
        if tgt:
            self._log("existing IDP session, reusing ticket")
            self._redeem(tgt)
            return

        if "#" not in r.url:
            raise DantaError(f"IDP did not return a login context: {r.url[:120]}")
        q = parse_qs(urlsplit("https://x/" + r.url.split("#", 1)[1]).query)
        lck, entity = q.get("lck", [None])[0], q.get("entityId", [None])[0]
        if not lck:
            raise DantaError("no lck in IDP URL")

        r = self._req("POST", f"https://{ID_HOST}/idp/authn/queryAuthMethods",
                      json={"lck": lck, "entityId": entity})
        d = r.json()
        if d.get("second") is True:
            raise DantaError("Enhanced authentication (2FA) required for this service.")
        methods = d.get("data") or []
        m = next((x for x in methods if x.get("moduleCode") == "userAndPwd"), None)
        if not m:
            raise DantaError(f"no userAndPwd method; got {[x.get('moduleCode') for x in methods]}")
        chain = m["authChainCode"]

        r = self._req("POST", f"https://{ID_HOST}/idp/authn/getJsPublicKey")
        pem = f"-----BEGIN PUBLIC KEY-----\n{r.json()['data']}\n-----END PUBLIC KEY-----"
        pub = serialization.load_pem_public_key(pem.encode())

        user, pw = read_credential(self.uis_target)
        enc_pw = base64.b64encode(pub.encrypt(pw.encode(), padding.PKCS1v15())).decode()

        # SINGLE attempt — repeated failures trigger university-side captcha.
        r = self._req("POST", f"https://{ID_HOST}/idp/authn/authExecute", tries=1, json={
            "authModuleCode": "userAndPwd", "authChainCode": chain,
            "entityId": entity, "requestType": "chain_type", "lck": lck,
            "authPara": {"loginName": user, "password": enc_pw, "verifyCode": ""},
        })
        d = r.json()
        msg = d.get("message") or ""
        token = d.get("loginToken") or (d.get("data") or {}).get("loginToken")
        if not token:
            if CAPTCHA_MARKER in msg:
                raise CaptchaRequired(
                    "UIS requires a captcha. Open https://id.fudan.edu.cn in a browser, "
                    "log in manually once, then retry.")
            if BAD_CRED_MARKER in msg:
                raise CredentialsInvalid(f"UIS rejected credentials: {msg}")
            raise DantaError(f"UIS login failed: {msg or json.dumps(d, ensure_ascii=False)[:200]}")
        self._log("UIS auth ok:", msg)

        r = self._req("POST", f"https://{ID_HOST}/idp/authCenter/authnEngine",
                      data={"loginToken": token})
        tgt = self._extract_ticket_target(r.text)
        if not tgt:
            raise DantaError("could not extract CAS ticket from authnEngine response")
        self._redeem(tgt)

    def _redeem(self, target_url: str) -> None:
        """Exchange a CAS ticket for a WebVPN session cookie."""
        self._req("GET", target_url, allow_redirects=True)
        if not any(c.name == "wengine_vpn_ticketwebvpn_fudan_edu_cn"
                   for c in self.s.cookies):
            raise DantaError("WebVPN ticket redemption did not yield a session cookie")
        self._log("webvpn session established")

    # ---------- fduhole auth ----------
    def ensure_token(self, force=False) -> str:
        if self.token and not force:
            return self.token
        self.ensure_webvpn()
        user, pw = read_credential(self.hole_target)
        r = self._req("POST", webvpn_url(f"{AUTH_BASE}/login"),
                      json={"email": user, "password": pw})
        if "json" not in r.headers.get("content-type", ""):
            # WebVPN bounced us to its login page -> session is stale. Re-auth once.
            self._log("login returned HTML, refreshing WebVPN session")
            self.ensure_webvpn(force=True)
            r = self._req("POST", webvpn_url(f"{AUTH_BASE}/login"),
                          json={"email": user, "password": pw})
            if "json" not in r.headers.get("content-type", ""):
                raise DantaError(
                    f"login still returns non-JSON (HTTP {r.status_code}) after "
                    f"re-establishing WebVPN")
        d = r.json()
        tok = d.get("access")
        if not tok:
            raise CredentialsInvalid(
                f"DanTa login failed (HTTP {r.status_code}): "
                f"{d.get('message') or json.dumps(d, ensure_ascii=False)[:200]}")
        self.token = tok
        self._save_state()
        self._log("fduhole token acquired")
        return tok

    def api(self, method: str, url: str, **kw):
        """Authenticated API call through WebVPN, with one auto-reauth retry."""
        tok = self.ensure_token()
        headers = {"Authorization": f"Bearer {tok}", **kw.pop("headers", {})}
        r = self._req(method, webvpn_url(url), headers=headers, **kw)
        if r.status_code == 401:
            self._log("401 -> refreshing token")
            self.ensure_webvpn(force=True)
            tok = self.ensure_token(force=True)
            headers["Authorization"] = f"Bearer {tok}"
            r = self._req(method, webvpn_url(url), headers=headers, **kw)
        if "json" not in r.headers.get("content-type", ""):
            raise DantaError(f"non-JSON response (HTTP {r.status_code}) from {url[:80]}")
        if r.status_code >= 400:
            d = r.json()
            raise DantaError(f"HTTP {r.status_code}: "
                             f"{d.get('message') or json.dumps(d, ensure_ascii=False)[:200]}")
        return r.json()

    # ---------- high level: 旦克 course reviews ----------
    def search_courses(self, keyword: str, page=1, page_size=10):
        return self.api("GET", f"{DANKE_BASE}/v3/course_groups/search",
                        params={"query": keyword, "page": page, "page_size": page_size})

    def course_group(self, group_id: int):
        return self.api("GET", f"{DANKE_BASE}/v3/course_groups/{group_id}")

    def course_reviews(self, course_id: int):
        return self.api("GET", f"{DANKE_BASE}/courses/{course_id}/reviews")

    # ---------- high level: 树洞 forum ----------
    def divisions(self):
        return self.api("GET", f"{FORUM_BASE}/divisions")

    def list_holes(self, division_id=1, length=10, start_time=None):
        p = {"division_id": division_id, "length": length}
        if start_time:
            p["start_time"] = start_time
        return self.api("GET", f"{FORUM_BASE}/holes", params=p)

    def hole(self, hole_id: int):
        return self.api("GET", f"{FORUM_BASE}/holes/{hole_id}")

    def floors(self, hole_id: int, start=0, length=50):
        return self.api("GET", f"{FORUM_BASE}/floors",
                        params={"hole_id": hole_id, "start_floor": start, "length": length})

    def search_floors(self, keyword: str, start=0, length=30):
        return self.api("GET", f"{FORUM_BASE}/floors/search",
                        params={"search": keyword, "start_floor": start, "length": length})

    def me(self):
        return self.api("GET", f"{FORUM_BASE}/users/me")
