"""
monitor.py – Scraping de ingressos para Iron Maiden Curitiba 2026
Usa Playwright (headless Chromium) para renderizar JavaScript corretamente.

Livepass:
  - Seleciona "VENDA GERAL" no dropdown de modalidade
  - Lê os setores (PISTA PREMIUM, etc.) e seus status
  - Alerta quando qualquer item sair de "Indisponível no momento"

BuyTicket:
  - Mercado secundário (revendedores)
  - Detecta preços listados na página
"""

import re
import json
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


class TicketMonitor:

    # ──────────────────────────────────────────
    # Livepass
    # ──────────────────────────────────────────

    async def check_livepass(self) -> dict:
        """
        Abre a página da Livepass, seleciona 'VENDA GERAL' no dropdown,
        e lê o status de cada setor/tipo de ingresso.
        Retorna disponível=True se QUALQUER ingresso não for 'Indisponível no momento'.
        """
        result = {
            "available": False,
            "min_price": None,
            "tickets": [],   # lista de dicts {sector, type, price, status}
            "message": "",
            "error": None,
        }

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                ctx = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    locale="pt-BR",
                    viewport={"width": 1280, "height": 900},
                )
                page = await ctx.new_page()

                logger.info("Livepass: abrindo página...")
                await page.goto(LIVEPASS_URL, wait_until="networkidle", timeout=60_000)

                # ── Seleciona "VENDA GERAL" no dropdown ──
                dropdown = page.locator("select").first
                await dropdown.wait_for(timeout=15_000)

                options = await dropdown.locator("option").all_inner_texts()
                logger.info(f"Livepass dropdown opções: {options}")

                venda_geral_value = None
                for opt in await dropdown.locator("option").all():
                    text = (await opt.inner_text()).strip().upper()
                    if "VENDA GERAL" in text:
                        venda_geral_value = await opt.get_attribute("value")
                        break

                if venda_geral_value is None:
                    # Tenta pelo texto visível
                    await dropdown.select_option(label="VENDA GERAL")
                else:
                    await dropdown.select_option(value=venda_geral_value)

                # Aguarda a tabela de ingressos carregar
                await page.wait_for_timeout(2000)

                # ── Lê os setores e status ──
                tickets = []
                prices = []

                # Cada linha da tabela de ingressos
                # Estrutura vista nas imagens:
                #   Setor (ex: PISTA PREMIUM) | Tipo (ex: INTEIRA) | Preço | Status
                rows = await page.locator("table tr, [class*='ticket'], [class*='ingresso']").all()

                if not rows:
                    # Fallback: lê o texto completo e faz parse manual
                    content = await page.inner_text("body")
                    tickets = self._parse_livepass_text(content)
                else:
                    for row in rows:
                        text = (await row.inner_text()).strip()
                        parsed = self._parse_ticket_row(text)
                        if parsed:
                            tickets.append(parsed)

                # Se ainda não achou nada, tenta parse no body completo
                if not tickets:
                    content = await page.inner_text("body")
                    tickets = self._parse_livepass_text(content)

                await browser.close()

                # ── Analisa resultados ──
                result["tickets"] = tickets
                available_tickets = [
                    t for t in tickets
                    if "indisponível" not in t.get("status", "").lower()
                    and t.get("status", "") != ""
                ]

                for t in tickets:
                    if t.get("price"):
                        prices.append(t["price"])

                if available_tickets:
                    result["available"] = True
                    result["message"] = f"{len(available_tickets)} tipo(s) disponível(is)"
                    if prices:
                        result["min_price"] = min(prices)
                elif tickets:
                    result["message"] = "Todos os setores indisponíveis no momento"
                else:
                    result["message"] = "Não foi possível ler os ingressos"

        except PWTimeout:
            result["error"] = "Timeout ao carregar Livepass (>60s)"
        except Exception as e:
            logger.exception("Erro no check_livepass")
            result["error"] = str(e)

        return result

    def _parse_livepass_text(self, text: str) -> list:
        """
        Parse manual do texto completo da página da Livepass.
        Baseado na estrutura real vista nas imagens:
          PISTA PREMIUM
          INTEIRA   R$ 890,00   Indisponível no momento
          MEIA ENTRADA  R$ 445,00  Indisponível no momento
          ...
        """
        tickets = []
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        # Setores conhecidos da Arena da Baixada para este evento
        sector_keywords = [
            "PISTA PREMIUM", "PISTA", "CADEIRA", "CAMAROTE",
            "VIP", "ARQUIBANCADA", "TRIBUNA", "SETOR",
        ]

        price_re = re.compile(r"R\$\s*(\d{1,3}(?:[.,]\d{3})*,\d{2})")
        current_sector = ""

        i = 0
        while i < len(lines):
            line = lines[i].upper()

            # Detecta linha de setor
            is_sector = any(kw in line for kw in sector_keywords)
            if is_sector and not price_re.search(lines[i]):
                current_sector = lines[i].strip()
                i += 1
                continue

            # Detecta linha de ingresso (tem preço)
            price_match = price_re.search(lines[i])
            if price_match and current_sector:
                ticket_type = lines[i][:price_match.start()].strip()
                price_str = price_match.group(1).replace(".", "").replace(",", ".")
                price_val = float(price_str)

                # Status: geralmente na mesma linha ou linha seguinte
                status = ""
                after_price = lines[i][price_match.end():].strip()
                if after_price:
                    status = after_price
                elif i + 1 < len(lines):
                    next_line = lines[i + 1].strip().lower()
                    status_keywords = ["indisponível", "disponível", "esgotado", "comprar", "adicionar"]
                    if any(kw in next_line for kw in status_keywords):
                        status = lines[i + 1].strip()
                        i += 1

                if ticket_type or price_val:
                    tickets.append({
                        "sector": current_sector,
                        "type": ticket_type,
                        "price": price_val,
                        "status": status if status else "Indisponível no momento",
                    })

            i += 1

        return tickets

    def _parse_ticket_row(self, text: str) -> dict | None:
        """Parse de uma linha/row individual."""
        price_re = re.compile(r"R\$\s*(\d{1,3}(?:[.,]\d{3})*,\d{2})")
        match = price_re.search(text)
        if not match:
            return None

        price_str = match.group(1).replace(".", "").replace(",", ".")
        price_val = float(price_str)
        before = text[:match.start()].strip()
        after = text[match.end():].strip()

        return {
            "sector": "",
            "type": before,
            "price": price_val,
            "status": after if after else "Indisponível no momento",
        }

    # ──────────────────────────────────────────
    # BuyTicket
    # ──────────────────────────────────────────

    async def check_buyticket(self) -> dict:
        """
        Verifica ingressos no BuyTicket (mercado secundário).
        A página é Next.js; usa Playwright para garantir renderização completa.
        """
        result = {
            "available": False,
            "min_price": None,
            "ticket_count": None,
            "message": "",
            "error": None,
        }

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                ctx = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    locale="pt-BR",
                )
                page = await ctx.new_page()

                logger.info("BuyTicket: abrindo página...")
                await page.goto(BUYTICKET_URL, wait_until="networkidle", timeout=60_000)
                await page.wait_for_timeout(2000)

                content = await page.inner_text("body")
                await browser.close()

            # Parse de preços
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
            sold_out = any(t in text_lower for t in [
                "sem ingressos", "nenhum ingresso", "esgotado",
            ])
            has_listings = any(t in text_lower for t in [
                "comprar", "ver ingresso", "ver oferta",
            ])

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
            result["error"] = str(e)

        return result

    # ──────────────────────────────────────────
    # Verifica os dois
    # ──────────────────────────────────────────

    async def check_all(self) -> dict:
        # Roda em paralelo
        bt, lp = await asyncio.gather(
            self.check_buyticket(),
            self.check_livepass(),
        )
        return {"buyticket": bt, "livepass": lp}