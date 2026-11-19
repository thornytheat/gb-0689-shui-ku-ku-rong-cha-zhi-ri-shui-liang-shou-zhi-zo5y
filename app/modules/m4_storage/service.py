from .rules import storage
def execute(ctx):
    rows=storage(ctx['records'],ctx['curve']);ctx['storage']=rows
    ctx['stages'].append({'title':'库容换算','rows':rows,'metrics':{'换算测次':len(rows),'最小库容 m³':str(min((x['volume'] for x in rows),default=0)),'最大库容 m³':str(max((x['volume'] for x in rows),default=0))}});return ctx

from .rules import interpolate
def level_to_volume(level,curve):return interpolate(level,curve)
