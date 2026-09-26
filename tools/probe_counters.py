import subprocess

cmds = [
    ("Counter sets:", "(Get-Counter -ListSet 'GPU*' -ErrorAction SilentlyContinue).CounterSetName"),
    ("Dedicated paths:", "(Get-Counter -ListSet 'GPU*' -ErrorAction SilentlyContinue).Paths | Where-Object { $_ -match 'Dedicated' } | Select-Object -First 8"),
    ("Local/Shared paths:", "(Get-Counter -ListSet 'GPU*' -ErrorAction SilentlyContinue).Paths | Where-Object { $_ -match 'Local Usage|Shared Usage' } | Select-Object -First 8"),
]

for label, c in cmds:
    r = subprocess.run(['powershell', '-NoProfile', '-Command', c],
                       capture_output=True, text=True, timeout=30)
    print('=' * 60)
    print(label)
    print('=' * 60)
    out = r.stdout.strip()
    print(out if out else ('ERR: ' + r.stderr.strip()[:300]))
    print()
