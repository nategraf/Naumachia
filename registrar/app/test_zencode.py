import hypothesis
import pytest
import re
from .zencode import encode, decode

@pytest.mark.parametrize("input,encoded", [
    ("indigo", "indigo"),
    ("zebra", "z7aebra"),
    ("bang! bang!", "bangz21z20bangz21"),
    ("~!@#$%^&()", "z7ez21z40z23z24z25z5ez26z28z29"),
    ("San Francisco 49ers", "Sanz20Franciscoz2049ers"),
    ("Zero", "z5aero"),
    ("", ""),
])
def test_encode_decode(input, encoded):
    assert encode(input) == encoded
    assert decode(encoded) == input

@hypothesis.given(hypothesis.strategies.text())
def test_encode_decode_hypothesis(input):
    encoded = encode(input)
    assert re.fullmatch(r'[a-zA-Z0-9]*', encoded)
    assert decode(encoded) == input
