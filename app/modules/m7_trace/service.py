from .rules import trace
def execute(ctx):
    ctx['audit']=trace(ctx['records'],ctx['quarantine'],ctx['input_count'],ctx['flows'],ctx['budgets'])
    rows=[{'station':k,'time':v} for k,v in sorted(ctx['audit']['watermarks'].items())]
    ctx['stages'].append({'title':'重算水位','rows':rows,'metrics':{'采信':len(ctx['records']),'隔离':len(ctx['quarantine']),'缺口':len(ctx['gaps']),'迟到测次':sum(r.get('arrival')=='迟到' for r in ctx['records'])}});return ctx
