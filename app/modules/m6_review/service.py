from .rules import evaluate
from app.normalize import number
def execute(ctx):
    rows=evaluate(ctx['budgets'],number(ctx['params']['tolerance_m3']));ctx['review_rows']=rows
    ctx['stages'].append({'title':'异常复核','rows':rows,'metrics':{'通过日':sum(r['state']=='通过' for r in rows),'待补测':sum(r['code']=='GAP' for r in rows),'超差日':sum(r['code']=='LIMIT' for r in rows)}});return ctx
