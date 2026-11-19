import pytest
from decimal import Decimal as D
from app.errors import DomainError
from app.pipeline import run
from app.normalize import instant
from app.modules.m1_receive.rules import receive
from app.config import SAMPLES

def test_legacy_encoding():
    # TRAP-01
    assert receive((SAMPLES/'legacy.csv').read_bytes())['encoding']=='gb18030'

def test_real_count(raw):
    assert receive(raw)['input_count']==47

def test_real_short_row(raw):
    assert receive(raw)['quarantine'][0]['code']=='COLUMN_COUNT'

def test_empty():
    with pytest.raises(DomainError):receive(b'')

def test_header():
    with pytest.raises(DomainError):receive(b'bad,header\n1,2')

def test_blank():
    with pytest.raises(DomainError,match='仅含空行'):receive(b' \n')

def test_real_id(raw):
    assert receive(raw)['records'][0]['id']=='00001'

