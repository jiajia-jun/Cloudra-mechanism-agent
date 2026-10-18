import re, sys
log = sys.argv[1]
lines = open(log).read().splitlines()
e = None
out = []
for ln in lines:
    if 'SCF Done' in ln:
        m = re.search(r'=\s*(-?\d+\.\d+)', ln)
        if m: e = float(m.group(1))
    m = re.match(r'\s*!\s*R\d+\s+R\((\d+),(\d+)\)\s+([-\d.]+)\s+-DE/DX', ln)
    if m:
        out.append((m.group(1)+'-'+m.group(2), float(m.group(3)), e))
print('coord   value      E/Ha')
for c, v, ee in out:
    print('%-7s %8.4f  %s' % (c, v, ee))