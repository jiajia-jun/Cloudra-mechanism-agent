E={}
E['ery_min']=-598.229013613; E['ery_ts']=-598.208585697
E['thr_min']=-598.231556225; E['thr_ts']=-598.208059052
C=627.509474
for tag,(a,b) in {'erythro syn':('ery_ts','ery_min'),'threo syn':('thr_ts','thr_min')}.items():
    d=E[a]-E[b]
    print(tag,'dE = %.9f Ha = %.3f kcal/mol'%(d,d*C))
print('min difference (threo - erythro) = %.3f kcal/mol (NOT a barrier, recorded only for bookkeeping)'%((E['thr_min']-E['ery_min'])*C))
