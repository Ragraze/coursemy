from urllib.parse import parse_qs, urlsplit


def valid_enroll_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme == "https" and (host == "udemy.com" or host.endswith(".udemy.com")) and not parsed.username and parsed.port in (None, 443):
            return url
    except ValueError:
        pass
    return None


def extract_coupon_code(enroll_url: str | None) -> str | None:
    url = valid_enroll_url(enroll_url)
    if not url:
        return None
    code = parse_qs(urlsplit(url).query).get("couponCode", [""])[0].strip()
    return code if 0 < len(code) <= 500 else None
