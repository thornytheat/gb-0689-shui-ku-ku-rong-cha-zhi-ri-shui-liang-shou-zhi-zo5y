from collections import defaultdict
from decimal import Decimal as D
def integrate(rows,max_gap):
    stations=defaultdict(list)
    for row in rows:stations[row['station']].append(row)
    parts=[];gaps=[]
    for station,items in sorted(stations.items()):
        items=sorted(items,key=lambda r:r['time'])
        for a,b in zip(items,items[1:]):
            seconds=D(str((b['time']-a['time']).total_seconds()))
            if seconds>max_gap*3600:
                gaps.append({'station':station,'start':a['time'],'end':b['time'],'hours':seconds/3600,'code':'GAP','state':'缺测'});continue
            parts.append({'station':station,'start':a['time'],'end':b['time'],'in_m3':(a['inflow']+b['inflow'])/2*seconds,'out_m3':(a['outflow']+b['outflow'])/2*seconds,'left':a,'right':b})
    return parts,gaps
