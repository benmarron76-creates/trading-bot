import asyncio
import httpx
import schedule
import time
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError

# ============================================================
#  CONFIGURATION — REMPLIS CES VALEURS
# ============================================================
TELEGRAM_BOT_TOKEN = "8219086095:AAG4oU0mMOCpLMlcsT5UaBgHadoLFc5awDE"
TELEGRAM_CHAT_ID   = "1038048711"

# Paramètres de trading
MISE_MAX_SOL       = 0.1     # Mise maximum par trade en SOL
STOP_LOSS_PCT      = 5       # Stop loss en %
TAKE_PROFIT_PCT    = 10      # Take profit en %

# ============================================================
#  TOKENS SURVEILLÉS — ajoute autant de tokens que tu veux !
#  Format : "NOM": "ADRESSE_SOLANA"
# ============================================================
TOKENS = {
    "SOL":   "So11111111111111111111111111111111111111112",
    "wBTC":  "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",
    "JUP":   "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "BONK":  "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "RAY":   "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "WIF":   "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "PYTH":  "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
    "JITO":  "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
    "POPCAT":"7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
    "MYRO":  "HhJpBhRRn4g56VsyLuT8DL5Bv31HkXqsrahTTUCZeZg4",
}

# ============================================================

bot = Bot(token=TELEGRAM_BOT_TOKEN)
prix_precedents = {}
positions_ouvertes = {}

async def envoyer_alerte(message: str, emoji: str = ""):
    try:
        texte = f"{emoji} *SOLANA TRADING BOT*\n{'='*30}\n{message}\n\n⏰ {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=texte,
            parse_mode="Markdown"
        )
        print(f"  Alerte envoyée : {emoji}")
    except TelegramError as e:
        print(f"  Erreur Telegram: {e}")

async def get_prix_jupiter(token_mint: str) -> float:
    url = f"https://price.jup.ag/v6/price?ids={token_mint}"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, timeout=10)
            data = res.json()
            return float(data["data"][token_mint]["price"])
        except Exception:
            return 0.0

async def analyser_signal(prix_actuel: float, prix_precedent: float) -> tuple:
    if prix_precedent == 0:
        return "neutre", 0.0
    variation = ((prix_actuel - prix_precedent) / prix_precedent) * 100
    if variation >= 2.0:
        return "achat_scalp", variation
    elif variation <= -2.0:
        return "vente_scalp", variation
    elif variation >= 0.7:
        return "achat_swing", variation
    elif variation <= -0.7:
        return "vente_swing", variation
    return "neutre", variation

async def verifier_stop_loss_take_profit():
    for token, position in list(positions_ouvertes.items()):
        prix_entree = position["prix_entree"]
        type_trade  = position["type"]
        mint        = TOKENS.get(token, "")
        prix_actuel = await get_prix_jupiter(mint)
        if prix_actuel == 0:
            continue
        variation = ((prix_actuel - prix_entree) / prix_entree) * 100
        if variation <= -STOP_LOSS_PCT:
            msg = (
                f"STOP LOSS — *{token}*\n"
                f"Entrée : ${prix_entree:.4f}\n"
                f"Actuel : ${prix_actuel:.4f}\n"
                f"Perte  : {variation:.2f}%\n"
                f"Type   : {type_trade.upper()}\n"
                f"Vends sur Jupiter maintenant !"
            )
            await envoyer_alerte(msg, "🔴")
            del positions_ouvertes[token]
        elif variation >= TAKE_PROFIT_PCT:
            msg = (
                f"TAKE PROFIT — *{token}*\n"
                f"Entrée : ${prix_entree:.4f}\n"
                f"Actuel : ${prix_actuel:.4f}\n"
                f"Gain   : +{variation:.2f}%\n"
                f"Type   : {type_trade.upper()}\n"
                f"Prends tes profits sur Jupiter !"
            )
            await envoyer_alerte(msg, "🟢")
            del positions_ouvertes[token]

async def scanner_marche():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scan en cours...")
    for nom, mint in TOKENS.items():
        prix_actuel = await get_prix_jupiter(mint)
        if prix_actuel == 0:
            print(f"  {nom}: prix indisponible")
            continue
        prix_precedent = prix_precedents.get(nom, prix_actuel)
        signal, variation = await analyser_signal(prix_actuel, prix_precedent)
        print(f"  {nom:8} ${prix_actuel:.4f}  ({variation:+.2f}%)  {signal}")

        if signal == "achat_scalp":
            msg = (
                f"SCALP ACHAT — *{nom}*\n"
                f"Prix    : ${prix_actuel:.4f}\n"
                f"Hausse  : +{variation:.2f}% en 30s\n"
                f"TP      : ${prix_actuel * (1 + TAKE_PROFIT_PCT/100):.4f}\n"
                f"SL      : ${prix_actuel * (1 - STOP_LOSS_PCT/100):.4f}\n"
                f"Mise    : {MISE_MAX_SOL} SOL max\n"
                f"Achète sur jup.ag"
            )
            await envoyer_alerte(msg, "⚡")
            positions_ouvertes[nom] = {"prix_entree": prix_actuel, "type": "scalp"}

        elif signal == "achat_swing":
            msg = (
                f"SWING ACHAT — *{nom}*\n"
                f"Prix    : ${prix_actuel:.4f}\n"
                f"Tendance: +{variation:.2f}%\n"
                f"TP      : ${prix_actuel * (1 + TAKE_PROFIT_PCT/100):.4f}\n"
                f"SL      : ${prix_actuel * (1 - STOP_LOSS_PCT/100):.4f}\n"
                f"Mise    : {MISE_MAX_SOL} SOL max\n"
                f"Achète sur jup.ag"
            )
            await envoyer_alerte(msg, "📈")
            positions_ouvertes[nom] = {"prix_entree": prix_actuel, "type": "swing"}

        elif signal == "vente_scalp":
            msg = (
                f"SCALP VENTE — *{nom}*\n"
                f"Prix    : ${prix_actuel:.4f}\n"
                f"Baisse  : {variation:.2f}% en 30s\n"
                f"Vends ou évite d'acheter maintenant"
            )
            await envoyer_alerte(msg, "🔻")

        elif signal == "vente_swing":
            msg = (
                f"SWING VENTE — *{nom}*\n"
                f"Prix    : ${prix_actuel:.4f}\n"
                f"Tendance: {variation:.2f}%\n"
                f"Surveille la tendance"
            )
            await envoyer_alerte(msg, "📉")

        prix_precedents[nom] = prix_actuel

    await verifier_stop_loss_take_profit()

async def rapport_quotidien():
    lignes = ""
    if positions_ouvertes:
        for token, pos in positions_ouvertes.items():
            prix_actuel = await get_prix_jupiter(TOKENS.get(token, ""))
            variation = ((prix_actuel - pos['prix_entree']) / pos['prix_entree']) * 100
            emoji = "✅" if variation >= 0 else "🔴"
            lignes += f"{emoji} {token} ({pos['type']}) : {variation:+.2f}%\n"
    else:
        lignes = "Aucune position ouverte\n"

    msg = (
        f"RAPPORT QUOTIDIEN\n"
        f"Tokens : {', '.join(TOKENS.keys())}\n\n"
        f"Positions :\n{lignes}\n"
        f"SL : {STOP_LOSS_PCT}%  |  TP : {TAKE_PROFIT_PCT}%"
    )
    await envoyer_alerte(msg, "📊")

async def main():
    print("=" * 50)
    print("  BOT TRADING SOLANA — @Soltader_bot")
    print("=" * 50)
    print(f"Tokens : {', '.join(TOKENS.keys())}")
    print(f"SL : {STOP_LOSS_PCT}%  |  TP : {TAKE_PROFIT_PCT}%")
    print(f"Scan toutes les 30 secondes")
    print("=" * 50)

    await envoyer_alerte(
        f"Bot démarré avec succès !\n"
        f"Tokens surveillés :\n" + "\n".join(TOKENS.keys()) + f"\n\n"
        f"SL : {STOP_LOSS_PCT}%  |  TP : {TAKE_PROFIT_PCT}%\n"
        f"Scan toutes les 30 secondes",
        "🚀"
    )

    await scanner_marche()

    while True:
        await asyncio.sleep(30)
        await scanner_marche()
        now = datetime.now()
        if now.hour == 8 and now.minute == 0:
            await rapport_quotidien()

if __name__ == "__main__":
    asyncio.run(main())