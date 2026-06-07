"""
monitor.py – Iron Maiden Curitiba 2026

Livepass: Playwright para carregar a página (contorna bloqueios de sessão/cookie),
          BeautifulSoup com seletores data-qa exatos para parsear o HTML.

BuyTicket: Playwright (Next.js).
"""

import re
import logging
import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

BUYTICKET_URL = (
    "https://buyticketbrasil.com/evento/ironmaiden-runforyourlivesworldtour2026"
    "?data=1793242799000"
    "&evento_local=1779374792451x659702685709631500"
    "&cidade=Curitiba"
)

LIVEPASS_URL = (
    "https://www.livepass.com.br/event/"
    "iron-maiden-run-for-your-lives-world-tour-2026-cwb-arena-da-baixada-21684448/"
    "?promo_id=186816"
)

STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox", "--disable-setuid-sandbox",
    "--disable-dev-shm-usage", "--disable-gpu",
    "--no-first-run", "--no-zygote", "--lang=pt-BR",
]


async def _new_stealth_context(pw):
    browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS)
    ctx = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        viewport={"width": 1366, "height": 768},
        extra_http_headers={
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "sec-ch-ua": '"Chromium";v="125", "Google Chrome";v="125"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
        },
        ignore_https_errors=True,
    )
    await ctx.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return browser, ctx


class TicketMonitor:

    # ──────────────────────────────────────────
    # Livepass
    # ──────────────────────────────────────────

    async def check_livepass(self) -> dict:
        result = {
            "available": False,
            "min_price": None,
            "tickets": [],
            "message": "",
            "error": None,
        }

        try:
            async with async_playwright() as pw:
                browser, ctx = await _new_stealth_context(pw)
                page = await ctx.new_page()

                logger.info("Livepass: carregando...")

                # domcontentloaded evita ERR_HTTP2 do networkidle
                # timeout generoso pois a Livepass pode ser lenta
                await page.goto(LIVEPASS_URL, wait_until="domcontentloaded", timeout=90_000)

                # Espera pelo menos um card de ingresso aparecer no DOM
                try:
                    await page.wait_for_selector(
                        '[data-qa="price-category"]',
                        state="attached",
                        timeout=20_000,
                    )
                except PWTimeout:
                    logger.warning("Livepass: [data-qa='price-category'] não apareceu, tentando ler assim mesmo")

                # Pequena pausa para renderização completa
                await page.wait_for_timeout(1500)

                html = await page.content()
                await browser.close()

            tickets = self._parse_livepass_html(html)
            result["tickets"] = tickets

            available = [
                t for t in tickets
                if "indisponível" not in t["status"].lower()
                and t["status"].strip() != ""
            ]
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

            logger.info(f"Livepass: {len(tickets)} ingressos, {len(available)} disponíveis")

        except PWTimeout:
            result["error"] = "Timeout ao carregar Livepass (>90s)"
        except Exception as e:
            logger.exception("Erro no check_livepass")
            result["error"] = str(e)[:200]

        return result

    def _parse_livepass_html(self, html: str) -> list:
        """
        Seletores data-qa exatos do HTML real da Livepass:

          <div data-qa="price-category">
            <div class="pc-list-category"><span>PISTA PREMIUM</span></div>
            <div data-qa="tickettype" data-tt-name="INTEIRA">
              <div data-qa="tickettypeItem-price">R$ 890,00</div>
              <div data-qa="ticket-type-availability-hint">Indisponível no momento</div>
            </div>
          </div>

        Quando disponível: ticket-type-availability-hint SOME e o stepper aparece.
        """
        soup = BeautifulSoup(html, "lxml")
        tickets = []

        for card in soup.select('[data-qa="price-category"]'):
            sector_el = card.select_one(".pc-list-category span")
            sector = sector_el.get_text(strip=True) if sector_el else ""

            for tt in card.select('[data-qa="tickettype"]'):
                # Nome — atributo data-tt-name é o mais limpo
                name = tt.get("data-tt-name", "").strip()
                if not name:
                    span = tt.select_one(".ticket-type-title span")
                    name = span.get_text(strip=True) if span else ""

                # Preço
                price_el = tt.select_one('[data-qa="tickettypeItem-price"]')
                price_val = None
                if price_el:
                    raw = price_el.get_text(strip=True).replace("\xa0", "")
                    m = re.search(r"(\d{1,3}(?:[.,]\d{3})*,\d{2})", raw)
                    if m:
                        price_val = float(m.group(1).replace(".", "").replace(",", "."))

                # Status
                hint_el = tt.select_one('[data-qa="ticket-type-availability-hint"]')
                print(f"DEBUG: name='{name}', price='{price_val}', hint='{hint_el.get_text(strip=True) if hint_el else 'N/A'}'")
                if hint_el:
                    status = hint_el.get_text(strip=True)
                else:
                    # Sem hint = disponível (stepper aparece no lugar)
                    status = "Disponível"

                if name:
                    tickets.append({
                        "sector": sector,
                        "type": name,
                        "price": price_val,
                        "status": status,
                    })

        return tickets

    # ──────────────────────────────────────────
    # BuyTicket
    # ──────────────────────────────────────────

    async def check_buyticket(self) -> dict:
        result = {
            "available": False,
            "min_price": None,
            "ticket_count": None,
            "message": "",
            "error": None,
        }

        try:
            async with async_playwright() as pw:
                browser, ctx = await _new_stealth_context(pw)
                page = await ctx.new_page()

                logger.info("BuyTicket: carregando...")
                await page.goto(BUYTICKET_URL, wait_until="networkidle", timeout=60_000)
                await page.wait_for_timeout(2000)

                content = await page.inner_text("body")
                await browser.close()

            price_re = re.compile(r"R\$\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)")
            prices = []
            for m in price_re.finditer(content):
                try:
                    val = float(m.group(1).replace(".", "").replace(",", "."))
                    if 100 <= val <= 50_000:
                        prices.append(val)
                except ValueError:
                    pass

            text_lower = content.lower()
            sold_out = any(t in text_lower for t in ["sem ingressos", "nenhum ingresso"])
            has_listings = any(t in text_lower for t in ["comprar", "ver ingresso", "ver oferta"])

            if prices and (has_listings or not sold_out):
                result["available"] = True
                result["min_price"] = min(prices)
                result["ticket_count"] = len(prices)
                result["message"] = f"{len(prices)} ingresso(s) a partir de R$ {min(prices):.2f}"
            else:
                result["message"] = "Sem ingressos no mercado secundário"

        except PWTimeout:
            result["error"] = "Timeout ao carregar BuyTicket (>60s)"
        except Exception as e:
            logger.exception("Erro no check_buyticket")
            result["error"] = str(e)[:200]

        return result

    # ──────────────────────────────────────────
    # Verifica os dois em paralelo
    # ──────────────────────────────────────────

    async def check_all(self) -> dict:
        bt, lp = await asyncio.gather(
            self.check_buyticket(),
            self.check_livepass(),
        )
        return {"buyticket": bt, "livepass": lp}