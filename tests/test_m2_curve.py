import pytest
from decimal import Decimal as D
from app.errors import DomainError
from app.pipeline import run
from app.normalize import instant
from app.modules.m2_curve.rules import validate_curve,normalize,select
CURVE=validate_curve([['100','0'],['102','30000'],['105','100000']])
def row(**kw):
 x=dict(id='1',station='甲库',time='2026-11-16T00:00:00Z',level='101',inflow='1',outflow='0',flow_unit='m3/s',version='1',_line=2);x.update(kw);return x

def test_fullwidth():
    # TRAP-06
    assert normalize(row(level='１０１'),CURVE)['level']==101

def test_unit_conversion():
    # TRAP-15
    assert normalize(row(inflow='1,000',flow_unit='L/s'),CURVE)['inflow']==1

def test_sentinel():
    # TRAP-07
    with pytest.raises(DomainError):normalize(row(level='未知'),CURVE)

def test_curve_monotonic():
    with pytest.raises(DomainError):validate_curve([[100,10],[101,9]])

def test_real_conflict(raw):
    # TRAP-14
    assert sum(x['code']=='CONFLICT' for x in run(raw,stop=2,persist=False)['quarantine'])==2

def test_real_curve(raw):
    assert len(run(raw,stop=2,persist=False)['curve'])==4

def test_real_valid_units(raw):
    assert all(x['flow_unit']=='m3/s' for x in run(raw,stop=2,persist=False)['records'])

