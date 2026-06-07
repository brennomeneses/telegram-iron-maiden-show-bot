#!/usr/bin/env python3
"""
Iron Maiden Ticket Monitor Bot
Monitora disponibilidade de ingressos no BuyTicket e Livepass
"""

import asyncio
import logging
import os
import json
from dotenv import load_dotenv

load_dotenv()  # Carrega variáveis do arquivo .env automaticamente
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from monitor import TicketMonitor

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Arquivo para persistir subscribers
SUBSCRIBERS_FILE = "subscribers.json"

def load_subscribers() -> set:
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_subscribers(subscribers: set):
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(list(subscribers), f)

# Estado global
subscribers: set = load_subscribers()
monitor = TicketMonitor()
last_status: dict = {}

# ──────────────────────────────────────────────
# Handlers
# ──────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    keyboard = [
        [InlineKeyboardButton("🔔 Ativar alertas", callback_data="subscribe")],
        [InlineKeyboardButton("📊 Ver status agora", callback_data="check")],
        [InlineKeyboardButton("🔗 Links dos sites", callback_data="links")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🤘 *Iron Maiden – Run For Your Lives World Tour 2026*\n"
        "🏟️ Arena da Baixada – Curitiba/PR – 28/10/2026\n\n"
        "Eu monitoro os dois canais de venda:\n"
        "• *BuyTicket* (mercado secundário)\n"
        "• *Livepass* (venda oficial)\n\n"
        "Escolha uma opção abaixo:",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *Comandos disponíveis:*\n\n"
        "/start – Menu principal\n"
        "/check – Verificar status agora\n"
        "/subscribe – Ativar alertas automáticos\n"
        "/unsubscribe – Desativar alertas\n"
        "/status – Ver se alertas estão ativos\n"
        "/links – Links diretos para compra\n"
        "/help – Esta mensagem",
        parse_mode="Markdown",
    )

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Verificando disponibilidade...")
    result = await monitor.check_all()
    await msg.edit_text(format_status(result), parse_mode="Markdown")

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subscribers.add(chat_id)
    save_subscribers(subscribers)
    await update.message.reply_text(
        "✅ *Alertas ativados!*\n\n"
        "Você receberá uma notificação assim que novos ingressos estiverem disponíveis.\n"
        "Use /unsubscribe para cancelar.",
        parse_mode="Markdown",
    )

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subscribers.discard(chat_id)
    save_subscribers(subscribers)
    await update.message.reply_text(
        "🔕 *Alertas desativados.*\n\nUse /subscribe para reativar.",
        parse_mode="Markdown",
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    active = chat_id in subscribers
    icon = "✅" if active else "❌"
    await update.message.reply_text(
        f"{icon} Alertas estão {'*ativados*' if active else '*desativados*'} para você.\n\n"
        f"👥 Total de usuários monitorando: {len(subscribers)}",
        parse_mode="Markdown",
    )

async def links_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔗 *Links diretos para ingressos:*\n\n"
        "🎟️ *BuyTicket (mercado secundário):*\n"
        "[Clique aqui](https://buyticketbrasil.com/evento/ironmaiden-runforyourlivesworldtour2026?data=1793242799000&evento_local=1779374792451x659702685709631500&cidade=Curitiba)\n\n"
        "🎟️ *Livepass (venda oficial):*\n"
        "[Clique aqui](https://www.livepass.com.br/event/iron-maiden-run-for-your-lives-world-tour-2026-cwb-arena-da-baixada-21684448/)",
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )

# ──────────────────────────────────────────────
# Callback de botões inline
# ──────────────────────────────────────────────

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "subscribe":
        chat_id = update.effective_chat.id
        subscribers.add(chat_id)
        save_subscribers(subscribers)
        await query.edit_message_text(
            "✅ *Alertas ativados!*\n\n"
            "Você será notificado quando novos ingressos aparecerem.\n"
            "Use /unsubscribe para cancelar.",
            parse_mode="Markdown",
        )

    elif query.data == "check":
        await query.edit_message_text("🔍 Verificando disponibilidade...")
        result = await monitor.check_all()
        await query.edit_message_text(format_status(result), parse_mode="Markdown")

    elif query.data == "links":
        await query.edit_message_text(
            "🔗 *Links diretos para ingressos:*\n\n"
            "🎟️ *BuyTicket (mercado secundário):*\n"
            "[Clique aqui](https://buyticketbrasil.com/evento/ironmaiden-runforyourlivesworldtour2026?data=1793242799000&evento_local=1779374792451x659702685709631500&cidade=Curitiba)\n\n"
            "🎟️ *Livepass (venda oficial):*\n"
            "[Clique aqui](https://www.livepass.com.br/event/iron-maiden-run-for-your-lives-world-tour-2026-cwb-arena-da-baixada-21684448/)",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

# ──────────────────────────────────────────────
# Formatação de status
# ──────────────────────────────────────────────

def format_status(result: dict) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    lines = [
        "🎸 *Iron Maiden – Curitiba 28/10/2026*",
        f"🕐 Última verificação: `{now}`\n",
    ]

    # BuyTicket
    bt = result.get("buyticket", {})
    bt_ok = bt.get("available", False)
    bt_icon = "🟢" if bt_ok else "🔴"
    lines.append(f"{bt_icon} *BuyTicket* (revenda)")
    if bt_ok:
        price = bt.get("min_price")
        count = bt.get("ticket_count")
        if price:
            lines.append(f"   💰 A partir de R$ {price:.2f}")
        if count:
            lines.append(f"   🎟️ {count} ingresso(s) disponível(is)")
    else:
        msg = bt.get("message", "Sem ingressos disponíveis no momento")
        lines.append(f"   ℹ️ {msg}")
    if bt.get("error"):
        lines.append(f"   ⚠️ Erro: {bt['error']}")
    lines.append("")

    # Livepass
    lp = result.get("livepass", {})
    lp_ok = lp.get("available", False)
    lp_icon = "🟢" if lp_ok else "🔴"
    lines.append(f"{lp_icon} *Livepass* (oficial – Venda Geral)")
    if lp.get("error"):
        lines.append(f"   ⚠️ {lp['error']}")
    elif lp_ok:
        price = lp.get("min_price")
        if price:
            lines.append(f"   💰 A partir de R$ {price:.2f}")
        tickets = lp.get("tickets", [])
        available = [t for t in tickets if "indisponível" not in t.get("status", "").lower()]
        for t in available[:6]:
            sector = t.get("sector", "")
            ttype  = t.get("type", "")
            tprice = t.get("price")
            tstatus = t.get("status", "")
            label = f"{sector} – {ttype}".strip(" –") if sector else ttype
            price_str = f"R$ {tprice:.2f}" if tprice else ""
            lines.append(f"   ✅ {label} {price_str} • {tstatus}")
    else:
        msg = lp.get("message", "Indisponível no momento")
        lines.append(f"   ℹ️ {msg}")
        tickets = lp.get("tickets", [])
        if tickets:
            lines.append(f"   📋 {len(tickets)} tipo(s) monitorado(s), todos indisponíveis")
    lines.append("")

    lines.append("🔗 [BuyTicket](https://buyticketbrasil.com/evento/ironmaiden-runforyourlivesworldtour2026?data=1793242799000&evento_local=1779374792451x659702685709631500&cidade=Curitiba) | [Livepass](https://www.livepass.com.br/event/iron-maiden-run-for-your-lives-world-tour-2026-cwb-arena-da-baixada-21684448/)")

    return "\n".join(lines)

# ──────────────────────────────────────────────
# Job de monitoramento periódico
# ──────────────────────────────────────────────

async def periodic_check(context: ContextTypes.DEFAULT_TYPE):
    global last_status
    if not subscribers:
        return

    logger.info("Executando verificação periódica...")
    result = await monitor.check_all()

    alerts = []

    # Verifica mudança no BuyTicket
    bt = result.get("buyticket", {})
    bt_prev = last_status.get("buyticket", {})
    bt_available = bt.get("available", False)
    bt_was_available = bt_prev.get("available", False)

    if bt_available and not bt_was_available:
        price = bt.get("min_price")
        count = bt.get("ticket_count")
        msg = "🚨 *NOVO INGRESSO NO BUYTICKET!*\n\n"
        msg += "🎸 Iron Maiden – Curitiba 28/10/2026\n"
        if price:
            msg += f"💰 A partir de R$ {price:.2f}\n"
        if count:
            msg += f"🎟️ {count} ingresso(s) disponível(is)\n"
        msg += "\n[👉 Comprar agora no BuyTicket](https://buyticketbrasil.com/evento/ironmaiden-runforyourlivesworldtour2026?data=1793242799000&evento_local=1779374792451x659702685709631500&cidade=Curitiba)"
        alerts.append(msg)

    # Verifica mudança no Livepass
    lp = result.get("livepass", {})
    lp_prev = last_status.get("livepass", {})
    lp_available = lp.get("available", False)
    lp_was_available = lp_prev.get("available", False)

    if lp_available and not lp_was_available:
        lots = lp.get("lots", [])
        msg = "🚨 *NOVO LOTE ABERTO NA LIVEPASS!*\n\n"
        msg += "🎸 Iron Maiden – Curitiba 28/10/2026\n"
        for lot in lots:
            msg += f"🎟️ {lot}\n"
        price = lp.get("min_price")
        if price:
            msg += f"💰 A partir de R$ {price:.2f}\n"
        msg += "\n[👉 Comprar agora na Livepass](https://www.livepass.com.br/event/iron-maiden-run-for-your-lives-world-tour-2026-cwb-arena-da-baixada-21684448/)"
        alerts.append(msg)

    # Envia alertas
    for alert in alerts:
        for chat_id in list(subscribers):
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=alert,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logger.error(f"Erro ao enviar para {chat_id}: {e}")
                if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                    subscribers.discard(chat_id)
                    save_subscribers(subscribers)

    last_status = result

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("Defina a variável de ambiente TELEGRAM_BOT_TOKEN")

    interval = int(os.environ.get("CHECK_INTERVAL_SECONDS", "300"))  # 5 min padrão

    app = Application.builder().token(token).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("subscribe", subscribe_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("links", links_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Job periódico
    app.job_queue.run_repeating(
        periodic_check,
        interval=interval,
        first=10,
        name="ticket_monitor",
    )

    logger.info(f"Bot iniciado. Verificando a cada {interval}s")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()