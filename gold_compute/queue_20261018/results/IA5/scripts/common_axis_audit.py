"""Read-only rotation audit; numpy only. Axes C2->C3 and C1->C4
both point central->terminal (nearly parallel, same viewing direction).
Reference y is C1->C2 projected normal to each axis; z=axis cross y.
atan2(H.z,H.y) is a proper-rotation/translation invariant pseudoscalar.
Each attached H is tracked without swapping. Unwrap continuous IRC frames.
Same signed increments on the two co-oriented axes = conrotation;
opposite signed increments = disrotation. Reflection flips both signs,
not their relative sign. Backbone-following reference removes rigid motion.
"""
import numpy as np,json,pathlib
root=pathlib.Path(__file__).resolve().parents[5]
# use explicit cwd project root when invoked there
base=pathlib.Path('ts/ts_0004/jobs/declaration_0006/irc')
def frames(p):
 l=p.read_text().splitlines();out=[];i=0
 while i<len(l):
  if not l[i].strip():i+=1;continue
  n=int(l[i]);out.append(np.array([[float(v) for v in s.split()[1:4]] for s in l[i+2:i+2+n]]));i+=n+2
 return out
def angle(x,c,a,h):
 u=(x[2]-x[1])/np.linalg.norm(x[2]-x[1])+(x[3]-x[0])/np.linalg.norm(x[3]-x[0]);u/=np.linalg.norm(u)
 y=x[1]-x[0];y=y-u*np.dot(y,u);y/=np.linalg.norm(y)
 z=np.cross(u,y);v=x[h]-x[c]
 return np.arctan2(np.dot(v,z),np.dot(v,y))
res={}
for label in ['F','B']:
 p=base/f'irc_IRC_{label}_trj.xyz';xs=frames(p)
 vals=np.array([[angle(x,2,1,6),angle(x,2,1,7),angle(x,3,0,8),angle(x,3,0,9)] for x in xs])
 deg=np.unwrap(vals,axis=0)*180/np.pi
 rows=[]
 for i,x in enumerate(xs):rows.append({'frame':i,'r34':float(np.linalg.norm(x[2]-x[3])),'angles_H7_H8_H9_H10':deg[i].tolist()})
 res[label]={'source':str(p),'count':len(xs),'first':rows[0],'last':rows[-1],'increments':(deg[-1]-deg[0]).tolist(),'rows':rows}
print(json.dumps(res,indent=2))
