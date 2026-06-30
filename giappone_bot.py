"""
Bot Telegram - Giappone Discovery Turno 1
Staff assistant per il viaggio 01/07/2026 - 16/07/2026

SETUP (TUTTO GRATIS):
1. Crea un bot su Telegram tramite @BotFather → ottieni il TOKEN
2. Crea un account su https://console.groq.com → genera una API key gratuita
3. Installa le dipendenze:
   pip install python-telegram-bot groq
4. Imposta le variabili d'ambiente:
   export TELEGRAM_TOKEN="il_tuo_token"
   export GROQ_API_KEY="la_tua_api_key_groq"
5. Avvia il bot:
   python giappone_bot.py
"""

import os
import logging
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    ContextTypes, filters, CallbackQueryHandler
)
from groq import Groq

# ─── CONFIGURAZIONE ───────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "INSERISCI_QUI_IL_TOKEN")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY",   "INSERISCI_QUI_LA_API_KEY_GROQ")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── GRUPPI COLORE ────────────────────────────────────────────────────────────
GRUPPI = {
    "🔴 ROSSO": [
        "CIMMINO Viola", "DI VINCENZO Erica Marizol", "GALLO Erica",
        "BUTTINO Desiree Fatima", "MORGESE Ilaria", "PIERGIACOMI Priscilla",
        "DI GIACOPO Lucrezia", "ERCOLI Eleonora", "DI GIACOPO Anastasia",
        "BACCARO Irene", "FROSINI Ilaria", "GRILLO Lucrezia",
        "VITALETTI Davide", "BELLUCCI Francesco", "DEL GIULIO Christian",
        "AGOSTINI Nicolò", "MACCAGNAN Tommaso", "MANCINO Gianluca",
        "FERRARI Tobia", "CARBONE Francesco", "MACCARRONE Francesco",
    ],
    "🔵 AZZURRO": [
        "ZOPPI Eleonora", "RANISI Giulia", "ZOPPI Maurizio",
        "BONELLI Martina", "LATO Giorgia Francesca", "MARINO Caterina", "POGGI Alice",
        "PALAZZO Giorgia", "SCIALABBA Anna", "MUSCAGLIONE Cecilia",
        "PANNACCI Cesira", "CORRADINI Giordano", "CORRADINI Luca",
        "DORONZO Michele", "BIFULCO Francesco Andrea", "LALA Matteo",
        "FERRARA Mattia", "NAPOLETANO Rodolfo", "CUCINO Francesco",
        "GIORDANO Gabriele", "LUCCI Christian", "IACOVELLA Leonardo Xiangxing",
    ],
}

# ─── PROGRAMMA GIORNALIERO ────────────────────────────────────────────────────
PROGRAMMA = {
    date(2026, 7, 2):  {
        "titolo": "✈️ Arrivo a Osaka",
        "attivita": "Arrivo all'aeroporto di Osaka Kansai alle 19:05 (volo TK086). Trasferimento in pullman all'Oriental Hotel Kyoto Rokujo.",
        "descrizione": "Dopo un lungo viaggio attraverso Istanbul, atterrate nella grande area metropolitana di Osaka-Kyoto. Il tragitto verso l'hotel vi darà i primi scorci del Giappone reale, molto diverso dai cliché: capannoni industriali, insegne al neon, reti ferroviarie sopraelevate."
    },
    date(2026, 7, 3):  {
        "titolo": "📚 Scuola + Arashiyama",
        "attivita": "Corso di giapponese 3 ore (Campus Plaza, 9:00-12:00, aule R4 F6 / R5 F6). Pomeriggio: Arashiyama + Noodles Party (bus).",
        "descrizione": "Arashiyama è il quartiere bambù di Kyoto: il celebre boschetto di bambù gigante è uno dei simboli del Giappone. Lungo il fiume Oi si trovano il Tempio Tenryu-ji (patrimonio UNESCO) e il pittoresco ponte Togetsukyo. La noodles party è un'introduzione pratica alla cucina locale — ramen, udon e soba sono le basi."
    },
    date(2026, 7, 4):  {
        "titolo": "📚 Scuola full day",
        "attivita": "Corso di giapponese 6 ore (sede Saiin/Minsai, 9:00-11:30 e 13:00-16:30).",
        "descrizione": "Giornata interamente dedicata alla Kyoto Minsai Japanese Language School. Il sabato è il giorno più intenso di studio — le 6 ore includono grammatica, conversazione, calligrafia e attività interattive con gli studenti locali."
    },
    date(2026, 7, 5):  {
        "titolo": "🏯 Osaka",
        "attivita": "Gita a Osaka: Castello → Kuromon Ichiba Market (pranzo) → Tsutenkaku → Nipponbashi → Dotonbori → eventuale Umekita Park. (Keihan line)",
        "descrizione": "Osaka è la città più vivace del Giappone, famosa per il cibo e il carattere schietto degli abitanti. Il Castello è una ricostruzione del 1931 dell'originale del 1583. Kuromon è il 'ventre di Osaka': 170 bancarelle di pesce fresco, frutti esotici e street food. Dotonbori è il cuore della movida, con le sue insegne luminose enormi (il famoso Glico Man)."
    },
    date(2026, 7, 6):  {
        "titolo": "🍵 Kyoto sacra",
        "attivita": "Alba facoltativa al Nishi Hongan-ji (cerimonia ore 6:00) + Cerimonia del Tè ore 10:30 + Pranzo al Mercato Nishiki + Padiglione d'Oro (Kinkaku-ji) + Shopping.",
        "descrizione": "Nishi Hongan-ji è il tempio madre del Buddhismo Shin, con cerimonie mattutine alle 6:00 aperte al pubblico — un'esperienza rara e silenziosa. La cerimonia del tè (chado) è una pratica codificata da 500 anni: ogni gesto ha un significato preciso. Nishiki è il 'mercato della cucina di Kyoto', soprannominato 'la cucina di Kyoto'. Il Kinkaku-ji (Padiglione d'Oro) è il monumento più fotografato del Giappone."
    },
    date(2026, 7, 7):  {
        "titolo": "📚 Scuola + Nijo",
        "attivita": "Corso 3 ore (Campus Plaza, 9:00-12:00). Pomeriggio: Castello Nijo + Shopping.",
        "descrizione": "Il Castello Nijo fu residenza degli shogun Tokugawa a Kyoto nel XVII secolo. È famoso per i 'corridoi usignolo' — i pavimenti scricchiolano apposta per segnalare eventuali intrusi. Oggi è patrimonio UNESCO. Il pomeriggio libero è ideale per i negozi di Shijo-Kawaramachi."
    },
    date(2026, 7, 8):  {
        "titolo": "📚 Scuola + TeamLab + Fushimi Inari",
        "attivita": "Corso 3 ore (Campus Plaza, 9:00-12:00). Pomeriggio: TeamLab Biovortex + Fushimi Inari.",
        "descrizione": "TeamLab Biovortex è una delle installazioni di arte digitale immersiva più spettacolari del Giappone — luci, proiezioni e ambienti interattivi che sembrano un sogno. Fushimi Inari è il santuario delle migliaia di torii arancioni che salgono lungo la collina — la salita completa è di 4 km, si può fare anche parzialmente."
    },
    date(2026, 7, 9):  {
        "titolo": "📚 Scuola + Kiyomizudera + Gion + Karaoke",
        "attivita": "Corso 3 ore (Campus Plaza, 9:00-12:00). Pomeriggio: Kiyomizudera + Gion + Karaoke.",
        "descrizione": "Kiyomizudera è uno dei templi più antichi e belli di Kyoto (778 d.C.), costruito su una scarpata con una terrazza di legno a strapiombo sulla foresta — 'saltare dalla terrazza di Kiyomizu' è un modo di dire giapponese per 'fare un salto nel vuoto'. Gion è il quartiere delle geishe, con le sue stradine di pietra e le case da tè (ochaya) del periodo Edo."
    },
    date(2026, 7, 10): {
        "titolo": "🦌 Nara + Uji",
        "attivita": "Giornata intera a Nara e Uji.",
        "descrizione": "Nara fu la prima capitale permanente del Giappone (710-784). Il Parco di Nara ospita circa 1.200 cervi liberi considerati sacri — si lasciano avvicinare e sfamare con crackers appositi. Il Todai-ji contiene il più grande Buddha in bronzo del mondo (15 metri). Uji è famosa per il tè matcha di altissima qualità e per il Byodoin, il tempio stampato sulla moneta da 10 yen."
    },
    date(2026, 7, 11): {
        "titolo": "📚 Scuola full day",
        "attivita": "Corso 6 ore (Saiin/Minsai, 9:00-11:30 e 13:00-16:30). Davide Di Stefano OFF.",
        "descrizione": "Seconda giornata full day di scuola. Gli studenti sono ormai abituati alla routine della scuola giapponese. Le attività del pomeriggio includono spesso lavori di gruppo con studenti giapponesi."
    },
    date(2026, 7, 12): {
        "titolo": "📚 Scuola full day",
        "attivita": "Corso 6 ore (Saiin/Minsai, 9:00-11:30 e 13:00-16:30). Francesco e Francesca OFF.",
        "descrizione": "Ultima giornata full day di scuola prima del weekend a Tokyo. I ragazzi riceveranno l'attestato di frequenza. Buon momento per raccogliere i contatti dei compagni giapponesi."
    },
    date(2026, 7, 13): {
        "titolo": "🚄 Nagoya → Tokyo",
        "attivita": "Shinkansen Kyoto→Nagoya ore 08:54. Nagoya: Castello + Osu Kannon. Shinkansen Nagoya→Tokyo ore 14:29. Sera: Tokyo Metropolitan Government Building + Shinjuku.",
        "descrizione": "Prima esperienza sullo Shinkansen (treno proiettile) — viaggia a 300 km/h con puntualità al secondo. Nagoya ospita uno dei castelli meglio restaurati del Giappone, con i celebri delfini dorati sul tetto. Osu Kannon è un tempio immerso in un quartiere pop pieno di negozietti vintage. La sera, la terrazza gratuita del Tokyo Metropolitan Government Building a 243 metri offre una vista a 360° su tutta la megalopoli."
    },
    date(2026, 7, 14): {
        "titolo": "🗼 Tokyo",
        "attivita": "Mattina: Shibuya + Tempio Meiji + Harajuku + Tokyo Tower. Pomeriggio/sera: Crociera Odaiba + cena Odaiba Bay.",
        "descrizione": "Shibuya Crossing è l'incrocio pedonale più trafficato del mondo — a ogni verde attraversano fino a 3.000 persone. Il Tempio Meiji è un'oasi di foresta dentro la metropoli, dedicato all'imperatore Meiji. Harajuku è la capitale mondiale della moda giovanile estrema. La crociera nella baia di Odaiba al tramonto offre una vista spettacolare sullo skyline di Tokyo e sul Rainbow Bridge."
    },
    date(2026, 7, 15): {
        "titolo": "🎌 Tokyo + Partenza",
        "attivita": "Mattina: Akihabara + Asakusa. Check-out hotel. Volo di rientro TK199 da Tokyo Haneda ore 21:45.",
        "descrizione": "Akihabara è il paradiso dell'elettronica e dell'anime/manga — negozi su 8 piani di action figure, videogame vintage, fumetti. Asakusa è il quartiere più antico di Tokyo: il Tempio Sensoji (645 d.C.) e la via Nakamise con i souvenir tradizionali. La sera si parte per Istanbul con Turkish Airlines."
    },
    date(2026, 7, 16): {
        "titolo": "🏠 Rientro a Roma",
        "attivita": "Arrivo Istanbul ore 05:05 (TK199). Volo TK1861 Istanbul→Roma ore 07:40. Arrivo Roma Fiumicino T3 ore 09:20.",
        "descrizione": "Scalo tecnico a Istanbul. Il volo di rientro è breve (2h40). All'arrivo a Fiumicino Terminal 3 i ragazzi saranno accolti dalle famiglie."
    },
}

# ─── BASE DI CONOSCENZA ───────────────────────────────────────────────────────
KNOWLEDGE_BASE = """
Sei l'assistente ufficiale dello staff del viaggio GIAPPONE DISCOVERY organizzato da Accademia Britannica / Travel Experts.
Rispondi sempre in italiano, in modo chiaro e conciso. Sei riservato a uso interno staff.
Per modifiche al programma o al rooming, proponi la modifica e chiedi conferma prima di applicarla.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INFORMAZIONI GENERALI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Viaggio: Giappone Discovery - Turno 1
Date: 01 luglio 2026 → 16 luglio 2026
Totale partecipanti: 43 (inclusi assistenti familiari)
Booking ref: XUR58X | Voli ref: TLC8KA
TL Staff: Davide Di Stefano, Francesco Chiappetta, Francesca Guerrato

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VOLI - TURKISH AIRLINES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANDATA:
  TK1864 | 01/07 | Roma FCO T3 20:00 → Istanbul 23:35
  TK086  | 02/07 | Istanbul 02:25 → Osaka Kansai T1 19:05
RITORNO:
  TK199  | 15/07 | Tokyo Haneda T3 21:45 → Istanbul 16/07 05:05
  TK1861 | 16/07 | Istanbul 07:40 → Roma FCO T3 09:20

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOTEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KYOTO: Oriental Hotel Kyoto Rokujo ★★★★ (camere triple)
TOKYO: Oriental Hotel Tokyo Bay ★★★★★ (camere quadruple, weekend 13-15 lug)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GRUPPI COLORE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 ROSSO (21 persone - stanze 1-4 e 12-14):
CIMMINO Viola, DI VINCENZO Erica Marizol, GALLO Erica,
BUTTINO Desiree Fatima, MORGESE Ilaria, PIERGIACOMI Priscilla,
DI GIACOPO Lucrezia, ERCOLI Eleonora, DI GIACOPO Anastasia,
BACCARO Irene, FROSINI Ilaria, GRILLO Lucrezia,
VITALETTI Davide, BELLUCCI Francesco, DEL GIULIO Christian,
AGOSTINI Nicolò, MACCAGNAN Tommaso, MANCINO Gianluca,
FERRARI Tobia, CARBONE Francesco, MACCARRONE Francesco

🔵 AZZURRO (22 persone - stanze 5-11):
ZOPPI Eleonora, RANISI Giulia, ZOPPI Maurizio,
BONELLI Martina, LATO Giorgia Francesca, MARINO Caterina, POGGI Alice,
PALAZZO Giorgia, SCIALABBA Anna, MUSCAGLIONE Cecilia,
PANNACCI Cesira, CORRADINI Giordano, CORRADINI Luca,
DORONZO Michele, BIFULCO Francesco Andrea, LALA Matteo,
FERRARA Mattia, NAPOLETANO Rodolfo, CUCINO Francesco,
GIORDANO Gabriele, LUCCI Christian, IACOVELLA Leonardo Xiangxing

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROOMING KYOTO (triple) - Oriental Hotel Kyoto Rokujo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stanza 1:  CIMMINO Viola | DI VINCENZO Erica Marizol | GALLO Erica
Stanza 2:  BUTTINO Desiree Fatima | MORGESE Ilaria | PIERGIACOMI Priscilla
Stanza 3:  DI GIACOPO Lucrezia | ERCOLI Eleonora | DI GIACOPO Anastasia
Stanza 4:  BACCARO Irene | FROSINI Ilaria | GRILLO Lucrezia
Stanza 5:  ZOPPI Eleonora | ZOPPI Maurizio | RANISI Giulia
Stanza 6:  BONELLI Martina | LATO Giorgia Francesca | MARINO Caterina | POGGI Alice
Stanza 7:  PALAZZO Giorgia | SCIALABBA Anna | MUSCAGLIONE Cecilia
Stanza 8:  PANNACCI Cesira | CORRADINI Giordano | CORRADINI Luca
Stanza 9:  DORONZO Michele | BIFULCO Francesco Andrea | LALA Matteo
Stanza 10: FERRARA Mattia | NAPOLETANO Rodolfo | CUCINO Francesco
Stanza 11: GIORDANO Gabriele | LUCCI Christian | IACOVELLA Leonardo Xiangxing
Stanza 12: VITALETTI Davide | BELLUCCI Francesco | DEL GIULIO Christian
Stanza 13: AGOSTINI Nicolò | MACCAGNAN Tommaso | MANCINO Gianluca
Stanza 14: FERRARI Tobia | CARBONE Francesco | MACCARRONE Francesco

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROOMING TOKYO (quadruple) - Oriental Hotel Tokyo Bay
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stanza 1:  CIMMINO Viola | DI VINCENZO Erica Marizol | GALLO Erica | BUTTINO Desiree Fatima
Stanza 2:  PIERGIACOMI Priscilla | DI GIACOPO Lucrezia | ERCOLI Eleonora | DI GIACOPO Anastasia
Stanza 3:  MORGESE Ilaria | BACCARO Irene | FROSINI Ilaria | GRILLO Lucrezia
Stanza 4:  ZOPPI Eleonora | RANISI Giulia | ZOPPI Maurizio
Stanza 5:  BONELLI Martina | LATO Giorgia Francesca | MARINO Caterina | POGGI Alice
Stanza 6:  PALAZZO Giorgia | SCIALABBA Anna | MUSCAGLIONE Cecilia
Stanza 7:  PANNACCI Cesira | CORRADINI Giordano | CORRADINI Luca
Stanza 8:  DORONZO Michele | BIFULCO Francesco Andrea | LALA Matteo | FERRARA Mattia
Stanza 9:  NAPOLETANO Rodolfo | CUCINO Francesco | GIORDANO Gabriele | LUCCI Christian
Stanza 10: IACOVELLA Leonardo Xiangxing | VITALETTI Davide | BELLUCCI Francesco | DEL GIULIO Christian
Stanza 11: AGOSTINI Nicolò | MACCAGNAN Tommaso | MANCINO Gianluca | FERRARI Tobia
Stanza 12: CARBONE Francesco | MACCARRONE Francesco

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INFO MEDICHE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LALA Matteo         → Allergico alla penicillina
LATO Giorgia F.     → Intollerante al lattosio, allergia polvere e gatti, asmatica
MORGESE Ilaria      → Intolleranza al lattosio
DI GIACOPO Lucrezia → Allergia alla polvere e acari
PALAZZO Giorgia     → Allergia acari, polvere, graminacee, asma
SCIALABBA Anna      → Allergia acari della polvere, DSA, ADHD con terapia farmacologica
CORRADINI Giordano  → Disabile, terapia depilino (assistenti: Luca Corradini + Pannacci Cesira)
ZOPPI Eleonora      → Disabile, terapia risperdal (assistenti: Zoppi Maurizio + Ranisi Giulia)
MACCARRONE Francesco → Diabete tipo 1, microinfusore insulinico (verificare frigorifero in stanza)
MANCINO Gianluca    → Sordità neurosensoriale bilaterale, usa apparecchi acustici
POGGI Alice         → Disabile (nulla di clinicamente rilevante)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MATERIALE CONSEGNATO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ogni partecipante riceve: carta prepagata Mastercard (€220) + carta ICOCA trasporti + braccialetto colorato
Numeri carta: 00806 CIMMINO → 00848 MACCARRONE (assegnate in ordine di stanza)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOTE OPERATIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- IACOVELLA Leonardo: parte da Roma ma rientra su Cagliari
- MACCARRONE Francesco: diabetico con microinfusore — verificare frigorifero disponibile
- Modifiche a programma o rooming: lo staff le comunica via chat, il bot le registra e le riporta
"""

# ─── STATO APPELLO ────────────────────────────────────────────────────────────
appello_state: dict[int, dict] = {}
# Struttura: { user_id: { "gruppo": "🔴 ROSSO", "nomi": [...], "indice": 0, "presenti": [], "assenti": [] } }

# Modifiche registrate in sessione
modifiche_log: list[str] = []

# Storico conversazioni AI
conversation_history: dict[int, list] = {}

groq_client = Groq(api_key=GROQ_API_KEY)

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def get_programma_oggi() -> str:
    oggi = date.today()
    if oggi in PROGRAMMA:
        p = PROGRAMMA[oggi]
        return (
            f"📅 *Oggi — {oggi.strftime('%d/%m/%Y')}*\n"
            f"*{p['titolo']}*\n\n"
            f"*Attività:* {p['attivita']}\n\n"
            f"*Info:* {p['descrizione']}"
        )
    return f"Nessun programma registrato per oggi ({oggi.strftime('%d/%m/%Y')})."

def get_programma_data(d: date) -> str:
    if d in PROGRAMMA:
        p = PROGRAMMA[d]
        return (
            f"📅 *{d.strftime('%d/%m/%Y')}*\n"
            f"*{p['titolo']}*\n\n"
            f"*Attività:* {p['attivita']}\n\n"
            f"*Info:* {p['descrizione']}"
        )
    return f"Nessun programma per il {d.strftime('%d/%m/%Y')}."

# ─── COMANDI ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Ciao! Sono l'assistente staff *Giappone Discovery - Turno 1*.\n\n"
        "Puoi scrivermi in linguaggio libero oppure usare questi comandi:\n\n"
        "📅 /oggi — programma e descrizione di oggi\n"
        "📢 /appello — appello presenti per colore\n"
        "📋 /modifiche — vedi le modifiche registrate\n"
        "❓ /help — esempi di domande\n"
        "🔄 /reset — cancella cronologia chat",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 *Esempi di domande:*\n"
        "• \"In che stanza è LALA Matteo a Kyoto?\"\n"
        "• \"Chi ha allergie alimentari?\"\n"
        "• \"Cosa facciamo il 9 luglio?\"\n"
        "• \"Numero carta di Erica Gallo?\"\n"
        "• \"Chi è nel gruppo rosso?\"\n"
        "• \"Sposta FERRARA Mattia dalla stanza 10 alla 9 a Kyoto\"\n"
        "• \"A che ora parte il volo di rientro?\"\n"
        "• \"Chi ha il diabete?\"\n\n"
        "Oppure usa /appello per fare l'appello interattivo.",
        parse_mode="Markdown"
    )

async def oggi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    testo = get_programma_oggi()
    await update.message.reply_text(testo, parse_mode="Markdown")

async def modifiche_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not modifiche_log:
        await update.message.reply_text("Nessuna modifica registrata in questa sessione.")
    else:
        testo = "📋 *Modifiche registrate:*\n\n" + "\n".join(f"• {m}" for m in modifiche_log)
        await update.message.reply_text(testo, parse_mode="Markdown")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    appello_state.pop(user_id, None)
    await update.message.reply_text("✅ Cronologia cancellata.")

# ─── APPELLO ──────────────────────────────────────────────────────────────────
async def appello_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔴 ROSSO (21 persone)", callback_data="appello_ROSSO")],
        [InlineKeyboardButton("🔵 AZZURRO (22 persone)", callback_data="appello_AZZURRO")],
    ]
    await update.message.reply_text(
        "📢 *Appello* — Seleziona il gruppo:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # Avvio appello
    if data.startswith("appello_"):
        colore = "🔴 ROSSO" if "ROSSO" in data else "🔵 AZZURRO"
        nomi = GRUPPI[colore].copy()
        appello_state[user_id] = {
            "gruppo": colore,
            "nomi": nomi,
            "indice": 0,
            "presenti": [],
            "assenti": [],
        }
        await _invia_prossimo_nome(query.message, user_id)
        return

    # Risposta appello
    if data in ("presente", "assente", "salta"):
        stato = appello_state.get(user_id)
        if not stato:
            await query.message.reply_text("Nessun appello in corso. Usa /appello.")
            return

        idx = stato["indice"]
        nome_corrente = stato["nomi"][idx]

        if data == "presente":
            stato["presenti"].append(nome_corrente)
        elif data == "assente":
            stato["assenti"].append(nome_corrente)
        # "salta" non aggiunge a nessuna lista

        stato["indice"] += 1

        if stato["indice"] >= len(stato["nomi"]):
            # Appello completato
            gruppo = stato["gruppo"]
            presenti = stato["presenti"]
            assenti = stato["assenti"]
            saltati = len(stato["nomi"]) - len(presenti) - len(assenti)
            del appello_state[user_id]

            testo = (
                f"✅ *Appello {gruppo} completato!*\n\n"
                f"*Presenti ({len(presenti)}):* {', '.join(presenti) if presenti else '—'}\n\n"
                f"*Assenti ({len(assenti)}):* {', '.join(assenti) if assenti else '—'}\n"
            )
            if saltati:
                testo += f"*Saltati:* {saltati}\n"
            await query.message.reply_text(testo, parse_mode="Markdown")
        else:
            await _invia_prossimo_nome(query.message, user_id)

async def _invia_prossimo_nome(message, user_id: int):
    stato = appello_state[user_id]
    idx = stato["indice"]
    totale = len(stato["nomi"])
    nome = stato["nomi"][idx]
    gruppo = stato["gruppo"]

    keyboard = [[
        InlineKeyboardButton("✅ Presente", callback_data="presente"),
        InlineKeyboardButton("❌ Assente",  callback_data="assente"),
        InlineKeyboardButton("⏭ Salta",    callback_data="salta"),
    ]]
    await message.reply_text(
        f"{gruppo} — {idx+1}/{totale}\n\n👤 *{nome}*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ─── MESSAGGI LIBERI (AI) ─────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Se c'è un appello in corso, non processare come domanda AI
    if user_id in appello_state:
        await update.message.reply_text("Hai un appello in corso — usa i pulsanti per rispondere, o /reset per annullarlo.")
        return

    user_text = update.message.text

    # Rilevamento richiesta programma di oggi nel testo
    if any(k in user_text.lower() for k in ["cosa facciamo oggi", "programma di oggi", "oggi cosa"]):
        await update.message.reply_text(get_programma_oggi(), parse_mode="Markdown")
        return

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": user_text})
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        # Arricchisci il contesto con il programma completo
        programma_testo = "\n".join(
            f"{d.strftime('%d/%m')}: {v['titolo']} — {v['attivita']}"
            for d, v in PROGRAMMA.items()
        )
        system = KNOWLEDGE_BASE + f"\n\nPROGRAMMA COMPLETO:\n{programma_testo}"

        # Aggiungi modifiche registrate al contesto
        if modifiche_log:
            system += "\n\nMODIFICHE REGISTRATE DALLO STAFF:\n" + "\n".join(f"- {m}" for m in modifiche_log)

        response = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system},
                *conversation_history[user_id]
            ]
        )

        reply = response.choices[0].message.content

        # Se la risposta sembra una modifica confermata, loggala
        if any(k in user_text.lower() for k in ["sposta", "cambia", "modifica", "aggiorna", "togli", "aggiungi"]):
            modifiche_log.append(f"[{date.today()}] {user_text}")

        conversation_history[user_id].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)

    except Exception as e:
        logger.error(f"Errore API: {e}")
        await update.message.reply_text("⚠️ Errore temporaneo. Riprova tra qualche secondo.")

# ─── AVVIO ────────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("help",     help_command))
    app.add_handler(CommandHandler("oggi",     oggi_command))
    app.add_handler(CommandHandler("appello",  appello_command))
    app.add_handler(CommandHandler("modifiche",modifiche_command))
    app.add_handler(CommandHandler("reset",    reset))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Bot avviato.")
    app.run_polling()

if __name__ == "__main__":
    main()
