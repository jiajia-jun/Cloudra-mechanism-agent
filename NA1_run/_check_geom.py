import math, sys

def parse_xyz(path):
    lines = open(path).read().split('\n')
    i = 0
    frames = []
    while i < len(lines):
        s = lines[i].strip()
        if s.isdigit():
            n = int(s)
            xyz = lines[i+3:i+3+n]
            ats = []
            for l in xyz:
                p = l.split()
                if len(p) >= 4:
                    ats.append((p[0], float(p[1]), float(p[2]), float(p[3])))
            frames.append(ats)
            i = i + 3 + n
        else:
            i += 1
    return frames

def d(a, b):
    return math.dist(a[1:], b[1:])

def report(path, label):
    frames = parse_xyz(path)
    last = frames[-1]
    print(f"--- {label}: {len(frames)} frames, last has {len(last)} atoms ---")
    # atom indices 0-based -> atom1(C enolate a)=idx0, atom8(C carbonyl)=idx7, atom9(O)=idx8
    print(f"  C1-C8 = {d(last[0], last[7]):.3f} A")
    print(f"  C1-C2 = {d(last[0], last[1]):.3f} A")
    print(f"  C8-O9 = {d(last[7], last[8]):.3f} A")

if __name__ == '__main__':
    report(sys.argv[1], sys.argv[2])
