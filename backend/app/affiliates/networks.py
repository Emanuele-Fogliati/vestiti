"""Affiliate network abstraction.

Every outbound "Buy" or "Rent" goes through /api/go/... which logs the click and then
redirects to the URL built here. If the network's publisher id is not configured, the
link goes out untracked (no commission) and the click row says tracked=false, so the
admin dashboard shows exactly how much traffic is being given away.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from app.config import Settings


@dataclass
class Outbound:
    url: str
    tracked: bool
    network: str


def _with_params(url: str, params: dict) -> str:
    u = urlparse(url)
    q = dict(parse_qsl(u.query, keep_blank_values=True))
    q.update({k: v for k, v in params.items() if v})
    return urlunparse(u._replace(query=urlencode(q)))


class Network:
    key = "direct"

    def __init__(self, settings: Settings):
        self.s = settings

    def configured(self) -> bool:
        return False

    def build(self, url: str, click_id: str, program_id: str | None = None) -> Outbound:
        return Outbound(url, False, self.key)


class Direct(Network):
    key = "direct"


class Amazon(Network):
    """Amazon Associates: append ?tag=<associate tag>. ascsubtag carries our click id."""

    key = "amazon"

    def configured(self) -> bool:
        return bool(self.s.amazon_associate_tag)

    def build(self, url, click_id, program_id=None):
        if not self.configured():
            return Outbound(url, False, self.key)
        return Outbound(_with_params(url, {"tag": self.s.amazon_associate_tag,
                                           "ascsubtag": click_id}), True, self.key)


class Awin(Network):
    """Awin deep link: https://www.awin1.com/cread.php?awinmid=<merchant>&awinaffid=<publisher>
    &clickref=<our click id>&ued=<encoded destination>"""

    key = "awin"

    def configured(self) -> bool:
        return bool(self.s.awin_publisher_id)

    def build(self, url, click_id, program_id=None):
        if not self.configured() or not program_id:
            return Outbound(url, False, self.key)
        link = ("https://www.awin1.com/cread.php?awinmid=" + quote(str(program_id))
                + "&awinaffid=" + quote(self.s.awin_publisher_id)
                + "&clickref=" + quote(click_id) + "&ued=" + quote(url, safe=""))
        return Outbound(link, True, self.key)


class Impact(Network):
    """Impact feeds already ship tracking URLs (Product URL); we add subId1 = click id."""

    key = "impact"

    def configured(self) -> bool:
        return bool(self.s.impact_account_sid)

    def build(self, url, click_id, program_id=None):
        if not self.configured():
            return Outbound(url, False, self.key)
        return Outbound(_with_params(url, {"subId1": click_id}), True, self.key)


class CJ(Network):
    """CJ deep link: https://www.anrdoezrs.net/links/<publisher id>/type/dlg/sid/<click>/<url>"""

    key = "cj"

    def configured(self) -> bool:
        return bool(self.s.cj_publisher_id)

    def build(self, url, click_id, program_id=None):
        if not self.configured():
            return Outbound(url, False, self.key)
        return Outbound(f"https://www.anrdoezrs.net/links/{self.s.cj_publisher_id}/type/dlg/sid/"
                        f"{quote(click_id)}/{url}", True, self.key)


class AvantLink(Network):
    """AvantLink: https://www.avantlink.com/click.php?tt=cl&mi=<merchant>&pw=<affiliate>
    &ctc=<click>&url=<encoded>"""

    key = "avantlink"

    def configured(self) -> bool:
        return bool(self.s.avantlink_affiliate_id)

    def build(self, url, click_id, program_id=None):
        if not self.configured() or not program_id:
            return Outbound(url, False, self.key)
        return Outbound("https://www.avantlink.com/click.php?tt=cl&mi=" + quote(str(program_id))
                        + "&pw=" + quote(self.s.avantlink_affiliate_id) + "&ctc="
                        + quote(click_id) + "&url=" + quote(url, safe=""), True, self.key)


REGISTRY = {cls.key: cls for cls in (Direct, Amazon, Awin, Impact, CJ, AvantLink)}


def network_for(key: str, settings: Settings) -> Network:
    return REGISTRY.get(key, Direct)(settings)


def status(settings: Settings) -> list[dict]:
    return [{"network": k, "configured": cls(settings).configured()} for k, cls in REGISTRY.items()
            if k != "direct"]
