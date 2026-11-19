import pytest
from decimal import Decimal as D
from app.errors import DomainError
from app.pipeline import run
from app.normalize import instant
from app.modules.m3_integrate.rules import integrate
def point(t,qin,qout=0):return dict(station='S',time=instant('2026-11-16T'+t+':00Z'),inflow=D(qin),outflow=D(qout),level=D(101))

def test_trapezoid():
    x,g=integrate([point('00:00','1'),point('01:00','3')],D(2));assert x[0]['in_m3']==7200

def test_gap_no_interpolation():
    # TRAP-13
    x,g=integrate([point('00:00','1'),point('04:00','3')],D(2));assert x==[] and g[0]['hours']==4

def test_out_of_order():
    x,g=integrate([point('01:00','3'),point('00:00','1')],D(2));assert x[0]['in_m3']==7200

def test_gap_boundary_accepted():
    assert len(integrate([point('00:00','1'),point('02:00','1')],D(2))[0])==1

def test_real_gaps(raw):
    assert len(run(raw,stop=3,persist=False)['gaps'])>=1

def test_real_flow_positive(raw):
    assert all(D(x['in_m3'])>=0 for x in run(raw,stop=3,persist=False)['flows'])

def test_real_late_point_retained(raw):
    # TRAP-13
    x=run(raw,stop=3,persist=False);assert sum(r.get('arrival')=='迟到' for r in x['records'])>=1
    assert len(x['flows'])>=30

