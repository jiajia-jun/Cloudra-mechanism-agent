import math, sys
def load(p):
    L=[l.split() for l in open(p).read().splitlines()[2:]]
    return [(l[0],float(l[1]),float(l[2]),float(l[3])) for l in L]
def sub(a,b): return [a[i]-b[i] for i in range(3)]
def cross(a,b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def dih(p0,p1,p2,p3):
    b1=sub(p1,p0); b2=sub(p2,p1); b3=sub(p3,p2)
    n1=cross(b1,b2); n2=cross(b2,b3)
    m=cross(n1,[b2[i]/math.dist([0,0,0],b2) for i in range(3)])
    x=dot(n1,n2); y=dot(m,n2)
    return math.degrees(math.atan2(y,x))
for f in sys.argv[1:]:
    A=load(f); d=lambda i,j: math.dist(A[i-1][1:],A[j-1][1:])
    on = [i+1 for i in range(len(A)) if A[i][0]=='H' and d(i+1,3)<1.2]
    nn = [i+1 for i in range(len(A)) if A[i][0]=='H' and d(i+1,1)<1.2]
    ch = [i+1 for i in range(len(A)) if A[i][0]=='H' and d(i+1,2)<1.2]
    print(f.split('/')[-1], 'H_on_O', on, 'H_on_N', nn, 'H_on_C', ch)
    if nn: print('  dih(HN-N1-C2-O3) = %.1f' % dih(A[nn[0]-1][1:],A[0][1:],A[1][1:],A[2][1:]))
    if on: print('  dih(HO-O3-C2-N1) = %.1f' % dih(A[on[0]-1][1:],A[2][1:],A[1][1:],A[0][1:]))