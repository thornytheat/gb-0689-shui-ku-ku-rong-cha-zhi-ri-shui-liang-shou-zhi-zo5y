from .rules import integrate
from app.normalize import number
def execute(ctx):
    parts,gaps=integrate(ctx['records'],number(ctx['params']['max_gap_hours']));ctx['flows']=parts;ctx['gaps']=gaps
    ctx['stages'].append({'title':'流量积分','rows':parts,'metrics':{'有效段':len(parts),'缺口':len(gaps),'入库 m³':str(sum((x['in_m3'] for x in parts),0))}});return ctx
