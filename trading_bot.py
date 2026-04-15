import asyncio
import httpx
import pandas as pd
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler
from telegram.error import TelegramError
import ta
import base58
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

# Config
TELEGRAM_BOT_TOKEN = "8219086095:AAG4oU0mMOCpLMlcsT5UaBgHadoLFc5awDE"
TELEGRAM_CHAT_ID = "1038048711"
MISE_MAX_SOL = 0.1
MISE_SHORT_USDC = 2
STOP_LOSS_PCT = 5
TAKE_PROFIT_PCT = 10
MAX_POSITIONS = 3
BUDGET_JOURNALIER_SOL = 0.5
SCORE_MIN_TRADE = 6
MAX_PERTES_CONSECUTIVES = 3
SOL_MINT = "So11111111111111111111111111111111111111112"
RPC_URL = "https://api.mainnet-beta.solana.com"
SHORT_TOKENS = {"SOL", "wBTC"}

PROJETS_INFO = {
    "SOL":      {"score_base": 9, "description": "Blockchain Solana native", "categorie": "L1", "solidite": "très élevée"},
    "wBTC":     {"score_base": 9, "description": "Bitcoin wrappé sur Solana", "categorie": "BTC", "solidite": "très élevée"},
    "JUP":      {"score_base": 8, "description": "DEX leader de Solana", "categorie": "DEX", "solidite": "élevée"},
    "ORCA":     {"score_base": 7, "description": "AMM DEX populaire", "categorie": "DEX", "solidite": "élevée"},
    "RENDER":   {"score_base": 8, "description": "GPU décentralisé pour IA", "categorie": "IA/GPU", "solidite": "élevée"},
    "DRIFT":    {"score_base": 7, "description": "Perpétuels décentralisés", "categorie": "DeFi", "solidite": "moyenne"},
    "PENGU":    {"score_base": 5, "description": "Meme coin Pudgy Penguins", "categorie": "Meme", "solidite": "faible"},
    "FARTCOIN": {"score_base": 3, "description": "Meme coin viral", "categorie": "Meme", "solidite": "très faible"},
    "TRUMP":    {"score_base": 4, "description": "Meme coin politique", "categorie": "Meme", "solidite": "faible"},
    "PYTH":     {"score_base": 7, "description": "Oracle de prix décentralisé", "categorie": "Infrastructure", "solidite": "élevée"},
    "WIF":      {"score_base": 4, "description": "Meme coin dogwifhat", "categorie": "Meme", "solidite": "faible"},
}

def charger_keypair():
    try:
        with open("config.env", "r") as f:
            for line in f:
                if line.startswith("PRIVATE_KEY="):
                    cle = line.strip().split("=", 1)[1]
                    return Keypair.from_bytes(base58.b58decode(cle))
    except Exception as e:
        print(f"Erreur chargement clé: {e}")
        return None

KEYPAIR = charger_keypair()

TOKENS = {
    "SOL":      "So11111111111111111111111111111111111111112",
    "wBTC":     "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",
    "JUP":      "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "ORCA":     "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
    "RENDER":   "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",
    "DRIFT":    "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7",
    "PENGU":    "2zMMhcVQEXDtdE6vsFS7S7D5oUodfJHE8vd1gnBouauv",
    "FARTCOIN": "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump",
    "TRUMP":    "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN",
    "PYTH":     "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
    "WIF":      "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
}

bot = Bot(token=TELEGRAM_BOT_TOKEN)
positions_ouvertes = {}
positions_short = {}
historique_prix = {nom: [] for nom in TOKENS}
prix_btc_precedent = 0.0
depenses_jour = 0.0
gains_jour = 0.0
bot_actif = True
pertes_consecutives = 0
fear_greed_cache = {"valeur": 50, "label": "Neutral", "timestamp": 0}

async def envoyer_alerte(message, emoji=""):
    try:
        texte = f"{emoji} *SOLANA TRADING BOT*\n{'='*30}\n{message}\n\nHeure: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=texte, parse_mode="Markdown")
        print(f"  Alerte envoyee : {emoji}")
    except TelegramError as e:
        print(f"  Erreur Telegram: {e}")

async def get_fear_greed():
    """Récupère le Fear & Greed Index crypto"""
    global fear_greed_cache
    now = datetime.now().timestamp()
    if now - fear_greed_cache["timestamp"] < 3600:
        return fear_greed_cache
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("https://api.alternative.me/fng/", timeout=10)
            data = res.json()
            valeur = int(data["data"][0]["value"])
            label = data["data"][0]["value_classification"]
            fear_greed_cache = {"valeur": valeur, "label": label, "timestamp": now}
            return fear_greed_cache
    except Exception:
        return fear_greed_cache

async def verifier_correlation_btc(prix_btc_actuel):
    """Vérifie si BTC chute brutalement"""
    global prix_btc_precedent, bot_actif
    if prix_btc_precedent == 0:
        prix_btc_precedent = prix_btc_actuel
        return False
    variation_btc = ((prix_btc_actuel - prix_btc_precedent) / prix_btc_precedent) * 100
    prix_btc_precedent = prix_btc_actuel
    if variation_btc <= -3.0:
        print(f"  ⚠️ BTC chute de {variation_btc:.2f}% - Pause automatique !")
        await envoyer_alerte(f"⚠️ BTC chute de {variation_btc:.2f}%\nPause automatique de 30 minutes !", "🚨")
        bot_actif = False
        await asyncio.sleep(1800)
        bot_actif = True
        await envoyer_alerte("Bot repris après pause BTC !", "✅")
        return True
    return False

async def get_prix(token_address):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, timeout=10)
            data = res.json()
            pairs = data.get("pairs", [])
            if not pairs:
                return 0.0, 0.0
            pair = sorted(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0), reverse=True)[0]
            return float(pair["priceUsd"]), float(pair.get("volume", {}).get("h24", 0) or 0)
        except Exception:
            return 0.0, 0.0

async def get_activite_baleines(token_address):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, timeout=10)
            data = res.json()
            pairs = data.get("pairs", [])
            if not pairs:
                return 0, "neutre"
            pair = sorted(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0), reverse=True)[0]
            txns = pair.get("txns", {})
            h1 = txns.get("h1", {})
            buys_1h = h1.get("buys", 0)
            sells_1h = h1.get("sells", 0)
            volume_1h = float(pair.get("volume", {}).get("h1", 0) or 0)
            price_change_1h = float(pair.get("priceChange", {}).get("h1", 0) or 0)
            score_baleine = 0
            signal_baleine = "neutre"
            if volume_1h > 500000:
                score_baleine += 3
            elif volume_1h > 100000:
                score_baleine += 1
            if buys_1h > sells_1h * 2 and price_change_1h > 0:
                score_baleine += 2
                signal_baleine = "accumulation"
            elif sells_1h > buys_1h * 2 and price_change_1h < 0:
                score_baleine += 2
                signal_baleine = "distribution"
            return score_baleine, signal_baleine
        except Exception:
            return 0, "neutre"

def calculer_score_confiance(nom, rsi, ma7, ma25, macd_line, macd_signal, variation, score_baleine, signal_baleine, fear_greed):
    score = 0
    projet = PROJETS_INFO.get(nom, {"score_base": 5})
    score += projet["score_base"] * 0.3
    if rsi and rsi < 30:
        score += 2
    elif rsi and rsi < 40:
        score += 1
    if macd_line and macd_signal and macd_line > macd_signal:
        score += 1.5
    if ma7 and ma25 and ma7 > ma25:
        score += 1
    if 1.0 <= variation <= 5.0:
        score += 1
    elif variation > 5.0:
        score += 0.5
    if signal_baleine == "accumulation":
        score += score_baleine * 0.5
    elif signal_baleine == "distribution":
        score -= score_baleine * 0.3
    # Fear & Greed bonus
    fg = fear_greed["valeur"]
    if fg <= 25:
        score += 1.5  # Peur extrême = opportunité d'achat
    elif fg >= 75:
        score -= 1.0  # Euphorie = risque élevé
    return min(round(score, 1), 10)

async def executer_swap_jupiter(token_mint, montant_lamports, mode="achat"):
    if not KEYPAIR:
        return False
    try:
        async with httpx.AsyncClient() as client:
            input_mint = SOL_MINT if mode == "achat" else token_mint
            output_mint = token_mint if mode == "achat" else SOL_MINT
            quote_url = (
                f"https://quote-api.jup.ag/v6/quote"
                f"?inputMint={input_mint}&outputMint={output_mint}"
                f"&amount={montant_lamports}&slippageBps=50"
            )
            quote_res = await client.get(quote_url, timeout=10)
            quote = quote_res.json()
            if "error" in quote:
                return False
            swap_res = await client.post(
                "https://quote-api.jup.ag/v6/swap",
                json={
                    "quoteResponse": quote,
                    "userPublicKey": str(KEYPAIR.pubkey()),
                    "wrapAndUnwrapSol": True,
                    "dynamicComputeUnitLimit": True,
                    "prioritizationFeeLamports": 1000,
                },
                timeout=15
            )
            swap_data = swap_res.json()
            if "swapTransaction" not in swap_data:
                return False
            tx_bytes = base58.b58decode(swap_data["swapTransaction"])
            tx = VersionedTransaction.from_bytes(tx_bytes)
            rpc = AsyncClient(RPC_URL)
            result = await rpc.send_raw_transaction(bytes(tx))
            await rpc.close()
            return str(result.value)
    except Exception as e:
        print(f"  Erreur Jupiter: {e}")
        return False

async def ouvrir_short_perps(token, prix, levier=2):
    if not KEYPAIR:
        return False
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                "https://perps-api.jup.ag/v1/open-position",
                json={
                    "owner": str(KEYPAIR.pubkey()),
                    "market": token,
                    "side": "short",
                    "collateralUsd": MISE_SHORT_USDC,
                    "sizeUsd": MISE_SHORT_USDC * levier,
                    "slippageBps": 100,
                    "takeProfit": prix * (1 - TAKE_PROFIT_PCT / 100),
                    "stopLoss": prix * (1 + STOP_LOSS_PCT / 100),
                },
                timeout=15
            )
            data = res.json()
            if "transaction" in data:
                tx_bytes = base58.b58decode(data["transaction"])
                tx = VersionedTransaction.from_bytes(tx_bytes)
                rpc = AsyncClient(RPC_URL)
                result = await rpc.send_raw_transaction(bytes(tx))
                await rpc.close()
                return str(result.value)
            return False
    except Exception as e:
        print(f"  Erreur Perps: {e}")
        return False

def calculer_indicateurs(prix_list):
    if len(prix_list) < 26:
        return None, None, None, None, None, None, None
    s = pd.Series(prix_list)
    rsi = ta.momentum.RSIIndicator(s, window=14).rsi().iloc[-1]
    ma7 = s.rolling(7).mean().iloc[-1]
    ma25 = s.rolling(25).mean().iloc[-1] if len(prix_list) >= 25 else None
    macd = ta.trend.MACD(s)
    macd_line = macd.macd().iloc[-1]
    macd_signal = macd.macd_signal().iloc[-1]
    bb = ta.volatility.BollingerBands(s, window=20)
    bb_high = bb.bollinger_hband().iloc[-1]
    bb_low = bb.bollinger_lband().iloc[-1]
    return round(rsi, 2), round(ma7, 6), round(ma25, 6) if ma25 else None, round(macd_line, 6), round(macd_signal, 6), round(bb_high, 6), round(bb_low, 6)

def signal_technique(rsi, ma7, ma25, variation, macd_line, macd_signal, prix, bb_high, bb_low):
    if rsi is None:
        if variation >= 2.0:
            return "achat_scalp"
        elif variation <= -2.0:
            return "vente_scalp"
        return "neutre"
    macd_haussier = macd_line > macd_signal if macd_line and macd_signal else False
    macd_baissier = macd_line < macd_signal if macd_line and macd_signal else False
    bb_survente = prix <= bb_low if bb_low else False
    bb_surachat = prix >= bb_high if bb_high else False
    if rsi < 35 and variation >= 1.0 and macd_haussier and bb_survente:
        return "achat_scalp"
    elif rsi > 65 and variation <= -1.0 and macd_baissier and bb_surachat:
        return "vente_scalp"
    elif ma25 and ma7 > ma25 and variation >= 0.5 and macd_haussier:
        return "achat_swing"
    elif ma25 and ma7 < ma25 and variation <= -0.5 and macd_baissier:
        return "vente_swing"
    return "neutre"

async def analyser(nom, prix_actuel):
    hist = historique_prix[nom]
    if len(hist) == 0:
        return "neutre", 0.0, None, None, None, None, None, None, None
    precedent = hist[-1]
    variation = ((prix_actuel - precedent) / precedent) * 100
    rsi, ma7, ma25, macd_line, macd_signal, bb_high, bb_low = calculer_indicateurs(hist)
    signal = signal_technique(rsi, ma7, ma25, variation, macd_line, macd_signal, prix_actuel, bb_high, bb_low)
    return signal, variation, rsi, ma7, ma25, macd_line, macd_signal, bb_high, bb_low

async def verifier_sl_tp():
    global gains_jour, pertes_consecutives
    for token, pos in list(positions_ouvertes.items()):
        prix, _ = await get_prix(TOKENS.get(token, ""))
        if prix == 0:
            continue
        var = ((prix - pos["entree"]) / pos["entree"]) * 100
        if prix > pos.get("highest", pos["entree"]):
            pos["highest"] = prix
        trailing_sl = pos.get("highest", pos["entree"]) * (1 - STOP_LOSS_PCT / 100)
        if prix <= trailing_sl:
            mint = TOKENS.get(token)
            lamports = int(pos.get("montant", 0))
            if lamports > 0:
                await executer_swap_jupiter(mint, lamports, mode="vente")
            gains_jour += var * MISE_MAX_SOL / 100
            pertes_consecutives += 1
            await envoyer_alerte(f"TRAILING STOP - *{token}*\nEntree: ${pos['entree']:.4f}\nActuel: ${prix:.4f}\nVar: {var:.2f}%\nPertes consec: {pertes_consecutives}", "🔴")
            del positions_ouvertes[token]
            if pertes_consecutives >= MAX_PERTES_CONSECUTIVES:
                await envoyer_alerte(f"⚠️ {MAX_PERTES_CONSECUTIVES} pertes consécutives!\nPause de 1 heure...", "🚨")
                global bot_actif
                bot_actif = False
                await asyncio.sleep(3600)
                bot_actif = True
                pertes_consecutives = 0
                await envoyer_alerte("Bot repris après pause pertes !", "✅")
        elif var >= TAKE_PROFIT_PCT:
            mint = TOKENS.get(token)
            lamports = int(pos.get("montant", 0))
            if lamports > 0:
                await executer_swap_jupiter(mint, lamports, mode="vente")
            gains_jour += var * MISE_MAX_SOL / 100
            pertes_consecutives = 0
            await envoyer_alerte(f"TAKE PROFIT - *{token}*\nEntree: ${pos['entree']:.4f}\nActuel: ${prix:.4f}\nGain: +{var:.2f}%", "🟢")
            del positions_ouvertes[token]

async def scanner():
    global depenses_jour, bot_actif
    if not bot_actif:
        print("  Bot en pause...")
        return

    fear_greed = await get_fear_greed()
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scan | Fear&Greed: {fear_greed['valeur']} ({fear_greed['label']})")

    # Vérifier corrélation BTC
    prix_btc, _ = await get_prix(TOKENS["wBTC"])
    if prix_btc > 0:
        await verifier_correlation_btc(prix_btc)

    if not bot_actif:
        return

    for nom, adresse in TOKENS.items():
        prix, volume = await get_prix(adresse)
        if prix == 0:
            print(f"  {nom}: indisponible")
            continue

        signal, var, rsi, ma7, ma25, macd_line, macd_signal, bb_high, bb_low = await analyser(nom, prix)
        score_baleine, signal_baleine = await get_activite_baleines(adresse)
        historique_prix[nom].append(prix)
        if len(historique_prix[nom]) > 100:
            historique_prix[nom].pop(0)

        score = calculer_score_confiance(nom, rsi, ma7, ma25, macd_line, macd_signal, var, score_baleine, signal_baleine, fear_greed)
        projet = PROJETS_INFO.get(nom, {"categorie": "?", "solidite": "?"})

        rsi_str = f"RSI:{rsi}" if rsi else "RSI:--"
        macd_str = "↑" if macd_line and macd_signal and macd_line > macd_signal else "↓"
        baleine_str = f"🐋{signal_baleine}" if signal_baleine != "neutre" else ""
        print(f"  {nom:8} ${prix:.4f} ({var:+.2f}%) {rsi_str} MACD:{macd_str} Score:{score} {baleine_str} {signal}")

        montant_lamports = int(MISE_MAX_SOL * 1_000_000_000)
        positions_total = len(positions_ouvertes) + len(positions_short)

        # Mode marché baissier : Fear < 25 = on réduit les mises
        mise_actuelle = montant_lamports
        if fear_greed["valeur"] >= 75:
            mise_actuelle = int(montant_lamports * 0.5)
            print(f"  ⚠️ Euphorie détectée - mise réduite de 50%")

        if signal in ["achat_scalp", "achat_swing"] and nom not in positions_ouvertes and positions_total < MAX_POSITIONS and depenses_jour < BUDGET_JOURNALIER_SOL:
            if score >= SCORE_MIN_TRADE:
                sig = await executer_swap_jupiter(adresse, mise_actuelle, "achat")
                if sig:
                    depenses_jour += MISE_MAX_SOL
                    positions_ouvertes[nom] = {"entree": prix, "type": signal, "montant": mise_actuelle, "highest": prix}
                    await envoyer_alerte(
                        f"{'SCALP' if signal == 'achat_scalp' else 'SWING'} ACHAT - *{nom}*\n"
                        f"Projet: {projet['categorie']} | {projet['solidite']}\n"
                        f"Prix: ${prix:.4f} | +{var:.2f}%\n"
                        f"RSI: {rsi} | MACD: {macd_str}\n"
                        f"Baleines: {signal_baleine} {baleine_str}\n"
                        f"Fear&Greed: {fear_greed['valeur']} ({fear_greed['label']})\n"
                        f"Score: {score}/10\n"
                        f"TP: ${prix*(1+TAKE_PROFIT_PCT/100):.4f} | SL: trailing\n"
                        f"TX: {sig[:20]}...", "⚡" if signal == "achat_scalp" else "📈")
            else:
                print(f"  {nom}: score trop bas ({score}/10)")

        elif signal in ["vente_scalp", "vente_swing"] and nom in SHORT_TOKENS and nom not in positions_short and positions_total < MAX_POSITIONS:
            if score >= SCORE_MIN_TRADE:
                sig = await ouvrir_short_perps(nom, prix, levier=2)
                if sig:
                    positions_short[nom] = {"entree": prix, "type": signal}
                    await envoyer_alerte(
                        f"SHORT - *{nom}*\n"
                        f"Prix: ${prix:.4f} | {var:.2f}%\n"
                        f"RSI: {rsi} | MACD: {macd_str}\n"
                        f"Baleines: {signal_baleine} {baleine_str}\n"
                        f"Fear&Greed: {fear_greed['valeur']} ({fear_greed['label']})\n"
                        f"Score: {score}/10\n"
                        f"TX: {sig[:20]}...", "🔻")

    await verifier_sl_tp()

async def reset_budget():
    global depenses_jour, gains_jour
    while True:
        now = datetime.now()
        if now.hour == 0 and now.minute == 0:
            fg = await get_fear_greed()
            await envoyer_alerte(
                f"📊 RÉSUMÉ QUOTIDIEN\n"
                f"SOL dépensés: {depenses_jour:.3f}\n"
                f"Gains estimés: {gains_jour:.3f} SOL\n"
                f"Fear&Greed: {fg['valeur']} ({fg['label']})\n"
                f"Positions: {len(positions_ouvertes)}", "📊")
            depenses_jour = 0.0
            gains_jour = 0.0
        await asyncio.sleep(60)

async def cmd_solde(update, context):
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return
    try:
        rpc = AsyncClient(RPC_URL)
        solde = await rpc.get_balance(KEYPAIR.pubkey())
        await rpc.close()
        sol = solde.value / 1_000_000_000
        fg = await get_fear_greed()
        await update.message.reply_text(
            f"💰 *Solde du wallet*\n"
            f"SOL: {sol:.4f} (~{sol*82:.2f}€)\n"
            f"Positions: {len(positions_ouvertes)}\n"
            f"Shorts: {len(positions_short)}\n"
            f"Fear&Greed: {fg['valeur']} ({fg['label']})\n"
            f"Pertes consec: {pertes_consecutives}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"Erreur: {e}")

async def cmd_status(update, context):
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return
    if not positions_ouvertes and not positions_short:
        await update.message.reply_text("Aucune position ouverte 😴")
        return
    msg = "📊 *Positions :*\n\n"
    for token, pos in positions_ouvertes.items():
        prix, _ = await get_prix(TOKENS.get(token, ""))
        var = ((prix - pos["entree"]) / pos["entree"]) * 100 if prix else 0
        msg += f"📈 *{token}*\n${pos['entree']:.4f} → ${prix:.4f} | {var:+.2f}%\n\n"
    for token, pos in positions_short.items():
        prix, _ = await get_prix(TOKENS.get(token, ""))
        var = ((pos["entree"] - prix) / pos["entree"]) * 100 if prix else 0
        msg += f"🔻 *{token}* (short)\n${pos['entree']:.4f} → ${prix:.4f} | {var:+.2f}%\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_projets(update, context):
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return
    msg = "🔍 *Projets surveillés :*\n\n"
    for nom, info in PROJETS_INFO.items():
        msg += f"*{nom}* ({info['categorie']}) Score:{info['score_base']}/10\n{info['description']}\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_pause(update, context):
    global bot_actif
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return
    bot_actif = False
    await update.message.reply_text("⏸️ Bot mis en pause !")

async def cmd_reprendre(update, context):
    global bot_actif
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return
    bot_actif = True
    await update.message.reply_text("▶️ Bot repris !")

async def cmd_baleines(update, context):
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return
    msg = "🐋 *Activité baleines :*\n\n"
    for nom, adresse in TOKENS.items():
        score, signal = await get_activite_baleines(adresse)
        if signal != "neutre":
            msg += f"*{nom}*: {signal} (score: {score})\n"
    if msg == "🐋 *Activité baleines :*\n\n":
        msg += "Aucune activité baleine détectée"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def main():
    print("="*50)
    print("  BOT TRADING SOLANA V5 - @Soltader_bot")
    print("  RSI+MACD+BB+Baleines+Fear&Greed+BTC corr")
    print("  Pause auto pertes | Mode eupho/peur")
    print("="*50)
    if KEYPAIR:
        print(f"  Wallet: {str(KEYPAIR.pubkey())[:20]}...")
    else:
        print("  ⚠️ Clé privée non chargée !")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("solde", cmd_solde))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("projets", cmd_projets))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("reprendre", cmd_reprendre))
    app.add_handler(CommandHandler("baleines", cmd_baleines))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    fg = await get_fear_greed()
    await envoyer_alerte(
        f"Bot V5 demarre!\n"
        f"✅ Fear&Greed: {fg['valeur']} ({fg['label']})\n"
        f"✅ Corrélation BTC active\n"
        f"✅ Pause auto après {MAX_PERTES_CONSECUTIVES} pertes\n"
        f"✅ Baleines + Score confiance\n"
        f"Commandes: /solde /status /projets /pause /reprendre /baleines\n"
        f"SL: {STOP_LOSS_PCT}% | TP: {TAKE_PROFIT_PCT}%", "🚀")

    asyncio.create_task(reset_budget())
    while True:
        await scanner()
        await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())