from .rules import validate_curve,normalize,select
from app.normalize import number
from app.errors import DomainError
from app.reasons import rejected
def execute(ctx):
    curve=validate_curve(ctx['params']['curve']);gap=number(ctx['params']['max_gap_hours']);tol=number(ctx['params']['tolerance_m3'])
    if gap<=0 or gap>24 or tol<0:raise DomainError('RANGE','缺口或容差参数无效')
    good=[]
    for row in ctx['records']:
        try:good.append(normalize(row,curve))
        except DomainError as exc:ctx['quarantine'].append(rejected(row,exc.code,exc.message))
    watermarks={}
    for row in good:
        old=watermarks.get(row['station'])
        row['arrival']='迟到' if old is not None and row['time']<old else '顺序'
        watermarks[row['station']]=max(old,row['time']) if old else row['time']
    good,bad=select(good);ctx['quarantine'].extend(bad);ctx['records']=good;ctx['curve']=curve
    ctx['stages'].append({'title':'曲线校核','rows':[{'level':h,'volume':v} for h,v in curve],'metrics':{'曲线点':len(curve),'有效测次':len(good),'最大缺口 h':str(gap)}});return ctx
