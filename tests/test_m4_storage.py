import pytest
from decimal import Decimal as D
from app.errors import DomainError
from app.pipeline import run
from app.normalize import instant
from app.modules.m4_storage.rules import interpolate
C=[(D(100),D(0)),(D(102),D(30000)),(D(105),D(100000))]

def test_linear_midpoint():
    assert interpolate(D(101),C)==15000

def test_knot_exact():
    assert interpolate(D(102),C)==30000

def test_no_extrapolation():
    with pytest.raises(DomainError):interpolate(D(99),C)

def test_decimal_precision():
    # TRAP-10
    assert interpolate(D('100.1'),C)==D(1500)

def test_real_storage_count(raw):
    x=run(raw,stop=4,persist=False);assert len(x['storage'])==len(x['records'])

def test_real_volume_range(raw):
    assert all(0<=D(x['volume'])<=220000 for x in run(raw,stop=4,persist=False)['storage'])

def test_real_formula(raw):
    x=run(raw,stop=4,persist=False)['storage'][0];assert D(x['volume'])==(D(x['level'])-100)*15000

