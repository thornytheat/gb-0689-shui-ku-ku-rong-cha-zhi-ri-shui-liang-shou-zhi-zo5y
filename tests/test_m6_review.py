import pytest
from decimal import Decimal as D
from app.errors import DomainError
from app.pipeline import run
from app.normalize import instant
from app.modules.m6_review.rules import evaluate

def test_incomplete_priority():
    assert evaluate([{'state':'缺测','residual':D(999)}],D(1))[0]['code']=='GAP'

def test_threshold_included():
    assert evaluate([{'state':'完整','residual':D(500)}],D(500))[0]['state']=='通过'

def test_negative_residual():
    assert evaluate([{'state':'完整','residual':D(-501)}],D(500))[0]['code']=='LIMIT'

def test_zero_residual():
    assert evaluate([{'state':'完整','residual':D(0)}],D(0))[0]['state']=='通过'

def test_real_review_present(raw):
    assert len(run(raw,stop=6,persist=False)['review_rows'])>=2

def test_real_missing_blocks(raw):
    assert any(x['state']=='待补测' for x in run(raw,stop=6,persist=False)['review_rows'])

def test_real_reasons(raw):
    assert set(x['code'] for x in run(raw,stop=6,persist=False)['review_rows'])<=set(['PASS','GAP','LIMIT'])

