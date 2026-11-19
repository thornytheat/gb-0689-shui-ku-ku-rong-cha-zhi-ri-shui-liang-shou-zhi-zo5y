from datetime import datetime,timedelta,timezone
from decimal import Decimal as D
from collections import defaultdict
# Public pure interpolation is deliberately passed in by the service.
def day_budget(flows,curve,interpolate):
    zone=timezone(timedelta(hours=8));buckets=defaultdict(lambda:{'in_m3':D(0),'out_m3':D(0),'storage_change':D(0),'coverage_hours':D(0)})
    for part in flows:
        left,right=part['left'],part['right'];start,end=part['start'],part['end'];duration=D(str((end-start).total_seconds()));cursor=start
        def at(t,key):return left[key]+(right[key]-left[key])*D(str((t-start).total_seconds()))/duration
        while cursor<end:
            local=cursor.astimezone(zone);midnight=datetime.combine(local.date()+timedelta(days=1),datetime.min.time(),zone);stop=min(end,midnight);seconds=D(str((stop-cursor).total_seconds()))
            b=buckets[(part['station'],local.date().isoformat())]
            b['in_m3']+=(at(cursor,'inflow')+at(stop,'inflow'))/2*seconds
            b['out_m3']+=(at(cursor,'outflow')+at(stop,'outflow'))/2*seconds
            b['storage_change']+=interpolate(at(stop,'level'),curve)-interpolate(at(cursor,'level'),curve)
            b['coverage_hours']+=seconds/3600;cursor=stop
    result=[]
    for (station,day),values in sorted(buckets.items()):
        result.append({'station':station,'date':day,**values,'residual':values['storage_change']-values['in_m3']+values['out_m3'],'state':'完整' if values['coverage_hours']==24 else '缺测'})
    return result
