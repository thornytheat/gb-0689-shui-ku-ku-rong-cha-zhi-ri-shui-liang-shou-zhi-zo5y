from .rules import day_budget
from app.modules.m4_storage.service import level_to_volume
def execute(ctx):
    rows=day_budget(ctx['flows'],ctx['curve'],level_to_volume);ctx['budgets']=rows
    ctx['stages'].append({'title':'日水量收支','rows':rows,'metrics':{'日账':len(rows),'缺测日':sum(x['state']=='缺测' for x in rows),'收支差 m³':str(sum((x['residual'] for x in rows),0))}});return ctx
