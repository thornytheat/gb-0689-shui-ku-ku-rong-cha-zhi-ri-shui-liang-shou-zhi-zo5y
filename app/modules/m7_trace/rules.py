from app.errors import DomainError
from decimal import Decimal as D
from collections import defaultdict
def trace(records,bad,total,flows,budgets):
    if len(records)+len(bad)!=total:raise DomainError('INCOMPLETE','测次行数不平衡')
    in_total=sum((r['in_m3'] for r in flows),D(0));daily=sum((r['in_m3'] for r in budgets),D(0))
    # Decimal divisions may differ in their final 1e-20 digit, well below 1 microlitre.
    if abs(in_total-daily)>D('.000000001'):raise DomainError('INCOMPLETE','日切积分不守恒')
    marks={}
    for row in records:marks[row['station']]=max(marks.get(row['station'],row['time']),row['time'])
    return {'input':total,'retained':len(records),'isolated':len(bad),'in_m3':in_total,'day_in_m3':daily,'watermarks':marks}
