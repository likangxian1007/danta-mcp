"""Store DanTa credentials in the OS credential store.

Usage:
    python setup_credentials.py            # interactive
    python setup_credentials.py --check    # verify what's stored

Backends:
    Windows        -> Credential Manager (DPAPI)
    macOS / Linux  -> `keyring` package (pip install keyring)
    Any platform   -> environment variables (see README)

Copyright (C) 2026  danta-mcp contributors
This program is free software under the GNU GPL v3 or later.
See <https://www.gnu.org/licenses/gpl-3.0.html>.
"""
import getpass
import io
import os
import subprocess
import sys
from pathlib import Path

# Windows consoles default to GBK; force UTF-8 so ✅/❌ and Chinese don't crash.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

TARGETS = {
    "DanTaMCP_UIS": ("复旦 UIS 统一身份认证", "Fudan UIS", "学号 / student ID"),
    "DanTaMCP_Hole": ("旦挞/树洞账号", "DanTa / Tree Hole", "邮箱 / email"),
}

_PS_WRITE = r'''
$sig=@"
using System;using System.Runtime.InteropServices;
public class CW{
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)]
 public struct CREDENTIAL{public UInt32 Flags;public UInt32 Type;public IntPtr TargetName;public IntPtr Comment;public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;public UInt32 CredentialBlobSize;public IntPtr CredentialBlob;public UInt32 Persist;public UInt32 AttributeCount;public IntPtr Attributes;public IntPtr TargetAlias;public IntPtr UserName;}
 [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
 public static extern bool CredWriteW([In] ref CREDENTIAL c,[In] UInt32 f);
}
"@
Add-Type -TypeDefinition $sig -ErrorAction SilentlyContinue
$blob=[System.Text.Encoding]::Unicode.GetBytes($env:DT_PASS)
$c=New-Object CW+CREDENTIAL
$c.Flags=0;$c.Type=1;$c.Persist=2
$c.TargetName=[Runtime.InteropServices.Marshal]::StringToCoTaskMemUni($env:DT_TARGET)
$c.UserName=[Runtime.InteropServices.Marshal]::StringToCoTaskMemUni($env:DT_USER)
$c.CredentialBlob=[Runtime.InteropServices.Marshal]::AllocCoTaskMem($blob.Length)
[Runtime.InteropServices.Marshal]::Copy($blob,0,$c.CredentialBlob,$blob.Length)
$c.CredentialBlobSize=$blob.Length
if([CW]::CredWriteW([ref]$c,0)){Write-Output "OK"}else{Write-Output "FAIL"}
'''


def store(target: str, user: str, password: str) -> bool:
    if sys.platform == "win32":
        env = dict(os.environ, DT_TARGET=target, DT_USER=user, DT_PASS=password)
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-Command", _PS_WRITE],
                           capture_output=True, text=True, env=env)
        return "OK" in (r.stdout or "")
    try:
        import keyring
        keyring.set_password(target, user, password)
        # Remember which username belongs to this target.
        keyring.set_password(target, "__user__", user)
        return True
    except ImportError:
        print("  ⚠️  需要 keyring: pip install keyring")
        print("      or use environment variables instead (see README).")
        return False
    except Exception as e:
        print(f"  ⚠️  {e}")
        return False


def main():
    if "--check" in sys.argv:
        from danta_client import read_credential
        ok = True
        for t in TARGETS:
            try:
                u, p = read_credential(t)
                print(f"  ✅ {t}: {u} ({len(p)} chars)")
            except Exception as e:
                ok = False
                print(f"  ❌ {t}: {str(e).splitlines()[0]}")
        sys.exit(0 if ok else 1)

    print("配置旦挞 MCP 凭据 / Configure DanTa MCP credentials")
    print("存入系统凭据库，不会明文落盘 / stored in the OS credential store\n")
    for target, (zh, en, hint) in TARGETS.items():
        print(f"— {zh} / {en}")
        user = input(f"  用户名 / username ({hint}): ").strip()
        if not user:
            print("  跳过 / skipped\n")
            continue
        pw = getpass.getpass("  密码 / password (hidden): ")
        if not pw:
            print("  跳过 / skipped\n")
            continue
        print("  " + ("✅ 已保存 / saved" if store(target, user, pw)
                      else "❌ 失败 / failed") + "\n")
    print("完成 / done. 验证 / verify:  python setup_credentials.py --check")


if __name__ == "__main__":
    main()
