import pytest
from decimal import Decimal as D
from app.errors import DomainError
from app.pipeline import run
from app.normalize import instant
from app.modules.m5_budget.rules import day_budget
from app.modules.m4_storage.service import level_to_volume
from app.modules.m3_integrate.rules import integrate
C=[(D(100),D(0)),(D(102),D(30000))]
def p(time,level):return dict(station='S',time=instant(time),inflow=D(1),outflow=D(0),level=D(level))

def test_midnight_split():
    # TRAP-23
    x=integrate([p('2026-12-31T23:00:00+08:00','100'),p('2027-01-01T01:00:00+08:00','102')],D(2))[0];days=day_budget(x,C,level_to_volume);assert len(days)==2 and [r['in_m3'] for r in days]==[3600,3600]

def test_storage_conservation():
    x=integrate([p('2026-11-16T23:00:00+08:00','100'),p('2026-11-17T01:00:00+08:00','102')],D(2))[0];assert sum(r['storage_change'] for r in day_budget(x,C,level_to_volume))==30000

def test_partial_day_flagged():
    x=integrate([p('2026-11-16T00:00:00Z','100'),p('2026-11-16T01:00:00Z','101')],D(2))[0];assert day_budget(x,C,level_to_volume)[0]['state']=='缺测'

def test_empty():
    assert day_budget([],C,level_to_volume)==[]

def test_real_day_count(raw):
    assert len(run(raw,stop=5,persist=False)['budgets'])>=2

def test_real_missing_day(raw):
    assert any(x['state']=='缺测' for x in run(raw,stop=5,persist=False)['budgets'])

def test_real_daily_integral(raw):
    x=run(raw,stop=5,persist=False);assert abs(sum(D(y['in_m3']) for y in x['budgets'])-sum(D(y['in_m3']) for y in x['flows']))<D('.000000001')

