import re
p="/home/ly/Cloudra-mechanism-agent/ts/ts_0042/jobs/declaration_0002/irc/irc.log"
L=open(p).read().split("\n")
for i,l in enumerate(L):
    if "Input orientation:" in l or "Standard orientation:" in l:
        j=i+5; atoms=[]
        while j<len(L) and re.match(r"\s*-+\s*$",L[j])==None:
            q=L[j].split()
            if len(q)==6: atoms.append(int(q[1]))
            j+=1
        print(i+1,l.strip()[:20],len(atoms),atoms)
