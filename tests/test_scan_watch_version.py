import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (scan_watch.py sits one level up) work regardless of the CWD this test is invoked from

import subprocess
import sys

result = subprocess.run(
    [sys.executable, '../scan_watch.py', '--version'],
    capture_output=True, text=True,
)
print("exit code:", result.returncode)
print("stdout:", result.stdout.strip())
print("stderr:", result.stderr.strip())
assert result.returncode == 0
assert result.stdout.strip() == 'scan_watch.py 1.7.1', f"unexpected --version output: {result.stdout!r}"
print("PASS")
