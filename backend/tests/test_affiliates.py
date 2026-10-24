from urllib.parse import parse_qs, urlparse

from app.affiliates.networks import network_for, status
from app.config import Settings


def test_unconfigured_networks_are_untracked():
    s = Settings()
    for k in ("amazon", "awin", "impact", "cj", "avantlink"):
        out = network_for(k, s).build("https://shop.example/p?x=1", "click1", "42")
        assert out.url == "https://shop.example/p?x=1" and out.tracked is False
    assert all(not row["configured"] for row in status(s))


def test_amazon_tag():
    out = network_for("amazon", Settings(amazon_associate_tag="me-21")).build("https://www.amazon.de/dp/B0?th=1", "c9")
    q = parse_qs(urlparse(out.url).query)
    assert out.tracked and q["tag"] == ["me-21"] and q["ascsubtag"] == ["c9"] and q["th"] == ["1"]


def test_awin_deeplink_encodes_destination():
    out = network_for("awin", Settings(awin_publisher_id="555")).build("https://shop.example/a?b=1&c=2", "c1", "123")
    q = parse_qs(urlparse(out.url).query)
    assert out.url.startswith("https://www.awin1.com/cread.php")
    assert q["awinmid"] == ["123"] and q["awinaffid"] == ["555"] and q["clickref"] == ["c1"]
    assert q["ued"] == ["https://shop.example/a?b=1&c=2"]


def test_awin_without_merchant_id_is_untracked():
    assert network_for("awin", Settings(awin_publisher_id="555")).build("https://x.example", "c1").tracked is False


def test_impact_and_cj():
    assert "subId1=c1" in network_for("impact", Settings(impact_account_sid="S")).build("https://imp.example/p", "c1").url
    cj = network_for("cj", Settings(cj_publisher_id="777")).build("https://shop.example/p", "c1")
    assert cj.url == "https://www.anrdoezrs.net/links/777/type/dlg/sid/c1/https://shop.example/p"


def test_unknown_network_is_direct():
    assert network_for("nope", Settings()).key == "direct"
