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
import json
import logging
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    ContextTypes, filters, CallbackQueryHandler
)
import anthropic
import gspread
from google.oauth2.service_account import Credentials

# ─── CONFIGURAZIONE ───────────────────────────────────────────────────────────
TELEGRAM_TOKEN        = os.environ.get("TELEGRAM_TOKEN",          "INSERISCI_QUI_IL_TOKEN")
ANTHROPIC_API_KEY     = os.environ.get("ANTHROPIC_API_KEY",       "INSERISCI_QUI_LA_API_KEY_ANTHROPIC")
GOOGLE_CREDS_JSON     = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
ROOMING_SHEET_IDS = [
    "1kXJUY2Q51cqV1pnzfCekYVq1cXy9xcdrUJAwwWpDgkU",  # Rooming turno 1
    "1dX9ZtULby3luzCImaFL6qNsI2TuvCflKEejBgVRCMEE",  # Secondo foglio
]

# ─── GOOGLE SHEETS CLIENT ─────────────────────────────────────────────────────
def get_sheets_client():
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds)

def _get_section_ranges(all_values):
    """
    Identifica le sezioni del foglio. Ogni riga con 'STANZA' come intestazione
    apre una nuova sezione (es. Kyoto e Tokyo sullo stesso tab).
    Restituisce lista di dict con: header_row, stanza_col, end_row.
    """
    sections = []
    for i, row in enumerate(all_values):
        for j, cell in enumerate(row):
            if cell.strip().upper() == "STANZA":
                sections.append({"header_row": i, "stanza_col": j})
                break  # una sola colonna STANZA per riga
    for idx in range(len(sections)):
        sections[idx]["end_row"] = (
            sections[idx + 1]["header_row"] if idx + 1 < len(sections) else len(all_values)
        )
    return sections

def _conta_stanza(all_values, sec, stanza_num_str):
    """Conta quante righe nella sezione hanno esattamente quel numero di stanza."""
    count = 0
    stanza_col = sec["stanza_col"]
    for i in range(sec["header_row"] + 1, sec["end_row"]):
        if i >= len(all_values):
            break
        row = all_values[i]
        if len(row) > stanza_col and row[stanza_col].strip() == stanza_num_str.strip():
            count += 1
    return count

def sposta_in_sheet(cognome: str, nome: str, nuova_stanza: str) -> str:
    """
    Aggiorna STANZA per tutte le occorrenze di cognome+nome.
    Controlla capienza: blocca se la stanza destinazione è già piena
    (capienza derivata dall'occupazione attuale del foglio, opzione B).
    """
    try:
        gc = get_sheets_client()
        cognome_up = cognome.strip().upper()
        nome_up    = nome.strip().upper()
        aggiornamenti = []
        blocchi = []

        for sheet_id in ROOMING_SHEET_IDS:
            sh = gc.open_by_key(sheet_id)
            for ws in sh.worksheets():
                all_values = ws.get_all_values()
                sections = _get_section_ranges(all_values)

                for sec_idx, sec in enumerate(sections):
                    stanza_col = sec["stanza_col"]
                    label = f"{ws.title} sez.{sec_idx + 1}"

                    # Cerca la persona in questa sezione
                    persona_row  = None
                    stanza_attuale = None
                    for i in range(sec["header_row"] + 1, sec["end_row"]):
                        if i >= len(all_values):
                            break
                        row = all_values[i]
                        for col_c in range(min(5, len(row) - 1)):
                            if (row[col_c].strip().upper() == cognome_up and
                                    row[col_c + 1].strip().upper() == nome_up):
                                persona_row  = i
                                stanza_attuale = row[stanza_col] if len(row) > stanza_col else ""
                                break
                        if persona_row is not None:
                            break

                    if persona_row is None:
                        continue

                    # Controllo capienza (opzione B: conta persone dal foglio)
                    count_target = _conta_stanza(all_values, sec, nuova_stanza)
                    count_source = _conta_stanza(all_values, sec, stanza_attuale) if stanza_attuale else 0

                    if count_target >= 4:
                        blocchi.append(
                            f"❌ {label}: stanza {nuova_stanza} ha già {count_target} persone "
                            f"(quadrupla piena). Spostamento bloccato."
                        )
                        continue

                    if count_target >= count_source:
                        blocchi.append(
                            f"❌ {label}: stanza {nuova_stanza} ha {count_target} persone "
                            f"(≥ stanza {stanza_attuale} con {count_source}). "
                            f"Usa /scambia {cognome} COGNOME2 per scambiare tra stanze della stessa capienza."
                        )
                        continue

                    # Esegui l'aggiornamento
                    ws.update_cell(persona_row + 1, stanza_col + 1, nuova_stanza)
                    aggiornamenti.append(
                        f"{label}: stanza {stanza_attuale} → {nuova_stanza} (riga {persona_row + 1})"
                    )

        parts = []
        if aggiornamenti:
            parts.append(f"✅ *{cognome} {nome}* → stanza *{nuova_stanza}*\n" + "\n".join(aggiornamenti))
        if blocchi:
            parts.append("\n".join(blocchi))
        if not parts:
            parts.append(f"⚠️ {cognome} {nome} non trovato/a in nessun foglio rooming.")
        return "\n\n".join(parts)

    except Exception as e:
        return f"❌ Errore: {type(e).__name__}: {str(e)[:200]}"

def scambia_in_sheet(cognome1: str, cognome2: str) -> str:
    """
    Scambia le stanze di due persone cercate per solo cognome.
    Funziona sezione per sezione (Kyoto e Tokyo separatamente).
    Se un cognome è ambiguo (più persone), richiede di usare /sposta col nome completo.
    """
    try:
        gc = get_sheets_client()
        c1_up = cognome1.strip().upper()
        c2_up = cognome2.strip().upper()
        scambi  = []
        avvisi  = []

        for sheet_id in ROOMING_SHEET_IDS:
            sh = gc.open_by_key(sheet_id)
            for ws in sh.worksheets():
                all_values = ws.get_all_values()
                sections   = _get_section_ranges(all_values)

                for sec_idx, sec in enumerate(sections):
                    stanza_col = sec["stanza_col"]
                    label = f"{ws.title} sez.{sec_idx + 1}"
                    matches1 = []  # (row_idx, stanza_val, nome_completo)
                    matches2 = []

                    for i in range(sec["header_row"] + 1, sec["end_row"]):
                        if i >= len(all_values):
                            break
                        row = all_values[i]
                        for col_c in range(min(5, len(row))):
                            cell = row[col_c].strip().upper()
                            stanza_val = row[stanza_col] if len(row) > stanza_col else ""
                            nome_comp  = " ".join(row[col_c:col_c + 2]).strip() if len(row) > col_c + 1 else row[col_c]
                            if cell == c1_up:
                                matches1.append((i, stanza_val, nome_comp))
                                break
                            elif cell == c2_up:
                                matches2.append((i, stanza_val, nome_comp))
                                break

                    if len(matches1) > 1:
                        return (f"⚠️ '{cognome1}' è ambiguo: {len(matches1)} persone trovate "
                                f"({', '.join(m[2] for m in matches1)}). "
                                f"Specifica anche il nome con /sposta.")
                    if len(matches2) > 1:
                        return (f"⚠️ '{cognome2}' è ambiguo: {len(matches2)} persone trovate "
                                f"({', '.join(m[2] for m in matches2)}). "
                                f"Specifica anche il nome con /sposta.")

                    if matches1 and matches2:
                        r1, s1, n1 = matches1[0]
                        r2, s2, n2 = matches2[0]
                        if s1 == s2:
                            avvisi.append(f"ℹ️ {label}: {n1} e {n2} sono già nella stessa stanza {s1}.")
                        else:
                            ws.update_cell(r1 + 1, stanza_col + 1, s2)
                            ws.update_cell(r2 + 1, stanza_col + 1, s1)
                            scambi.append(f"{label}: *{n1}* {s1}↔{s2} *{n2}*")

        if scambi:
            msg = "✅ Scambio completato:\n" + "\n".join(scambi)
            if avvisi:
                msg += "\n" + "\n".join(avvisi)
            return msg
        if avvisi:
            return "\n".join(avvisi)
        return f"⚠️ Non ho trovato entrambi i cognomi nei fogli rooming."

    except Exception as e:
        return f"❌ Errore: {type(e).__name__}: {str(e)[:200]}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── WHITELIST UTENTI AUTORIZZATI ─────────────────────────────────────────────
# Aggiungi qui gli ID Telegram dello staff autorizzato.
# Per trovare il proprio ID: aprire il bot e scrivere /myid
AUTHORIZED_IDS: set[int] = {
    # es: 123456789,  # Davide
    #     987654321,  # Francesco
}

def is_authorized(user_id: int) -> bool:
    # Se la whitelist è vuota, tutti possono accedere (utile in fase di setup)
    if not AUTHORIZED_IDS:
        return True
    return user_id in AUTHORIZED_IDS

async def check_auth(update: Update) -> bool:
    """Controlla autorizzazione e invia messaggio di rifiuto se non autorizzato."""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text(
            "🔒 Accesso non autorizzato.\n"
            "Contatta il responsabile del viaggio per richiedere l'accesso."
        )
        return False
    return True

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
        "titolo": "✈️ Arrivo a Osaka + Noodles Party",
        "attivita": "Arrivo all'aeroporto di Osaka Kansai alle 19:05 (volo TK086). Trasferimento in pullman all'Oriental Hotel Kyoto Rokujo. Cena: Noodles Party (instant noodles) in hotel.",
        "descrizione": "Dopo un lungo viaggio attraverso Istanbul, atterrate nella grande area metropolitana di Osaka-Kyoto. Il tragitto verso l'hotel vi darà i primi scorci del Giappone reale, molto diverso dai cliché: capannoni industriali, insegne al neon, reti ferroviarie sopraelevate. La Noodles Party è la prima cena in Giappone: instant noodles giapponesi per cominciare subito a immergersi nella cultura locale."
    },
    date(2026, 7, 3):  {
        "titolo": "📚 Scuola + Arashiyama",
        "attivita": "Corso di giapponese 3 ore (Campus Plaza, 9:00-12:00, aule R4 F6 / R5 F6). Pomeriggio: Arashiyama (bus).",
        "descrizione": "Arashiyama è il quartiere bambù di Kyoto: il celebre boschetto di bambù gigante è uno dei simboli del Giappone. Lungo il fiume Oi si trovano il Tempio Tenryu-ji (patrimonio UNESCO) e il pittoresco ponte Togetsukyo."
    },
    date(2026, 7, 4):  {
        "titolo": "📚 Scuola full day",
        "attivita": "Corso di giapponese 6 ore (sede Saiin/Minsai, 9:00-11:30 e 13:00-16:30).",
        "descrizione": "Giornata interamente dedicata alla Kyoto Minsai Japanese Language School. Il sabato è il giorno più intenso di studio — le 6 ore includono grammatica, conversazione, calligrafia e attività interattive con gli studenti locali."
    },
    date(2026, 7, 5):  {
        "titolo": "🏯 Osaka",
        "attivita": "Gita a Osaka (Keihan line): Castello (TKT) → Kuromon Market (pranzo) → Tsutenkaku → Nipponbashi → Dotonbori → eventuale Umekita Park.",
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
        "attivita": "Mattina: Akihabara + Asakusa. Check-out hotel e partenza per aeroporto. Volo di rientro TK199 da Tokyo Haneda ore 21:45.",
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
HAI ACCESSO DIRETTO A GOOGLE SHEETS: puoi modificare il rooming in tempo reale. Quando lo staff chiede di spostare qualcuno di stanza, conferma che stai aggiornando il foglio e fallo sapere. NON dire mai che non puoi modificare il foglio — puoi farlo. Per le modifiche al programma di viaggio, proponi la modifica e chiedi conferma.

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
ROOMING KYOTO - Oriental Hotel Kyoto Rokujo (numeri camera reali)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Camera 218 [tripla F]: CIMMINO Viola | DI VINCENZO Erica Marizol | GALLO Erica
Camera 219 [tripla F]: BUTTINO Desiree Fatima | MORGESE Ilaria | PIERGIACOMI Priscilla
Camera 340 [tripla F]: DI GIACOPO Lucrezia | ERCOLI Eleonora | DI GIACOPO Anastasia
Camera 341 [tripla F]: BACCARO Irene | FROSINI Ilaria | GRILLO Lucrezia
Camera 342 [tripla]:   ZOPPI Eleonora (disabile) | ZOPPI Maurizio (assist.) | RANISI Giulia (assist.)
Camera 338 [doppia F]: BONELLI Martina | LATO Giorgia Francesca
Camera 337 [doppia F]: MARINO Caterina | POGGI Alice (disabile)
Camera 243 [tripla F]: PALAZZO Giorgia | SCIALABBA Anna (disabile) | MUSCAGLIONE Cecilia
Camera 244 [tripla]:   CORRADINI Giordano (disabile) | CORRADINI Luca (assist.) | PANNACCI Cesira (assist.)
Camera 245 [tripla M]: DORONZO Michele | BIFULCO Francesco Andrea | LALA Matteo
Camera 246 [tripla M]: FERRARA Mattia | NAPOLETANO Rodolfo | CUCINO Francesco
Camera 247 [tripla M]: GIORDANO Gabriele | LUCCI Christian | IACOVELLA Leonardo Xiangxing
Camera 343 [tripla M]: VITALETTI Davide | BELLUCCI Francesco | DEL GIULIO Christian
Camera 220 [tripla M]: AGOSTINI Nicolò | MACCAGNAN Tommaso | MANCINO Gianluca (disabile)
Camera 221 [tripla M]: FERRARI Tobia | CARBONE Francesco | MACCARRONE Francesco (disabile)
Camera 313 [singola]:  TL Davide Di Stefano
Camera 314 [singola]:  TL Francesco Chiappetta
Camera 315 [singola]:  TL Francesca Guerrato

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
PARTENZE PER CITTÀ (operativo)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NAPOLI (7): Cimmino Viola, Di Vincenzo Erica Marizol, Gallo Erica, Bifulco Francesco Andrea, Lala Matteo, Ferrara Mattia, Napoletano Rodolfo
ROMA (21):  Buttino Desiree Fatima, Morgese Ilaria, Piergiacomi Priscilla, Di Giacopo Lucrezia, Ercoli Eleonora, Di Giacopo Anastasia, Baccaro Irene, Frosini Ilaria, Grillo Lucrezia, Zoppi Eleonora, Zoppi Maurizio (assist.), Ranisi Giulia (assist.), Pannacci Cesira (assist.), Corradini Giordano, Corradini Luca (assist.), Cucino Francesco, Giordano Gabriele, Lucci Christian, Iacovella Leonardo Xiangxing, Vitaletti Davide, Bellucci Francesco
BARI (3):   Bonelli Martina, Lato Giorgia Francesca, Doronzo Michele
BOLOGNA (1): Marino Caterina
MILANO (4): Poggi Alice, Palazzo Giorgia, Scialabba Anna, Ferrari Tobia
PALERMO (1): Muscaglione Cecilia
VENEZIA (6): Del Giulio Christian, Agostini Nicolò, Maccagnan Tommaso, Mancino Gianluca, Carbone Francesco, Maccarrone Francesco
Nota: IACOVELLA Leonardo → parte da Roma ma TORNA su Cagliari

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MATERIALE CONSEGNATO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ogni partecipante riceve: carta prepagata Mastercard (€220) + carta ICOCA trasporti + braccialetto colorato
Numeri carta: 00806 CIMMINO → 00848 MACCARRONE (assegnate in ordine di stanza)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RUBRICA PARTECIPANTI (data nascita | cell partecipante | cell genitore/intestatario | email)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AGOSTINI Nicolò          | 30/07/2008 | 3714244516 | 3475923795 | annaalberoni@gmail.com
BACCARO Irene            | 03/06/2008 | 3498132759 | 3391514087 | alessandrapadiglione@yahoo.it
BELLUCCI Francesco       | 25/06/2009 | —          | 3391944963 | totaro.cris@gmail.com
BIFULCO Francesco Andrea | 05/10/2009 | 3518784841 | 3315738738 | bifulco.massimo@gdf.it
BONELLI Martina          | 23/03/2008 | 3207812774 | 3289167065 | bonelli-antonio@libero.it
BUTTINO Desiree Fatima   | 11/05/2009 | 3247728521 | 3270027458 | ermy_1990@hotmail.it
CARBONE Francesco        | 15/07/2008 | 3756736714 | 3477913283 | giovcarbone@alice.it
CIMMINO Viola            | 27/01/2010 | 3470073206 | 3470073206 | lucia.castagnozzi@alice.it
CORRADINI Giordano       | 12/01/2007 | 3498081514 | 3382639439 | lucajago@gmail.com
CORRADINI Luca (assist.) | 19/06/1971 | —          | 3382639439 | lucajago@gmail.com
CUCINO Francesco         | 28/04/2008 | 3313739594 | 3313739594 | umbertovfs@libero.it
DEL GIULIO Christian     | 13/11/2009 | 3501385914 | 3384009799 | stefanodelgiulio@virgilio.it
DI GIACOPO Anastasia     | 21/03/2010 | 3518760707 | 3391150456 | fabrizio.digiacopo35@gmail.com
DI GIACOPO Lucrezia      | 16/08/2008 | 3481145978 | 3391150456 | fabrizio.digiacopo35@gmail.com
DI VINCENZO Erica Marizol| 25/08/2007 | 3921815461 | 3470186389 | onofrio.divincenzo@unibas.it
DORONZO Michele          | 14/11/2008 | 3703603834 | 3497644252 | mar.tutti@libero.it
ERCOLI Eleonora          | 31/08/2008 | 3518341253 | 3922631771 | daniela_renna@hotmail.com
FERRARI Tobia            | 20/02/2008 | 3387097359 | 3494328563 | nora.bentivoglio@gmail.com
FERRARA Mattia           | 08/10/2008 | 3512233875 | 3662476894 | antoniofer11@libero.it
FROSINI Ilaria           | 22/11/2008 | 3474068434 | 3381212666 | paolamenci70@gmail.com
GALLO Erica              | 03/12/2008 | 3714952943 | 3346318300 | modababy011@libero.it
GIORDANO Gabriele        | 06/10/2008 | 3669051522 | 3313621258 | sabativit@alice.it
GRILLO Lucrezia          | 17/10/2008 | 3922908227 | 3385218965 | kettyproia75@gmail.com
IACOVELLA Leonardo       | 05/05/2010 | 3294476385 | 3470734473 | linda.dilario@gmail.com
LALA Matteo              | 02/02/2010 | —          | 3333898170 | giorgiolala@libero.it
LATO Giorgia Francesca   | 04/10/2009 | 3701513468 | 3341155095 | Romotron@gmail.com
LUCCI Christian          | 27/10/2008 | 3806588128 | 3388265011 | lucciantonio71@gmail.com
MACCAGNAN Tommaso        | 07/01/2008 | 3471430255 | 3389050848 | tomasci@libero.it
MACCARRONE Francesco     | 07/02/2009 | 3519280527 | 3478569733 | longo.imma64@gmail.com
MANCINO Gianluca         | 02/01/2008 | 3779891711 | 3286862980 | paola.caposiena@liceocuriel.net
MARINO Caterina          | 31/12/2008 | 3337796784 | 3384536986 | france7373@gmail.com
MORGESE Ilaria           | 24/05/2008 | 3393400112 | 3393400112 | morganfree72@libero.it
MUSCAGLIONE Cecilia      | 22/01/2010 | 3475384298 | 3495606837 | danielasampino@virgilio.it
NAPOLETANO Rodolfo       | 02/09/2008 | 3493255877 | 3388934294 | cosmo.napoletano@gmail.com
PALAZZO Giorgia          | 25/01/2009 | 3475323149 | 335373246  | gpalazzo@studiopalazzo.eu
PANNACCI Cesira (assist.)| 21/09/1968 | —          | 3382639439 | lucajago@gmail.com
PIERGIACOMI Priscilla    | 10/08/2008 | 3890276131 | 3470664669 | annarita.vozza1000@gmail.com
POGGI Alice              | 07/01/2008 | 3479268724 | 3476917430 | anna.levrero@gmail.com
RANISI Giulia (assist.)  | 30/05/1974 | —          | 3316041944 | zoppimaurizio73@gmail.com
SCIALABBA Anna           | 06/12/2011 | —          | 3387782947 | ciceraro71@gmail.com
VITALETTI Davide         | 15/12/2009 | —          | 3291681077 | cencett84@hotmail.it
ZOPPI Eleonora           | 18/08/2005 | 3316041944 | 3316041944 | zoppimaurizio73@gmail.com
ZOPPI Maurizio (assist.) | 30/05/1973 | —          | 3316041944 | zoppimaurizio73@gmail.com

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CODICI FISCALI PARTECIPANTI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AGOSTINI Nicolò          → GSTNCL08L30G224L
BACCARO Irene            → BCCRNI08H43H501F
BELLUCCI Francesco       → BLLFNC09H25D451X
BIFULCO Francesco Andrea → BFLFNC09R05A509X
BONELLI Martina          → BNLMTN08C63A662F
BUTTINO Desiree Fatima   → BTTDRF09E51A783B
CARBONE Francesco        → CRBFNC08L15L840H
CIMMINO Viola            → CMMVLI10A67A783U
CORRADINI Giordano       → CRRGDN07A12H501N
CORRADINI Luca           → CRRLCU71H19H501N
CUCINO Francesco         → CCNFNC08D28E958K
DEL GIULIO Christian     → DLGCRS09S13E473O
DI GIACOPO Anastasia     → DGCNTS10C61L103O
DI GIACOPO Lucrezia      → DGCLRZ08M56L103X
DI VINCENZO Erica Marizol→ DVNRMR07M65Z611E
DORONZO Michele          → DRNMHL08S14A669B
ERCOLI Eleonora          → RCLLNR08M71H501M
FERRARI Tobia            → FRRTBO08B20A246D
FERRARA Mattia           → FRRMTT08R08F839L
FROSINI Ilaria           → FRSLRI08S62A851V
GALLO Erica              → GLLRCE08T43F839I
GIORDANO Gabriele        → GRDGRL08R06H501M
GRILLO Lucrezia          → GRLLRZ08R57H501J
IACOVELLA Leonardo       → CVLLRD10E05Z210C
LALA Matteo              → LLAMTT10B02A509W
LATO Giorgia Francesca   → LTAGGF09R44A285D
LUCCI Christian          → LCCCRS08R24H501J
MACCAGNAN Tommaso        → MCCTMS08A07A001E
MACCARRONE Francesco     → MCCFNC09B07L840K
MANCINO Gianluca         → MNCGLC08A02G224H
MARINO Caterina          → MRNCRN08T71D548R
MORGESE Ilaria           → MRGLRI08E64A048E
MUSCAGLIONE Cecilia      → MSCCCL10A62G273S
NAPOLETANO Rodolfo       → NPLRLF08P02F839A
PALAZZO Giorgia          → PLZGRG09A65A794S
PANNACCI Cesira          → PNNCSR68P61H501P
PIERGIACOMI Priscilla    → PRGPSC08M50L049E
POGGI Alice              → PGGLCA08A47I480T
RANISI Giulia            → RNSGLI74E70H501F
SCIALABBA Anna           → SCLNNA11T46F205E
VITALETTI Davide         → VTLDVD09T15A271V
ZOPPI Eleonora           → ZPPLNR05M58H501B
ZOPPI Maurizio           → ZPPMRZ73E30H501J

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCUOLA DI GIAPPONESE - Kyoto Minsai (Schedule Tentative)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Scuola: Kyoto Minsai Japanese Language School
Due classi parallele: CLASSE A e CLASSE B (stesso orario, aule diverse)
Totale ore: 30 ore per classe

CALENDARIO LEZIONI TURNO 1:

03/07 ven  │ 3 ore  │ 9:00-12:00
  Classe A → Campus Plaza, Lecture Room 4 (6F)
  Classe B → Campus Plaza, Lecture Room 5 (6F)

04/07 sab  │ 6 ore  │ 9:00-11:30 / 13:00-16:30
  Classe A → Minsai Saiin Campus, aula 2A
  Classe B → Minsai Saiin Campus, aula 2B

05/07 dom  │ NIENTE SCUOLA
06/07 lun  │ NIENTE SCUOLA

07/07 mar  │ 3 ore  │ 9:00-12:00
  Classe A → Campus Plaza, Lecture Room 6 (6F)
  Classe B → Campus Plaza, Lecture Room 5 (6F)

08/07 mer  │ 3 ore  │ 9:00-12:00
  Classe A → Campus Plaza, Lecture Room 6 (6F)
  Classe B → Campus Plaza, Lecture Room 5 (6F)

09/07 gio  │ 3 ore  │ 9:00-12:00
  Classe A → Campus Plaza, Lecture Room 6 (6F)
  Classe B → Campus Plaza, Lecture Room 5 (6F)

10/07 ven  │ NIENTE SCUOLA

11/07 sab  │ 6 ore  │ 9:00-11:30 / 13:00-16:30
  Classe A → Minsai Saiin Campus, aula 2A
  Classe B → Minsai Saiin Campus, aula 2B

12/07 dom  │ 6 ore  │ 9:00-11:30 / 13:00-16:30
  Classe A → Minsai Saiin Campus, aula 2A
  Classe B → Minsai Saiin Campus, aula 2B

RIEPILOGO SEDI:
- Campus Plaza (giorni feriali): edificio con aule al 6° piano
- Minsai Saiin Campus: sede principale Minsai (fine settimana)
Indirizzo Minsai: 69 Nishikyogoku Kitaooiri-cho, Ukyo-ku, Kyoto | Tel: 075-316-0190

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SHINKANSEN - 13 LUGLIO (Kyoto → Nagoya → Tokyo)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TRATTO 1 — Kyoto → Nagoya
  Treno:    NOZOMI 244
  Orario:   08:54 → 09:28
  Durata:   34 minuti
  Carrozze: multiple (Car 14, 15 tra le prenotate)

TRATTO 2 — Nagoya → Tokyo
  Treno:    NOZOMI 406
  Orario:   14:29 → 16:06
  Durata:   1h 37min
  Carrozze: multiple (Car 3, 4, 5 tra le prenotate)

Nota: a Nagoya (09:28 – 14:29) visita al Castello di Nagoya e Osu Kannon.
Arrivo a Tokyo 16:06. Sera: Tokyo Metropolitan Government Building + Shinjuku.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AVVICINAMENTI NAZIONALI - TURNO 1 (1 lug / 16 lug)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VOLI ANDATA (1 luglio):
  PMO→FCO  XZ2712 (Aeroitalia)  11:30→12:40  1 pax

TRENI ANDATA (1 luglio) → Roma Termini:
  Bari→Roma Termini       Frecciarossa 8306   08:40→13:15  3 pax
  Venezia S.Lucia→Roma    Frecciarossa 9411   09:26→13:30  6 pax
  Milano→Roma Termini     Italo 9979          11:15→14:30  4 pax
  Bologna→Roma Termini    Italo 8902          11:42→14:05  1 pax
  Napoli→Roma Termini     Italo 9940          13:20→14:30  7 pax

VOLI RITORNO (16 luglio):
  FCO→CAG  XZ2341 (Aeroitalia)  13:30→14:40  1 pax
  FCO→PMO  AZ 1779 (ITA)        14:20→15:25  1 pax

TRENI RITORNO (16 luglio) ← Roma Termini:
  Roma Termini→Venezia S.Lucia  Italo 8916          12:55→16:55  6 pax
  Roma Termini→Milano           Italo 9982          13:05→16:15  4 pax
  Roma Termini→Bari             Frecciarossa 8311   13:15→17:43  3 pax
  Roma Termini→Napoli           Italo 8907          13:30→14:43  7 pax
  Roma Termini→Bologna          Italo 8134          13:40→16:03  1 pax

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOTE OPERATIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- IACOVELLA Leonardo: parte da Roma ma rientra su Cagliari
- MACCARRONE Francesco: diabetico con microinfusore — verificare frigorifero disponibile
- Modifiche a programma o rooming: lo staff le comunica via chat, il bot le registra e le riporta
"""

# ─── BRIEFING ARRIVO ──────────────────────────────────────────────────────────
BRIEFING_P1 = """🎌 *BRIEFING ARRIVO KYOTO — Giappone Discovery T1*

Benvenuti in Giappone! Ora ci aspetta circa *1h30 di bus* per raggiungere l'hotel — *Oriental Hotel Kyoto Rokujo*.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚌 *ICOCA — Carta Trasporti*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Nella bustina ricevete l'*ICOCA* con *10.000 yen pre-caricati*, da usare *solo per gli spostamenti col gruppo*. Se la usate per acquisti personali ai distributori dovrete ricaricarla a vostre spese.

⚠️ *NON trasferite l'ICOCA nel wallet dell'iPhone* — diventa inutilizzabile e dovrete ricomprarne una nuova.

• Portatela *SEMPRE* con voi ogni volta che uscite
• Metro/treno: *tap all\'ingresso E all\'uscita* — aspettate il *BIP*, non passate col tornello di qualcun altro
• Sui mezzi pubblici non si parla (o sottovoce)
• Bus: si sale da dietro, si scende da davanti. Si tappa l\'ICOCA *solo quando si scende*. Su alcuni bus vi diremo noi quando tapparla anche in salita"""

BRIEFING_P2 = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💳 *Carta Mastercard Prepagata*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Nella bustina trovate anche la *carta prepagata Mastercard*, senza PIN — si può *solo strisciare*. Spiegalo sempre all\'esercente e provatela da entrambi i lati.

• *Budget pasti: 1.400–1.500 yen a pasto*, autogestito (se a pranzo spendo 1.000, a cena posso spendere 1.800)
• Dove accettano carta: pagate sempre con la card
• Se viene smarrita: segnalatecelo subito
• Saldo: *getmybalance.com*
• Stasera vi aiutiamo a registrarla su Apple Pay / Google Pay (guida nel gruppo WhatsApp)
• La carta rimane vostra — se avanzano soldi è spendibile anche in Italia

Nella bustina c\'è anche il *braccialetto colorato* — serve per dividervi in classi a scuola e per i gruppi sui bus. Per il resto fate tutto insieme. Non scambiateveli."""

BRIEFING_P3 = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏨 *Hotel — Oriental Hotel Kyoto Rokujo*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Max *2 tessere magnetiche per camera* — non perdetele
• Per salire in ascensore serve la tessera: tenetelo a mente quando uscite
• In camera: inserite la tessera nella *fessura* vicino all\'ingresso per abilitare la corrente

🚭 *VIETATO FUMARE IN CAMERA* — fee di *¥30.000* se viene rilevato odore. Si fuma solo nella *Smoking Room al Piano 1*. Anche fuori: solo nelle zone fumo segnalate vicino ai konbini.

• Per la pulizia della stanza: magnete *"PLEASE MAKE MY ROOM"* fuori dalla porta la mattina
• Bollitore, tè e caffè: gratuiti | Ciabattine e pigiami: in dotazione, *non portarli via*
• Asciugamani, shampoo ecc.: rimangono in stanza (se mancano li addebitano)
• *Passaporto: lasciatelo in cassaforte* fino al check-out per Tokyo
• *Colazione:* 6:45 → 9:30
• *Snack e bevande in lobby:* gratuiti 14:30 → 23:00
• *Lavanderia (Piano 1):* ¥500–600 in monete da ¥100, durata ~2h — svuotate subito a fine ciclo
• Acqua del rubinetto potabile — usate il distributore al piano terra

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🍜 *Stasera — Noodles Party*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
In lobby trovate noodles istantanei e snack. Disfate le valigie e scendete a prenderli!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 *Domani — Lezione di Giapponese*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*Partenza dall\'hotel alle 8:30 puntuali.*
Nello zaino: 📓 quaderno e penna, 🌂 mantellina/k-way + ombrello, maglia e calzini di ricambio, ICOCA sempre.

Buona prima notte in Giappone\\! 🇯🇵"""

# ─── STATO APPELLO ────────────────────────────────────────────────────────────
appello_state: dict[int, dict] = {}
# Struttura: { user_id: { "gruppo": "🔴 ROSSO", "nomi": [...], "indice": 0, "presenti": [], "assenti": [] } }

# Modifiche registrate in sessione
modifiche_log: list[str] = []

# Storico conversazioni AI
conversation_history: dict[int, list] = {}

claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

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
async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.full_name
    await update.message.reply_text(
        f"👤 *{name}*\n🆔 Il tuo ID Telegram è: `{uid}`\n\nMandalo al responsabile per ottenere l'accesso.",
        parse_mode="Markdown"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    await update.message.reply_text(
        "👋 Ciao! Sono l'assistente staff *Giappone Discovery - Turno 1*.\n\n"
        "Puoi scrivermi in linguaggio libero oppure usare questi comandi:\n\n"
        "🎌 /briefing — briefing di arrivo (ICOCA, carte, hotel, regole)\n"
        "📅 /oggi — programma e descrizione di oggi\n"
        "📢 /appello — appello presenti per colore\n"
        "📋 /modifiche — vedi le modifiche registrate\n"
        "❓ /help — esempi di domande\n"
        "🔄 /reset — cancella cronologia chat",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
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

async def briefing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    for parte in [BRIEFING_P1, BRIEFING_P2, BRIEFING_P3]:
        await update.message.reply_text(parte, parse_mode="Markdown")

async def oggi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    testo = get_programma_oggi()
    await update.message.reply_text(testo, parse_mode="Markdown")

async def modifiche_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not modifiche_log:
        await update.message.reply_text("Nessuna modifica registrata in questa sessione.")
    else:
        testo = "📋 *Modifiche registrate:*\n\n" + "\n".join(f"• {m}" for m in modifiche_log)
        await update.message.reply_text(testo, parse_mode="Markdown")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    appello_state.pop(user_id, None)
    await update.message.reply_text("✅ Cronologia cancellata.")

# ─── APPELLO ──────────────────────────────────────────────────────────────────
async def appello_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
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
            "saltati": [],   # nomi saltati nel giro corrente
            "giro": 1,
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
        elif data == "salta":
            stato["saltati"].append(nome_corrente)  # ricordati chi hai saltato

        stato["indice"] += 1

        if stato["indice"] >= len(stato["nomi"]):
            saltati_rimasti = stato["saltati"]

            if saltati_rimasti:
                # Riparti con i soli saltati
                stato["nomi"]    = saltati_rimasti.copy()
                stato["saltati"] = []
                stato["indice"]  = 0
                stato["giro"]   += 1
                avviso = (
                    f"↩️ *Giro {stato['giro']} — Saltati ({len(saltati_rimasti)}):*\n"
                    + "\n".join(f"• {n}" for n in saltati_rimasti)
                )
                await query.message.reply_text(avviso, parse_mode="Markdown")
                await _invia_prossimo_nome(query.message, user_id)
            else:
                # Nessun saltato rimasto → appello completo
                gruppo   = stato["gruppo"]
                presenti = stato["presenti"]
                assenti  = stato["assenti"]
                del appello_state[user_id]

                testo = (
                    f"✅ *Appello {gruppo} completato!*\n\n"
                    f"*Presenti ({len(presenti)}):* {', '.join(presenti) if presenti else '—'}\n\n"
                    f"*Assenti ({len(assenti)}):* {', '.join(assenti) if assenti else '—'}\n"
                )
                await query.message.reply_text(testo, parse_mode="Markdown")
        else:
            await _invia_prossimo_nome(query.message, user_id)

async def _invia_prossimo_nome(message, user_id: int):
    stato = appello_state[user_id]
    idx    = stato["indice"]
    totale = len(stato["nomi"])
    nome   = stato["nomi"][idx]
    gruppo = stato["gruppo"]
    giro   = stato.get("giro", 1)

    keyboard = [[
        InlineKeyboardButton("✅ Presente", callback_data="presente"),
        InlineKeyboardButton("❌ Assente",  callback_data="assente"),
        InlineKeyboardButton("⏭ Salta",    callback_data="salta"),
    ]]
    intestazione = f"{gruppo} — {idx+1}/{totale}"
    if giro > 1:
        intestazione += f"  ♻️ Giro {giro} (saltati)"
    await message.reply_text(
        f"{intestazione}\n\n👤 *{nome}*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ─── COMPLEANNI ───────────────────────────────────────────────────────────────
# Date di nascita reali dal file Excel (giorno, mese, anno)
PARTECIPANTI_DATE = [
    ("AGOSTINI Nicolò",           date(2008,  7, 30)),
    ("BACCARO Irene",             date(2008,  6,  3)),
    ("BELLUCCI Francesco",        date(2009,  6, 25)),
    ("BIFULCO Francesco Andrea",  date(2009, 10,  5)),
    ("BONELLI Martina",           date(2008,  3, 23)),
    ("BUTTINO Desiree Fatima",    date(2009,  5, 11)),
    ("CARBONE Francesco",         date(2008,  7, 15)),
    ("CIMMINO Viola",             date(2010,  1, 27)),
    ("CORRADINI Giordano",        date(2007,  1, 12)),
    ("CORRADINI Luca",            date(1971,  6, 19)),
    ("CUCINO Francesco",          date(2008,  4, 28)),
    ("DEL GIULIO Christian",      date(2009, 11, 13)),
    ("DI GIACOPO Anastasia",      date(2010,  3, 21)),
    ("DI GIACOPO Lucrezia",       date(2008,  8, 16)),
    ("DI VINCENZO Erica Marizol", date(2007,  8, 25)),
    ("DORONZO Michele",           date(2008, 11, 14)),
    ("ERCOLI Eleonora",           date(2008,  8, 31)),
    ("FERRARI Tobia",             date(2008,  2, 20)),
    ("FERRARA Mattia",            date(2008, 10,  8)),
    ("FROSINI Ilaria",            date(2008, 11, 22)),
    ("GALLO Erica",               date(2008, 12,  3)),
    ("GIORDANO Gabriele",         date(2008, 10,  6)),
    ("GRILLO Lucrezia",           date(2008, 10, 17)),
    ("IACOVELLA Leonardo",        date(2010,  5,  5)),
    ("LALA Matteo",               date(2010,  2,  2)),
    ("LATO Giorgia Francesca",    date(2009, 10,  4)),
    ("LUCCI Christian",           date(2008, 10, 27)),
    ("MACCAGNAN Tommaso",         date(2008,  1,  7)),
    ("MACCARRONE Francesco",      date(2009,  2,  7)),
    ("MANCINO Gianluca",          date(2008,  1,  2)),
    ("MARINO Caterina",           date(2008, 12, 31)),
    ("MORGESE Ilaria",            date(2008,  5, 24)),
    ("MUSCAGLIONE Cecilia",       date(2010,  1, 22)),
    ("NAPOLETANO Rodolfo",        date(2008,  9,  2)),
    ("PALAZZO Giorgia",           date(2009,  1, 25)),
    ("PANNACCI Cesira",           date(1968,  9, 21)),
    ("PIERGIACOMI Priscilla",     date(2008,  8, 10)),
    ("POGGI Alice",               date(2008,  1,  7)),
    ("RANISI Giulia",             date(1974,  5, 30)),
    ("SCIALABBA Anna",            date(2011, 12,  6)),
    ("VITALETTI Davide",          date(2009, 12, 15)),
    ("ZOPPI Eleonora",            date(2005,  8, 18)),
    ("ZOPPI Maurizio",            date(1973,  5, 30)),
]

INIZIO_TURNO = date(2026, 7, 1)
FINE_TURNO   = date(2026, 7, 16)

async def compleanni_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    trovati = [
        (d.replace(year=2026), nome)
        for nome, d in PARTECIPANTI_DATE
        if INIZIO_TURNO <= d.replace(year=2026) <= FINE_TURNO
    ]
    trovati.sort()

    if trovati:
        righe = "\n".join(f"🎂 *{nome}* — {d.strftime('%d/%m')}" for d, nome in trovati)
        testo = f"*Compleanni durante il turno (01–16 luglio):*\n\n{righe}"
    else:
        testo = "Nessun compleanno durante il turno."

    await update.message.reply_text(testo, parse_mode="Markdown")

# ─── MESSAGGI LIBERI (AI) ─────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
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

    # Rilevamento domande sui compleanni → risposta programmatica (non AI)
    if any(k in user_text.lower() for k in ["complean", "compie gli anni", "festeggia", "nato il", "nata il"]):
        trovati = [
            (d.replace(year=2026), nome)
            for nome, d in PARTECIPANTI_DATE
            if INIZIO_TURNO <= d.replace(year=2026) <= FINE_TURNO
        ]
        trovati.sort()
        if trovati:
            righe = "\n".join(f"🎂 *{nome}* — {d.strftime('%d/%m')}" for d, nome in trovati)
            testo = f"*Compleanni durante il turno (01–16 luglio):*\n\n{righe}"
        else:
            testo = "Nessun compleanno durante il turno."
        await update.message.reply_text(testo, parse_mode="Markdown")
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

        response = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system,
            messages=conversation_history[user_id]
        )

        reply = response.content[0].text

        # Rilevamento cambio stanza → chiedi all'AI di estrarre i dati in JSON e aggiorna il foglio
        if any(k in user_text.lower() for k in ["sposta", "stanza", "cambia", "metti in", "spostalo", "spostala", "trasferisci", "manda in"]):
            extract_response = claude_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                system=(
                    "Sei un estrattore di dati. Dall'input dell'utente, estrai il cambio stanza richiesto. "
                    "Rispondi SOLO con JSON valido nel formato: "
                    "{\"cognome\": \"COGNOME\", \"nome\": \"NOME\", \"stanza\": \"NUMERO\"} "
                    "Se non riesci a identificare con certezza cognome, nome e nuova stanza, rispondi con: {}"
                ),
                messages=[{"role": "user", "content": user_text}]
            )
            try:
                raw = extract_response.content[0].text.strip()
                extracted = json.loads(raw)
                if extracted.get("cognome") and extracted.get("nome") and extracted.get("stanza"):
                    esito = sposta_in_sheet(extracted["cognome"], extracted["nome"], extracted["stanza"])
                    modifiche_log.append(f"[{date.today()}] {user_text} → {esito}")
                    reply += f"\n\n{esito}"
                else:
                    reply += "\n\n⚠️ Non ho capito chi spostare e in quale stanza. Usa: `/sposta COGNOME NOME stanza NUMERO`"
            except json.JSONDecodeError as e:
                reply += f"\n\n⚠️ Errore parsing modifica: {str(e)[:100]}"
            except Exception as e:
                reply += f"\n\n⚠️ Errore Sheets: {type(e).__name__}: {str(e)[:150]}"

        conversation_history[user_id].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Errore API: {type(e).__name__}: {e}")
        await update.message.reply_text(f"⚠️ Errore: `{type(e).__name__}: {str(e)[:200]}`", parse_mode="Markdown")

# ─── SPOSTA / SCAMBIA ROOMING ────────────────────────────────────────────────
async def sposta_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    # Uso: /sposta COGNOME NOME stanza NUMERO
    args = context.args
    if len(args) < 4 or args[2].lower() != "stanza":
        await update.message.reply_text(
            "Uso corretto:\n`/sposta COGNOME NOME stanza NUMERO`\n\nEsempio:\n`/sposta FERRARA MATTIA stanza 11`\n\n"
            "Per scambiare due persone tra stanze della stessa capienza usa:\n`/scambia COGNOME1 COGNOME2`",
            parse_mode="Markdown"
        )
        return

    cognome      = args[0]
    nome         = args[1]
    nuova_stanza = args[3]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    esito = sposta_in_sheet(cognome, nome, nuova_stanza)
    modifiche_log.append(f"[{date.today()}] /sposta {cognome} {nome} → stanza {nuova_stanza}")
    await update.message.reply_text(esito, parse_mode="Markdown")

async def scambia_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    # Uso: /scambia COGNOME1 COGNOME2
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Uso corretto:\n`/scambia COGNOME1 COGNOME2`\n\nEsempio:\n`/scambia CIMMINO BUTTINO`\n\n"
            "Scambia le stanze tra due persone mantenendo la capienza di entrambe le stanze invariata.",
            parse_mode="Markdown"
        )
        return

    cognome1 = args[0]
    cognome2 = args[1]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    esito = scambia_in_sheet(cognome1, cognome2)
    modifiche_log.append(f"[{date.today()}] /scambia {cognome1} ↔ {cognome2}: {esito[:80]}")
    await update.message.reply_text(esito, parse_mode="Markdown")

# ─── AVVIO ────────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("myid",     myid_command))
    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("help",     help_command))
    app.add_handler(CommandHandler("briefing", briefing_command))
    app.add_handler(CommandHandler("oggi",     oggi_command))
    app.add_handler(CommandHandler("appello",  appello_command))
    app.add_handler(CommandHandler("modifiche",modifiche_command))
    app.add_handler(CommandHandler("compleanni", compleanni_command))
    app.add_handler(CommandHandler("sposta",     sposta_command))
    app.add_handler(CommandHandler("scambia",    scambia_command))
    app.add_handler(CommandHandler("reset",    reset))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Bot avviato.")
    app.run_polling()

if __name__ == "__main__":
    main()
