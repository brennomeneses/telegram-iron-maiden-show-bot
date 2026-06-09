"""
monitor.py – Iron Maiden Curitiba 2026
Stdlib only: tenta urllib com sessão de cookies; fallback para curl se disponível.
"""

import re
import gzip
import logging
import asyncio
import subprocess
import urllib.request
import urllib.error
from http.cookiejar import CookieJar
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

BUYTICKET_URL = (
    "https://buyticketbrasil.com/evento/ironmaiden-runforyourlivesworldtour2026"
    "?data=1793242799000"
    "&evento_local=1779374792451x659702685709631500"
    "&cidade=Curitiba"
)

LIVEPASS_BASE  = "https://www.livepass.com.br"
LIVEPASS_EVENT = "/event/iron-maiden-run-for-your-lives-world-tour-2026-cwb-arena-da-baixada-21684448/"
LIVEPASS_URL   = LIVEPASS_BASE + LIVEPASS_EVENT + "?promo_id=186816"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


# ──────────────────────────────────────────────────────────────────────────────
# Fetch helpers
# ──────────────────────────────────────────────────────────────────────────────

def _curl_fetch(url: str, referer: str = None, timeout: int = 45) -> str:
    """Usa curl como fallback — TLS fingerprint diferente, mais difícil de bloquear."""
    cmd = [
        "curl", "-sL",
        "--max-time", str(timeout),
        "--compressed",
        "-A", UA,
        "-H", "Accept-Language: pt-BR,pt;q=0.9",
        "-H", "Accept: text/html,application/xhtml+xml,*/*;q=0.8",
        "-H", "Upgrade-Insecure-Requests: 1",
    ]
    if referer:
        cmd += ["-H", f"Referer: {referer}"]
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, timeout=timeout + 5)
    if result.returncode != 0:
        raise RuntimeError(f"curl falhou: {result.stderr.decode()[:100]}")
    return result.stdout.decode("utf-8", errors="replace")


def _urllib_fetch(url: str, opener=None, extra_headers: dict = None, timeout: int = 45) -> str:
    """Fetch com urllib + CookieJar."""
    if opener is None:
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )
    req = urllib.request.Request(url, headers={**BASE_HEADERS, **(extra_headers or {})})
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def _fetch_livepass(timeout: int = 45) -> str:
    """
    Tenta urllib com sessão de 2 passos.
    Se receber 403, faz fallback para curl.
    """
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )

    # Passo 1: homepage para obter cookies
    try:
        _urllib_fetch(LIVEPASS_BASE, opener=opener, timeout=15)
        logger.debug("Livepass: cookies da homepage coletados")
    except Exception as e:
        logger.debug(f"Livepass: homepage ignorada ({e})")

    # Passo 2: página do evento
    try:
        html = _urllib_fetch(
            LIVEPASS_URL,
            opener=opener,
            extra_headers={"Referer": LIVEPASS_BASE + "/", "Sec-Fetch-Site": "same-origin"},
            timeout=timeout,
        )
        logger.info("Livepass: carregado via urllib")
        return html
    except urllib.error.HTTPError as e:
        if e.code == 403:
            logger.warning("Livepass: urllib 403, tentando curl...")
            return _curl_fetch(LIVEPASS_URL, referer=LIVEPASS_BASE + "/", timeout=timeout)
        raise


def _fetch_buyticket(timeout: int = 30) -> str:
    """BuyTicket: urllib com fallback para curl."""
    try:
        html = _urllib_fetch(BUYTICKET_URL, timeout=timeout)
        logger.info("BuyTicket: carregado via urllib")
        return html
    except urllib.error.HTTPError as e:
        if e.code == 403:
            logger.warning("BuyTicket: urllib 403, tentando curl...")
            return _curl_fetch(BUYTICKET_URL, timeout=timeout)
        raise


# ──────────────────────────────────────────────────────────────────────────────
# Parsers
# ──────────────────────────────────────────────────────────────────────────────

class LivepassParser(HTMLParser):
    """
    Seletores data-qa exatos do HTML real da Livepass:
      <div data-qa="price-category">
        <div class="pc-list-category"><span>SETOR</span></div>
        <div data-qa="tickettype" data-tt-name="INTEIRA">
          <div data-qa="tickettypeItem-price">R$ 890,00</div>
          <div data-qa="ticket-type-availability-hint">Indisponível no momento</div>
        </div>
      </div>
    Sem hint = Disponível.
    """

    def __init__(self):
        super().__init__()
        self.tickets = []
        self._depth = 0
        self._card_depth = None
        self._tt_depth = None
        self._sector = ""
        self._tt_name = ""
        self._tt_price = None
        self._tt_status = None
        self._collect_sector = False
        self._collect_price = False
        self._collect_hint = False

    @staticmethod
    def _attr(attrs, key):
        return dict(attrs).get(key) or ""

    def handle_starttag(self, tag, attrs):
        self._depth += 1
        qa  = self._attr(attrs, "data-qa")
        cls = self._attr(attrs, "class")

        if qa == "price-category":
            self._card_depth = self._depth
            self._sector = ""
            self._tt_depth = None
            return

        if self._card_depth is None:
            return

        if "pc-list-category" in cls:
            self._collect_sector = True
            return

        if qa == "tickettype":
            self._tt_depth = self._depth
            self._tt_name = self._attr(attrs, "data-tt-name").strip()
            self._tt_price = None
            self._tt_status = None
            return

        if self._tt_depth is None:
            return

        if qa == "tickettypeItem-price":
            self._collect_price = True
        elif qa == "ticket-type-availability-hint":
            self._collect_hint = True

    def handle_endtag(self, tag):
        if self._tt_depth is not None and self._depth == self._tt_depth:
            if self._tt_name:
                status = self._tt_status if self._tt_status is not None else "Disponível"
                self.tickets.append({
                    "sector": self._sector,
                    "type": self._tt_name,
                    "price": self._tt_price,
                    "status": status,
                })
            self._tt_depth = None
            self._collect_price = False
            self._collect_hint = False

        if self._card_depth is not None and self._depth == self._card_depth:
            self._card_depth = None

        self._depth -= 1

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return
        if self._collect_sector:
            self._sector = text
            self._collect_sector = False
            return
        if self._collect_price:
            m = re.search(r"(\d{1,3}(?:[.,]\d{3})*,\d{2})", text.replace("\xa0", ""))
            if m:
                self._tt_price = float(m.group(1).replace(".", "").replace(",", "."))
            self._collect_price = False
            return
        if self._collect_hint:
            self._tt_status = text
            self._collect_hint = False


class BuyTicketParser(HTMLParser):
    PRICE_RE = re.compile(r"R\$[\s\xa0]*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)")

    def __init__(self):
        super().__init__()
        self.prices = []
        self._chunks = []

    def handle_data(self, data):
        t = data.strip()
        if t:
            self._chunks.append(t.lower())
        for m in self.PRICE_RE.finditer(data):
            try:
                val = float(m.group(1).replace(".", "").replace(",", "."))
                if 100 <= val <= 50_000:
                    self.prices.append(val)
            except ValueError:
                pass

    @property
    def full_text(self):
        return " ".join(self._chunks)


# ──────────────────────────────────────────────────────────────────────────────
# Monitor
# ──────────────────────────────────────────────────────────────────────────────

class TicketMonitor:

    async def check_livepass(self) -> dict:
        result = {"available": False, "min_price": None, "tickets": [], "message": "", "error": None}
        try:
            html = await asyncio.get_event_loop().run_in_executor(
                None, lambda: _fetch_livepass(timeout=45)
            )
            parser = LivepassParser()
            parser.feed(html)
            tickets = parser.tickets
            result["tickets"] = tickets
            logger.info(f"Livepass: {len(tickets)} ingressos parseados")

            available = [t for t in tickets if "indisponível" not in t["status"].lower()]
            prices = [t["price"] for t in tickets if t["price"]]

            if available:
                result["available"] = True
                result["message"] = f"{len(available)} tipo(s) disponível(is)"
                result["min_price"] = min(prices) if prices else None
            elif tickets:
                result["message"] = f"{len(tickets)} tipo(s) — todos indisponíveis"
                result["min_price"] = min(prices) if prices else None
            else:
                result["message"] = "Sem dados — verifique manualmente"

        except urllib.error.HTTPError as e:
            result["error"] = f"HTTP {e.code}"
            logger.error(f"Livepass: HTTP {e.code}")
        except Exception as e:
            logger.exception("Erro no check_livepass")
            result["error"] = str(e)[:200]
        return result

    async def check_buyticket(self) -> dict:
        result = {"available": False, "min_price": None, "ticket_count": None, "message": "", "error": None}
        try:
            html = await asyncio.get_event_loop().run_in_executor(
                None, lambda: _fetch_buyticket(timeout=30)
            )
            parser = BuyTicketParser()
            parser.feed(html)

            sold_out = any(t in parser.full_text for t in ["sem ingressos", "nenhum ingresso"])

            if parser.prices and not sold_out:
                result["available"] = True
                result["min_price"] = min(parser.prices)
                result["ticket_count"] = len(parser.prices)
                result["message"] = f"{len(parser.prices)} ingresso(s) a partir de R$ {min(parser.prices):.2f}"
            else:
                result["message"] = "Sem ingressos no mercado secundário"

        except urllib.error.HTTPError as e:
            result["error"] = f"HTTP {e.code}"
            logger.error(f"BuyTicket: HTTP {e.code}")
        except Exception as e:
            logger.exception("Erro no check_buyticket")
            result["error"] = str(e)[:200]
        return result

    async def check_all(self) -> dict:
        bt, lp = await asyncio.gather(
            self.check_buyticket(),
            self.check_livepass(),
        )
        return {"buyticket": bt, "livepass": lp}