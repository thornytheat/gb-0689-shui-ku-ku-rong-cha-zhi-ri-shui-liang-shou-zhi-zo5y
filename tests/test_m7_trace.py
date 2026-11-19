import pytest
from decimal import Decimal as D
from app.errors import DomainError
from app.pipeline import run
from app.normalize import instant
from app.modules.m7_trace.rules import trace

def test_row_count_failure():
    with pytest.raises(DomainError):trace([],[],1,[],[])

def test_water_failure():
    with pytest.raises(DomainError):trace([],[],0,[{'in_m3':D(1)}],[])

def test_empty():
    assert trace([],[],0,[],[])['watermarks']=={}

def test_watermark_max():
    a=instant('2026-11-16T00:00:00Z');b=instant('2026-11-17T00:00:00Z');assert trace([{'station':'S','time':b},{'station':'S','time':a}],[],2,[],[])['watermarks']['S']==b

def test_real_row_balance(raw):
    x=run(raw,persist=False);assert x['audit']['input']==x['audit']['retained']+x['audit']['isolated']

def test_real_water_balance(raw):
    x=run(raw,persist=False);assert abs(D(x['audit']['in_m3'])-D(x['audit']['day_in_m3']))<D('.000000001')

def test_real_stable_id(raw,isolate):
    assert run(raw)['manifest']['run_id']==run(raw)['manifest']['run_id']

