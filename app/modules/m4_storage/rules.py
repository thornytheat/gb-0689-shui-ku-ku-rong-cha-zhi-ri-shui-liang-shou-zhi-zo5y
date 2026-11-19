from app.errors import DomainError
def interpolate(level,curve):
    if not curve[0][0]<=level<=curve[-1][0]:raise DomainError('RANGE','水位超出曲线范围')
    for (ha,va),(hb,vb) in zip(curve,curve[1:]):
        if ha<=level<=hb:return va+(vb-va)*(level-ha)/(hb-ha)
    raise DomainError('CURVE','曲线没有覆盖水位')
def storage(rows,curve):return [{**row,'volume':interpolate(row['level'],curve)} for row in rows]
