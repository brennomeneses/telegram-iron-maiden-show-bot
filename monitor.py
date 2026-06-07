"""
monitor.py – Scraping de ingressos para Iron Maiden Curitiba 2026
"""

import re
import logging
import asyncio
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
)

STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-accelerated-2d-canvas",
    "--no-first-run",
    "--no-zygote",
    "--disable-gpu",
    "--lang=pt-BR",
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
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "sec-ch-ua": '"Chromium";v="125", "Google Chrome";v="125", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
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

                logger.info("Livepass: abrindo página...")
                try:
                    await page.goto(LIVEPASS_URL, wait_until="networkidle", timeout=60_000)
                except Exception as e:
                    if "net::" in str(e) or "ERR_HTTP2" in str(e):
                        logger.warning(f"Livepass network error, retrying: {e}")
                        await page.goto(LIVEPASS_URL, wait_until="domcontentloaded", timeout=60_000)
                        await page.wait_for_timeout(5000)
                    else:
                        raise

                # ── Encontra e clica no dropdown de modalidade ──
                # O log mostrou que o único <select> visível é #language-selection
                # O dropdown de modalidade é um componente customizado (div/button)
                # Tentamos múltiplas estratégias em ordem

                selected_venda_geral = await self._select_venda_geral(page)
                if selected_venda_geral:
                    await page.wait_for_timeout(2500)

                content = await page.inner_text("body")
                await browser.close()

            tickets = self._parse_livepass_text(content)
            result["tickets"] = tickets

            available = [
                t for t in tickets
                if "indisponível" not in t.get("status", "").lower()
                and t.get("status", "").strip() != ""
            ]
            prices = [t["price"] for t in tickets if t.get("price")]

            if available:
                result["available"] = True
                result["message"] = f"{len(available)} tipo(s) disponível(is)"
                if prices:
                    result["min_price"] = min(prices)
            elif tickets:
                result["message"] = f"{len(tickets)} setor(es) monitorado(s) — todos indisponíveis"
                if prices:
                    result["min_price"] = min(prices)
            else:
                result["message"] = "Aguardando abertura de vendas"

        except PWTimeout:
            result["error"] = "Timeout ao carregar Livepass (>60s)"
        except Exception as e:
            logger.exception("Erro no check_livepass")
            result["error"] = str(e)[:200]

        return result

    async def _select_venda_geral(self, page) -> bool:
        """
        Seleciona 'VENDA GERAL' no <select data-qa="promo-selection-box">.
        HTML real:
          <select name="promo_id" data-qa="promo-selection-box" ...>
            <option value="">Selecione</option>
            <option value="186439">SÓCIO FURACÃO</option>
            <option value="186816">VENDA GERAL</option>
          </select>
        """
        try:
            sel = page.locator('[data-qa="promo-selection-box"]')
            await sel.wait_for(state="attached", timeout=15_000)

            # Seleciona pelo value fixo (186816) com fallback pelo label
            try:
                await sel.select_option(value="186816")
            except Exception:
                await sel.select_option(label="VENDA GERAL")

            logger.info("Livepass: selecionou VENDA GERAL via [data-qa='promo-selection-box']")
            return True
        except Exception as e:
            logger.warning(f"Livepass: falha ao selecionar VENDA GERAL: {e}")
            return False

    def _parse_livepass_text(self, text: str) -> list:
        """
        Parse do texto da página Livepass.
        Estrutura real (imagem):
          PISTA PREMIUM
            INTEIRA          R$ 890,00   Indisponível no momento
            MEIA ENTRADA     R$ 445,00   Indisponível no momento
        """
        tickets = []
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        sector_keywords = [
            "PISTA PREMIUM", "PISTA", "CADEIRA", "CAMAROTE",
            "VIP", "ARQUIBANCADA", "TRIBUNA", "MEZANINO",
        ]
        price_re = re.compile(r"R\$\s*(\d{1,3}(?:[.,]\d{3})*,\d{2})")
        current_sector = ""

        i = 0
        while i < len(lines):
            line_upper = lines[i].upper()

            # Linha de setor (keyword sem preço)
            if any(kw in line_upper for kw in sector_keywords) and not price_re.search(lines[i]):
                current_sector = lines[i].strip()
                i += 1
                continue

            # Linha com preço
            m = price_re.search(lines[i])
            if m and current_sector:
                ticket_type = lines[i][:m.start()].strip()
                price_val = float(m.group(1).replace(".", "").replace(",", "."))

                status = lines[i][m.end():].strip()
                if not status and i + 1 < len(lines):
                    nxt = lines[i + 1].strip().lower()
                    if any(k in nxt for k in ["indisponível", "disponível", "esgotado", "comprar", "adicionar"]):
                        status = lines[i + 1].strip()
                        i += 1

                if not status:
                    status = "Indisponível no momento"

                tickets.append({
                    "sector": current_sector,
                    "type": ticket_type,
                    "price": price_val,
                    "status": status,
                })

            i += 1

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

                logger.info("BuyTicket: abrindo página...")
                await page.goto(BUYTICKET_URL, wait_until="networkidle", timeout=60_000)
                await page.wait_for_timeout(2000)

                content = await page.inner_text("body")
                await browser.close()

            price_re = re.compile(r"R\$\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)")
            prices = []
            for m in price_re.finditer(content):
                try:
                    clean = m.group(1).replace(".", "").replace(",", ".")
                    val = float(clean)
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
    # Verifica os dois
    # ──────────────────────────────────────────

    async def check_all(self) -> dict:
        bt, lp = await asyncio.gather(
            self.check_buyticket(),
            self.check_livepass(),
        )
        return {"buyticket": bt, "livepass": lp}