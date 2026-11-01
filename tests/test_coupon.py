import pytest

from app.services.coupon import extract_coupon_code, valid_enroll_url


@pytest.mark.parametrize(("url", "expected"), [
    ("https://www.udemy.com/course/python/?couponCode=REAL%2BCODE&utm_source=x", "REAL+CODE"),
    ("https://udemy.com/course/python/?couponCode=FIRST&couponCode=SECOND", "FIRST"),
    ("https://www.udemy.com/course/python/?couponCode=", None),
    ("https://www.udemy.com/course/python/", None), (None, None),
    ("https://udemy.com.attacker.test/course/?couponCode=FAKE", None),
    ("javascript:alert(1)", None), ("http://www.udemy.com/?couponCode=CODE", None),
    ("https://www.udemy.com:1234/?couponCode=CODE", None),
    ("https://evil@www.udemy.com/?couponCode=CODE", None),
    ("https://[invalid/?couponCode=CODE", None),
])
def test_coupon_comes_only_from_valid_enroll_url(url, expected):
    assert extract_coupon_code(url) == expected


def test_enroll_rejects_untrusted_destinations():
    assert valid_enroll_url("https://other.test/course/") is None
    assert extract_coupon_code("https://udemy.com/?couponCode=" + "X" * 501) is None
