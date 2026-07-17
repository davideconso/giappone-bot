"""
Bot Telegram - Giappone Discovery Turno 3
Staff assistant per il viaggio 16/07/2026 - 31/07/2026 (arrivo Osaka 17/07, rientro Italia 31/07)

SETUP:
1. Crea un bot su Telegram tramite @BotFather → ottieni il TOKEN
2. Variabili d'ambiente: TELEGRAM_TOKEN, ANTHROPIC_API_KEY, GROQ_API_KEY,
   GOOGLE_CREDENTIALS_JSON, (opz.) DIARY_SHEET_ID
3. Avvio: python giappone_bot_t3.py

NOTA T3: come T2, niente gruppi colore — braccialetti tutti verdi, appello unico.
Partenze da Roma FCO e Milano MXP (con avvicinamenti da Bari, Catania, Napoli,
Palermo, Bologna, Venezia, Alghero). Gruppo grande: 54 partecipanti + 3 TL
(+ 1 TL in prosecuzione dal Turno 2).
Il rooming è di SOLA LETTURA (nessuna scrittura sul foglio).
"""

import os
import json
import logging
import tempfile
from datetime import date, datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    ContextTypes, filters, CallbackQueryHandler
)
import anthropic
import gspread
from google.oauth2.service_account import Credentials
from groq import Groq

# ─── CONFIGURAZIONE ───────────────────────────────────────────────────────────
TELEGRAM_TOKEN        = os.environ.get("TELEGRAM_TOKEN",          "INSERISCI_QUI_IL_TOKEN")
ANTHROPIC_API_KEY     = os.environ.get("ANTHROPIC_API_KEY",       "INSERISCI_QUI_LA_API_KEY_ANTHROPIC")
GROQ_API_KEY          = os.environ.get("GROQ_API_KEY",            "INSERISCI_QUI_LA_API_KEY_GROQ")
GOOGLE_CREDS_JSON     = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
# Rooming T3 (Google Sheet, sola lettura)
ROOMING_SHEET_IDS: list[str] = [
    "1PpNCHvUtYKTSB30r1ckWaOUEYlkL8HWSAehP-w1P5ds",  # Rooming turno 3
]
# Cartella Drive Turno 3
STAFF_FOLDER_ID = "1SP_xHxhoJXVtzYuXJ1_Q5bBb3uuRFjJ6"
_diary_sheet_id: str = os.environ.get("DIARY_SHEET_ID", "")

# ─── GOOGLE SHEETS CLIENT (SOLA LETTURA rooming) ─────────────────────────────
def get_sheets_client():
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds)

# ─── DIARIO VIAGGIO ───────────────────────────────────────────────────────────
INIZIO_VIAGGIO = date(2026, 7, 17)  # arrivo a Osaka/Kyoto
FINE_VIAGGIO   = date(2026, 7, 31)  # rientro in Italia

def _citta_oggi() -> str:
    oggi = date.today()
    if oggi < date(2026, 7, 28):
        return "Kyoto"
    elif oggi <= date(2026, 7, 31):
        return "Tokyo"
    return "—"

def _giorno_viaggio() -> int:
    delta = (date.today() - INIZIO_VIAGGIO).days + 1
    return max(1, min(delta, 15))

def get_or_create_diary_sheet() -> gspread.Spreadsheet:
    """Restituisce il foglio diario; lo crea se non esiste ancora."""
    global _diary_sheet_id
    gc = get_sheets_client()
    if _diary_sheet_id:
        return gc.open_by_key(_diary_sheet_id)
    sh = gc.create("Diario Viaggio — Giappone Discovery T3")
    sh.client.insert_permission(sh.id, None, perm_type="anyone", role="writer")
    import googleapiclient.discovery
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"]
    )
    drive_svc = googleapiclient.discovery.build("drive", "v3", credentials=creds)
    f = drive_svc.files().get(fileId=sh.id, fields="parents").execute()
    prev_parents = ",".join(f.get("parents", []))
    drive_svc.files().update(
        fileId=sh.id, addParents=STAFF_FOLDER_ID,
        removeParents=prev_parents, fields="id, parents"
    ).execute()
    ws = sh.sheet1
    ws.update_title("Diario")
    ws.append_row(["#", "Data", "Ora", "Giorno", "Città", "Mittente", "Trascrizione", "Note"])
    ws.format("A1:H1", {"textFormat": {"bold": True}})
    _diary_sheet_id = sh.id
    logging.info(f"Diario creato: https://docs.google.com/spreadsheets/d/{sh.id}")
    return sh

def salva_nel_diario(mittente: str, testo: str, note: str = "") -> str:
    try:
        sh = get_or_create_diary_sheet()
        ws = sh.sheet1
        ora_it = datetime.now().strftime("%H:%M")
        data_it = datetime.now().strftime("%d/%m/%Y")
        n_righe = len(ws.get_all_values())
        riga = [n_righe, data_it, ora_it, _giorno_viaggio(), _citta_oggi(), mittente, testo, note]
        ws.append_row(riga)
        return f"https://docs.google.com/spreadsheets/d/{_diary_sheet_id}"
    except Exception as e:
        return f"ERRORE: {e}"

def trascrivi_audio(percorso: str) -> str:
    client = Groq(api_key=GROQ_API_KEY)
    with open(percorso, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-large-v3", file=f, language="it")
    return result.text.strip()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── WHITELIST UTENTI AUTORIZZATI ─────────────────────────────────────────────
AUTHORIZED_IDS: set[int] = {
    # es: 123456789,  # Davide
}

def is_authorized(user_id: int) -> bool:
    if not AUTHORIZED_IDS:
        return True
    return user_id in AUTHORIZED_IDS

async def check_auth(update: Update) -> bool:
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text(
            "🔒 Accesso non autorizzato.\n"
            "Contatta il responsabile del viaggio per richiedere l'accesso.")
        return False
    return True

# ─── GRUPPO UNICO (T3: braccialetti tutti VERDI, nessuna divisione colore) ────
PARTECIPANTI_T3 = [
    # BARI (12)
    "ANCONA Alessandro", "ANSANI Antonio Zhelyazko", "BIANCO Riccardo",
    "BONASIA Ilaria", "DE BRACO Maria Rita", "DELLI CARRI Maria",
    "FACCILONGO Mariachiara", "LOJACONO Silvia", "MARINELLI Egle",
    "PALMERI Federico", "VERRIELLO Giovanni", "ZOPPI Aurora",
    # BOLOGNA (1)
    "MILLI Nicholas",
    # CATANIA (5)
    "CLEMENTI Aurelio Rosario", "COSTA Aurora", "GENOVESE Andrea",
    "LO BARTOLO Carola Maria", "RIGGI Giorgia",
    # NAPOLI (4)
    "D'ANIELLO Giulia", "D'ORTA Martina", "DELLA GATTA Salvatore", "ROSSI Martina",
    # PALERMO (3)
    "BURRIESCI Giuliana", "LO BAIDO Vittoria", "TARGIA Francesco",
    # ROMA (15)
    "ADDESSE Damiano", "CAPRIOTTI Vittoria", "DI GIORGIO Sofia",
    "DI PAOLO Christian", "DI VICO Flavia", "LA VECCHIA Antonio",
    "LUCIOLI Maria Vittoria", "MAFFIA Simone", "PIANESE Francesca",
    "PISANO Raffaele", "PIZZUTO Oscar", "PRACILIO Giulio",
    "SPINA Daniele", "SPINA Martina", "VECCHIOTTI Guenda",
    # MILANO (9)
    "BARBAGALLO Fabrizio", "CARULLI Roberto Maria", "COCCO Asia",
    "COSTA Angela", "DE ANGELIS Lavinia", "GENTILE Damiano",
    "MANNAI Eleonora", "OTERI Gianluca", "SPADARO Alessandro",
    # VENEZIA (4)
    "PASCOLI Emma", "PASCOLI Sofia", "PIAZZO Chiara", "TORRICELLI Alessandro",
    # ALGHERO (1)
    "GARAU Gabriele",
]
GRUPPI = {"🟢 VERDE (tutti)": PARTECIPANTI_T3}

# ─── PROGRAMMA GIORNALIERO T3 ─────────────────────────────────────────────────
PROGRAMMA = {
    date(2026, 7, 17): {
        "titolo": "✈️ Arrivo a Osaka + Noodles Party",
        "attivita": "Arrivo a Osaka Kansai alle 18:50 (volo TK086). Trasferimento in bus all'Oriental Hotel Kyoto Rokujo. Cena: Noodles Party in hotel.",
        "descrizione": "Dopo il lungo viaggio via Istanbul, atterrate nell'area metropolitana di Osaka-Kyoto. Il tragitto in bus offre i primi scorci del Giappone reale. La Noodles Party è la prima cena giapponese: instant noodles in hotel per iniziare l'immersione nella cultura locale."
    },
    date(2026, 7, 18): {
        "titolo": "📚 Scuola full day",
        "attivita": "Corso di giapponese 6 ore (Minsai Saiin Campus: Classe Rossi aula 2C, Classe Blu aula 2F; 9:00-11:30 e 13:00-16:30). Sera: Pontocho.",
        "descrizione": "Prima giornata alla Kyoto Minsai Japanese Language School, divisi in due classi. Portare quaderno e penna. La sera, passeggiata sulla storica via di Pontocho, tra le case da tè sul fiume Kamo."
    },
    date(2026, 7, 19): {
        "titolo": "🏯 Osaka",
        "attivita": "Giornata a Osaka. Sera: Dotonbori.",
        "descrizione": "Osaka è la città più vivace del Giappone, famosa per il cibo e il carattere schietto degli abitanti. Dotonbori è il cuore della movida, con le insegne luminose enormi (il famoso Glico Man) e lo street food lungo il canale."
    },
    date(2026, 7, 20): {
        "titolo": "🦌 Uji + Nara (giornata con tutto il gruppo)",
        "attivita": "Uji e Nara, in giornata unica con l'intero gruppo (tutti ensemble). Sera: Nara.",
        "descrizione": "Uji è la capitale del tè matcha, con il Byodoin stampato sulla moneta da 10 yen. Nara fu la prima capitale del Giappone (710-784): il parco ospita ~1.200 cervi liberi considerati sacri, sfamati con crackers appositi."
    },
    date(2026, 7, 21): {
        "titolo": "⛩️ Scuola + Kiyomizudera + Gion",
        "attivita": "Corso 3 ore (Campus Plaza: Classe Rossi R5F6, Classe Blu R6F6). Pomeriggio 14:40-17:40: Kiyomizudera + Yasaka Pagoda + Yasaka Temple + Gion. Sera: Karasuma.",
        "descrizione": "Kiyomizudera (778 d.C.) è costruito su una scarpata con terrazza di legno a strapiombo. Gion è il quartiere delle geishe con le stradine di pietra e le case da tè del periodo Edo."
    },
    date(2026, 7, 22): {
        "titolo": "🏯 Scuola + Nijo + Fushimi Inari",
        "attivita": "Corso 3 ore (Campus Plaza: Classe Rossi R5F6, Classe Blu R6F6, 9:00-12:00). Pomeriggio: Castello Nijo + Fushimi Inari. Sera: Oicy Village.",
        "descrizione": "Il Castello Nijo fu residenza degli shogun Tokugawa nel XVII secolo, famoso per i 'corridoi usignolo' che scricchiolano per rivelare gli intrusi (UNESCO). Fushimi Inari è il santuario dei migliaia di torii arancioni sulla collina."
    },
    date(2026, 7, 23): {
        "titolo": "🎋 Scuola + Arashiyama + Karaoke",
        "attivita": "Corso 3 ore (Campus Plaza: Classe Rossi R8F6, Classe Blu R6F6). Pomeriggio 14:40-17:40: Arashiyama. Sera: Aeon Mall + Karaoke ore 21:00 (stanze prenotate 713/28, 704/16, 604/13).",
        "descrizione": "Arashiyama è il quartiere del bambù di Kyoto: il boschetto di bambù gigante è uno dei simboli del Giappone, insieme al Tempio Tenryu-ji (UNESCO) e al ponte Togetsukyo."
    },
    date(2026, 7, 24): {
        "titolo": "🌀 Scuola + TeamLab Biovortex",
        "attivita": "Corso 3 ore (Campus Plaza: Classe Rossi R2F6, Classe Blu R4F6, 9:00-12:00). Pomeriggio: TeamLab Biovortex (ingresso 14:00-14:30) + shopping.",
        "descrizione": "TeamLab Biovortex è una delle installazioni di arte digitale immersiva più spettacolari del Giappone. Un biglietto QR a testa, niente foto di gruppo, arrivo con mezzi pubblici."
    },
    date(2026, 7, 25): {
        "titolo": "📚 Scuola full day + Cena con Turno 2",
        "attivita": "Corso 6 ore (Tenjingawa Campus, aule 304/305, 9:00-11:30 e 13:00-16:30). Sera: cena tutti insieme + saluti al Turno 2 in partenza!",
        "descrizione": "Giornata di scuola nella sede Tenjingawa. La sera è speciale: cena condivisa con i ragazzi del Turno 2, che salutano prima del loro rientro in Italia."
    },
    date(2026, 7, 26): {
        "titolo": "📚 Scuola full day",
        "attivita": "Corso 6 ore (Tenjingawa Campus, aule 304/305, 9:00-11:30 e 13:00-16:30). Sera: Gion.",
        "descrizione": "Ultima giornata full day di scuola prima delle uscite finali a Kyoto. Attestato di frequenza in arrivo."
    },
    date(2026, 7, 27): {
        "titolo": "🍵 Kyoto sacra",
        "attivita": "Nishi Hongan-ji + Cerimonia del Tè ore 10:30 + Pranzo Mercato Nishiki + Padiglione d'Oro (Kinkaku-ji).",
        "descrizione": "Nishi Hongan-ji è il tempio madre del Buddhismo Shin. La cerimonia del tè (chado) è codificata da 500 anni. Nishiki è 'la cucina di Kyoto'. Il Kinkaku-ji è il monumento più fotografato del Giappone."
    },
    date(2026, 7, 28): {
        "titolo": "🚄 Shinkansen → Tokyo",
        "attivita": "Shinkansen Kyoto→Nagoya (NOZOMI 244, ore 8:54). Shinkansen Nagoya→Tokyo (NOZOMI 406, ore 14:29). Check-in Oriental Hotel Tokyo Bay. Sera: Tokyo Metropolitan Government Building + Shinjuku.",
        "descrizione": "Prima esperienza sullo Shinkansen: 300 km/h, puntualità al secondo. La sera, terrazza gratuita del Metropolitan Government Building: vista a 360° dalla quota 243 m su tutta Tokyo."
    },
    date(2026, 7, 29): {
        "titolo": "🗼 Tokyo",
        "attivita": "Mattina: Tokyo Tower + Shibuya + Tempio Meiji + Harajuku. Sera: Crociera Odaiba + Odaiba + Statua della Libertà + Gundam (Diver City Tokyo Plaza, 2F).",
        "descrizione": "Shibuya Crossing è l'incrocio pedonale più trafficato del mondo. Il Tempio Meiji è un'oasi di foresta nella metropoli. Harajuku è la capitale della moda giovanile. Odaiba offre la replica della Statua della Libertà e il gigantesco Gundam in scala 1:1."
    },
    date(2026, 7, 30): {
        "titolo": "🏠 Akihabara + Asakusa + Rientro",
        "attivita": "Mattina: Akihabara + Asakusa. Rientro in hotel e partenza per l'aeroporto. Volo TK199 da Tokyo Haneda Terminal 3 ore 21:35/21:45.",
        "descrizione": "Akihabara è il paradiso di elettronica e anime/manga. Asakusa è il quartiere più antico di Tokyo (Tempio Sensoji, via Nakamise). Sera: partenza per Istanbul con Turkish Airlines."
    },
    date(2026, 7, 31): {
        "titolo": "🏠 Rientro in Italia",
        "attivita": "Arrivo Istanbul ore 04:50/05:05. Chi parte da Roma: TK1861 Istanbul 07:35 → Roma FCO T3 09:20. Chi parte da Milano: TK1873 Istanbul 06:55 → Milano MXP 08:40.",
        "descrizione": "Scalo tecnico a Istanbul, poi due voli separati per Roma Fiumicino e Milano Malpensa. Le famiglie accolgono i ragazzi ai rispettivi aeroporti."
    },
}

# ─── BASE DI CONOSCENZA ───────────────────────────────────────────────────────
KNOWLEDGE_BASE = """
Sei l'assistente ufficiale dello staff del viaggio GIAPPONE DISCOVERY - TURNO 3 organizzato da Accademia Britannica / Travel Experts.
Rispondi sempre in italiano, in modo chiaro e conciso. Sei riservato a uso interno staff.
Il rooming è di SOLA LETTURA: se lo staff chiede di spostare qualcuno di stanza, rispondi che le modifiche al foglio vanno fatte a mano su Google Sheets, ma puoi registrare la variazione come nota.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INFORMAZIONI GENERALI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Viaggio: Giappone Discovery - Turno 3
Date: 16 luglio 2026 → 31 luglio 2026 (arrivo Osaka 17/07, rientro Italia 31/07)
Partecipanti: 54 ragazzi/assistenti + 3 TL = 57 pax (+ 1 TL, Francesca Guerrato, in prosecuzione dal Turno 2)
TL Staff: Gabriella Manno, Giulia Carbone, Matteo Filippini (+ Francesca Guerrato in prosecuzione)
Assistenza voli/treni (solo mattina partenze) WhatsApp Francesca: +39 349 871 0515
Braccialetti: TUTTI VERDI — nessuna divisione in gruppi colore (le "classi" Rossi/Blu sono solo i due gruppi-scuola, non colori braccialetto).
Gruppo grande: due punti di partenza principali (Roma Fiumicino e Milano Malpensa) con avvicinamenti da Bari, Catania, Napoli, Palermo, Bologna, Venezia, Alghero.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VOLI - TURKISH AIRLINES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DA ROMA FIUMICINO (ritrovo ore 17:00, banco Turkish Airlines T3):
  ANDATA:  TK1864 | 16/07 | Roma FCO T3 19:55 → Istanbul 23:35
           TK086  | 17/07 | Istanbul 02:10 → Osaka Kansai T1 18:50
  RITORNO: TK199  | 30/07 | Tokyo Haneda T3 21:45 → Istanbul 31/07 04:50
           TK1861 | 31/07 | Istanbul 07:35 → Roma FCO T3 09:20
DA MILANO MALPENSA (ritrovo ore 17:00, banco Turkish Airlines T1):
  ANDATA:  TK1876 | 16/07 | Milano MXP 19:45 → Istanbul 23:40
           TK086  | 17/07 | Istanbul 02:10 → Osaka Kansai T1 18:50 (stesso volo di collegamento di Roma)
  RITORNO: TK199  | 30/07 | Tokyo Haneda T3 21:45 → Istanbul 31/07 05:05
           TK1873 | 31/07 | Istanbul 06:55 → Milano MXP 08:40
AVVICINAMENTI (senza accompagnatore AB fino a Roma/Milano):
  Da Cagliari, Catania, Palermo, Alghero: volo nazionale fino a Roma Fiumicino (assistenza solo la mattina della partenza).
  Da Venezia (o altre città con Frecciarossa/Italo): treno alta velocità fino a Roma Termini o Milano Centrale, poi Leonardo Express (per Roma) o Malpensa Express (per Milano) con personale Accademia Britannica — i biglietti li ha il referente in loco.
Bagaglio: 1 stiva max 20 kg (somma dimensioni ≤160 cm) + 1 zaino max 8 kg.
Carte d'imbarco: conservarle TUTTE fino al rientro (obbligo portale INPS).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOTEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KYOTO (17→28/07): Oriental Hotel Kyoto Rokujo — 181 Bokumikanabutsucho, Shimogyo Ward
  Tel +81 75-343-8111 | inquiry@kyotorokujo.oriental-hotels.com
  Camere: triple (+2 doppie ragazze, 1 doppia ragazzi). Colazione 6:45→9:30.
TOKYO (28→30/07): Oriental Hotel Tokyo Bay — 1-8-2 Mihama, Urayasu, Chiba
  Tel +81 47-350-8111 | info@oriental-hotel.co.jp
  Camere: quadruple (+3 doppie).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROOMING KYOTO (Oriental Hotel Kyoto Rokujo)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stanza 1 [tripla F, Bari]: DE BRACO Maria Rita | FACCILONGO Mariachiara | ZOPPI Aurora
Stanza 2 [tripla F, Bari]: DELLI CARRI Maria | BONASIA Ilaria | LOJACONO Silvia
Stanza 3 [tripla F, Milano]: COCCO Asia | MANNAI Eleonora | COSTA Angela
Stanza 4 [tripla F, Bari/Palermo]: MARINELLI Egle | BURRIESCI Giuliana | LO BAIDO Vittoria
Stanza 5 [tripla F, Catania]: COSTA Aurora | LO BARTOLO Carola Maria | RIGGI Giorgia
Stanza 6 [tripla F, Napoli]: D'ANIELLO Giulia | D'ORTA Martina | ROSSI Martina
Stanza 7 [tripla F, Roma]: DI GIORGIO Sofia | LUCIOLI Maria Vittoria | SPINA Martina
Stanza 8 [tripla F, Roma]: DI VICO Flavia | PIANESE Francesca | VECCHIOTTI Guenda
Stanza 9 [doppia F, Venezia]: PASCOLI Emma | PASCOLI Sofia (sorella, assistente)
Stanza 10 [doppia F, Roma/Milano]: CAPRIOTTI Vittoria | DE ANGELIS Lavinia (richiesta letti singoli)
Stanza 11 [tripla M, Alghero/Bari]: GARAU Gabriele | ANCONA Alessandro | ANSANI Antonio Zhelyazko
Stanza 12 [tripla M, Bari]: BIANCO Riccardo | PALMERI Federico | VERRIELLO Giovanni
Stanza 13 [tripla M, Bologna/Catania]: MILLI Nicholas | CLEMENTI Aurelio Rosario | GENOVESE Andrea
Stanza 14 [tripla M, Milano]: BARBAGALLO Fabrizio | CARULLI Roberto Maria | GENTILE Damiano
Stanza 15 [tripla M, Milano/Napoli]: OTERI Gianluca | SPADARO Alessandro | DELLA GATTA Salvatore
Stanza 16 [tripla M, Palermo/Roma]: TARGIA Francesco | ADDESSE Damiano | MAFFIA Simone
Stanza 17 [tripla M, Roma]: DI PAOLO Christian | LA VECCHIA Antonio | SPINA Daniele
Stanza 18 [tripla M, Roma]: PISANO Raffaele | PIZZUTO Oscar | PRACILIO Giulio
Stanza 19 [doppia, Venezia]: PIAZZO Chiara (assistente/mamma) | TORRICELLI Alessandro
Singola: GUERRATO Francesca (TL in prosecuzione dal Turno 2)
TL: MANNO Gabriella, CARBONE Giulia, FILIPPINI Matteo

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROOMING TOKYO (Oriental Hotel Tokyo Bay)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stanza 1 [quadrupla F, Bari]: DE BRACO Maria Rita | DELLI CARRI Maria | FACCILONGO Mariachiara | ZOPPI Aurora
Stanza 2 [quadrupla F, Bari/Milano]: BONASIA Ilaria | LOJACONO Silvia | COCCO Asia | MANNAI Eleonora
Stanza 3 [quadrupla F, Milano/Bari/Catania]: COSTA Angela | MARINELLI Egle | COSTA Aurora | LO BARTOLO Carola Maria
Stanza 4 [quadrupla F, Catania/Napoli]: RIGGI Giorgia | D'ANIELLO Giulia | D'ORTA Martina | ROSSI Martina
Stanza 5 [quadrupla F, Roma]: DI GIORGIO Sofia | LUCIOLI Maria Vittoria | SPINA Martina | DI VICO Flavia
Stanza 6 [quadrupla F, Roma/Palermo]: PIANESE Francesca | VECCHIOTTI Guenda | BURRIESCI Giuliana | LO BAIDO Vittoria
Stanza 7 [doppia F, Roma/Milano]: CAPRIOTTI Vittoria | DE ANGELIS Lavinia
Stanza 8 [doppia F, Venezia]: PASCOLI Emma | PASCOLI Sofia
Stanza 9 [quadrupla M, Alghero/Bari]: GARAU Gabriele | ANCONA Alessandro | ANSANI Antonio Zhelyazko | BIANCO Riccardo
Stanza 10 [quadrupla M, Bari/Bologna/Catania]: PALMERI Federico | VERRIELLO Giovanni | MILLI Nicholas | CLEMENTI Aurelio Rosario
Stanza 11 [quadrupla M, Catania/Milano]: GENOVESE Andrea | BARBAGALLO Fabrizio | CARULLI Roberto Maria | GENTILE Damiano
Stanza 12 [quadrupla M, Milano/Napoli/Palermo]: OTERI Gianluca | SPADARO Alessandro | DELLA GATTA Salvatore | TARGIA Francesco
Stanza 13 [quadrupla M, Roma]: MAFFIA Simone | PISANO Raffaele | PIZZUTO Oscar | PRACILIO Giulio
Stanza 14 [quadrupla M, Roma]: ADDESSE Damiano | LA VECCHIA Antonio | DI PAOLO Christian | SPINA Daniele
Stanza 15 [doppia, Venezia]: PIAZZO Chiara | TORRICELLI Alessandro
Singola: GUERRATO Francesca (TL in prosecuzione dal Turno 2)
TL: MANNO Gabriella, CARBONE Giulia, FILIPPINI Matteo

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INFO MEDICHE / ATTENZIONI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRACILIO Giulio     → Art. 3 comma 3, no accompagnatori. Portatore di impianto cocleare, autonomo. Verificare adattatore corrente per ricaricare gli impianti. Di notte non li indossa e non sente: il compagno di stanza deve fargli un cenno per svegliarlo.
TORRICELLI Alessandro + PIAZZO Chiara (mamma) → Art. 3 comma 3, 1 accompagnatore. ENTRAMBI CELIACI (attenzione: la celiachia è poco nota/gestita in Giappone, possibile difficoltà a garantire non contaminazione). Alessandro è autistico, gestito completamente dalla mamma: stanza insieme sempre.
PASCOLI Emma + PASCOLI Sofia (sorella maggiore, assistente) → Art. 3 comma 3, 1 accompagnatore famiglia. Emma autonoma dal punto di vista motorio e intellettivo. Terapia farmacologica quotidiana gestita dalla sorella (se presa regolarmente nessun problema). Nessuna allergia. Richiesta camera doppia.
TARGIA Francesco    → Art. 3 comma 1. Nessuna indicazione medica. Già partecipante ad altri soggiorni con noi (Londra).
MARINELLI Egle      → Allergica a polvere e kiwi
LO BARTOLO Carola M.→ Intollerante al lattosio
COSTA Angela        → Allergia a vespa/imenotteri
DE ANGELIS Lavinia  → Richiesta camera con letti singoli (non a castello)
Nessuna segnalazione: Ancona, Ansani, Bianco, Bonasia, Delli Carri, Faccilongo, Lojacono, Palmeri, Verriello, Zoppi Aurora, Milli, Clementi, Costa Aurora, Genovese, Riggi, D'Aniello, D'Orta, Della Gatta, Rossi Martina, Burriesci, Lo Baido, Addesse, Capriotti, Di Giorgio, Di Paolo, Di Vico, La Vecchia, Lucioli, Maffia, Pianese, Pisano, Pizzuto, Spina Daniele, Spina Martina, Vecchiotti, Barbagallo, Carulli, Cocco, Gentile, Mannai, Oteri, Spadaro, Garau

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MATERIALE CONSEGNATO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ogni partecipante riceve: carta prepagata Mastercard (€220) + carta ICOCA trasporti + braccialetto VERDE.
Numeri carta (in ordine di stanza Kyoto): 00877 DE BRACO Maria Rita → 00930 TORRICELLI Alessandro.
00877 DE BRACO Maria Rita | 00878 FACCILONGO Mariachiara | 00879 ZOPPI Aurora | 00880 DELLI CARRI Maria
00881 BONASIA Ilaria | 00882 LOJACONO Silvia | 00883 COCCO Asia | 00884 MANNAI Eleonora
00885 COSTA Angela | 00886 MARINELLI Egle | 00887 BURRIESCI Giuliana | 00888 LO BAIDO Vittoria
00889 COSTA Aurora | 00890 LO BARTOLO Carola Maria | 00891 RIGGI Giorgia | 00892 D'ANIELLO Giulia
00893 D'ORTA Martina | 00894 ROSSI Martina | 00895 DI GIORGIO Sofia | 00896 LUCIOLI Maria Vittoria
00897 SPINA Martina | 00898 DI VICO Flavia | 00899 PIANESE Francesca | 00900 VECCHIOTTI Guenda
00901 PASCOLI Emma | 00902 PASCOLI Sofia | 00903 CAPRIOTTI Vittoria | 00904 DE ANGELIS Lavinia
00905 GARAU Gabriele | 00906 ANCONA Alessandro | 00907 ANSANI Antonio Zhelyazko | 00908 BIANCO Riccardo
00909 PALMERI Federico | 00910 VERRIELLO Giovanni | 00911 MILLI Nicholas | 00912 CLEMENTI Aurelio Rosario
00913 GENOVESE Andrea | 00914 BARBAGALLO Fabrizio | 00915 CARULLI Roberto Maria | 00916 GENTILE Damiano
00917 OTERI Gianluca | 00918 SPADARO Alessandro | 00919 DELLA GATTA Salvatore | 00920 TARGIA Francesco
00921 ADDESSE Damiano | 00922 MAFFIA Simone | 00923 DI PAOLO Christian | 00924 LA VECCHIA Antonio
00925 SPINA Daniele | 00926 PISANO Raffaele | 00927 PIZZUTO Oscar | 00928 PRACILIO Giulio
00929 PIAZZO Chiara | 00930 TORRICELLI Alessandro
Saldo carta: getmybalance.com

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCUOLA DI GIAPPONESE - Kyoto Minsai (Group 3, max 51 studenti, 2 classi: ROSSI e BLU)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Nota: "Rossi" e "Blu" sono i nomi delle due classi/aule, NON hanno relazione con i braccialetti (tutti verdi).
18/07 sab │ 6 ore │ 9:00-11:30 / 13:00-16:30 │ Minsai Saiin Campus (Rossi: aula 2C, Blu: aula 2F)
19/07 dom │ NIENTE SCUOLA (Osaka)
20/07 lun │ NIENTE SCUOLA (Uji + Nara, tutto il gruppo insieme)
21/07 mar │ 3 ore │ 9:00-12:00 (pom. 14:40-17:40 uscita) │ Campus Plaza (Rossi: R5F6, Blu: R6F6)
22/07 mer │ 3 ore │ 9:00-12:00 │ Campus Plaza (Rossi: R5F6, Blu: R6F6)
23/07 gio │ 3 ore │ 9:00-12:00 (pom. 14:40-17:40 uscita) │ Campus Plaza (Rossi: R8F6, Blu: R6F6)
24/07 ven │ 3 ore │ 9:00-12:00 │ Campus Plaza (Rossi: R2F6, Blu: R4F6)
25/07 sab │ 6 ore │ 9:00-11:30 / 13:00-16:30 │ Tenjingawa Campus (aule 304/305)
26/07 dom │ 6 ore │ 9:00-11:30 / 13:00-16:30 │ Tenjingawa Campus (aule 304/305)
Indirizzo Minsai: 69 Nishikyogoku Kitaooiri-cho, Ukyo-ku, Kyoto | Tel: 075-316-0190

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EVENTI PRENOTATI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- TeamLab Biovortex Kyoto: 24/07 ingresso 14:00-14:30, biglietti QR individuali (PDF su Drive, 2 gruppi). No foto di gruppo, no bus privati.
- Karaoke: 23/07 ore 21:00, stanze prenotate 713/28, 704/16, 604/13.
- Cerimonia del Tè (AN KYOTO): 27/07 ore 10:30. Tel +81-80-9307-1873.
- Shinkansen Kyoto→Nagoya→Tokyo: 28/07 ore 8:54 (NOZOMI 244) e 14:29 (NOZOMI 406). QR ticket nella cartella Drive 'Qr-code Ticket Shinkansen Turno 3'.
- Cena ensemble con saluti al Turno 2: sera del 25/07.
- Jankara QR Code discount: sconto karaoke, foto nella cartella Drive.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOTE OPERATIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Partenze/rientri su due aeroporti: Roma Fiumicino (15 pax + avvicinamenti da Cagliari/Catania/Palermo/Alghero via aereo o Venezia/altre città via treno+Leonardo Express) e Milano Malpensa (9 pax + avvicinamenti da Venezia via treno+Malpensa Express).
- Fuso: +7h rispetto all'Italia. Cambio: ~168 yen per euro.
- SIM: eSIM Holafly/Airalo consigliata, oppure SIM in aeroporto. Wi-fi in hotel.
- ICOCA precaricata per i trasporti col gruppo. NON trasferirla nel wallet iPhone.
- Modifiche a programma o rooming: lo staff le comunica via chat, il bot le registra e le riporta.
"""

# ─── BRIEFING ARRIVO ──────────────────────────────────────────────────────────
BRIEFING_P1 = """🎌 *BRIEFING ARRIVO KYOTO — Giappone Discovery T3*

Benvenuti in Giappone! Ora ci aspetta circa *1h30 di bus* per raggiungere l'hotel — *Oriental Hotel Kyoto Rokujo*.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚌 *ICOCA — Carta Trasporti*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Nella bustina ricevete l'*ICOCA* con credito pre-caricato, da usare *solo per gli spostamenti col gruppo*. Se la usate per acquisti personali ai distributori dovrete ricaricarla a vostre spese.

⚠️ *NON trasferite l'ICOCA nel wallet dell'iPhone* — diventa inutilizzabile e dovrete ricomprarne una nuova.

• Portatela *SEMPRE* con voi ogni volta che uscite
• Metro/treno: *tap all'ingresso E all'uscita* — aspettate il *BIP*, non passate col tornello di qualcun altro
• Sui mezzi pubblici non si parla (o sottovoce)
• Bus: si sale da dietro, si scende da davanti. Si tappa l'ICOCA *solo quando si scende*. Su alcuni bus vi diremo noi quando tapparla anche in salita"""

BRIEFING_P2 = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💳 *Carta Mastercard Prepagata (€220)*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Nella bustina trovate anche la *carta prepagata Mastercard*, senza PIN — si può *solo strisciare*. Spiegalo sempre all'esercente e provatela da entrambi i lati.

• *Budget pasti: 1.400–1.500 yen a pasto*, autogestito (se a pranzo spendo 1.000, a cena posso spendere 1.800)
• Dove accettano carta: pagate sempre con la card
• Se viene smarrita: segnalatecelo subito
• Saldo: *getmybalance.com*
• Stasera vi aiutiamo a registrarla su Apple Pay / Google Pay (guida nel gruppo WhatsApp)
• La carta rimane vostra — se avanzano soldi è spendibile anche in Italia

Nella bustina c'è anche il *braccialetto verde* — quest'anno siamo un gruppo unico, tenetelo al polso: serve a riconoscervi nei luoghi affollati. Non toglietevelo. Le due classi (Rossi/Blu) valgono solo per la scuola, non per il resto del programma."""

BRIEFING_P3 = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏨 *Hotel — Oriental Hotel Kyoto Rokujo*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Max *2 tessere magnetiche per camera* — non perdetele
• Per salire in ascensore serve la tessera: tenetelo a mente quando uscite
• In camera: inserite la tessera nella *fessura* vicino all'ingresso per abilitare la corrente

🚭 *VIETATO FUMARE IN CAMERA* — fee di *¥30.000* se viene rilevato odore. Si fuma solo nella *Smoking Room al Piano 1*. Anche fuori: solo nelle zone fumo segnalate vicino ai konbini.

• Per la pulizia della stanza: magnete *"PLEASE MAKE MY ROOM"* fuori dalla porta la mattina
• Bollitore, tè e caffè: gratuiti | Ciabattine e pigiami: in dotazione, *non portarli via*
• Asciugamani, shampoo ecc.: rimangono in stanza (se mancano li addebitano)
• *Passaporto: lasciatelo in cassaforte* fino al check-out per Tokyo
• *Colazione:* 6:45 → 9:30 (consigliata dopo le 7:45)
• *Snack e bevande in lobby:* gratuiti 14:30 → 23:00
• *Lavanderia (Piano 1):* ¥500–600 in monete da ¥100, durata ~2h — svuotate subito a fine ciclo
• Acqua del rubinetto potabile — usate il distributore al piano terra

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🍜 *Stasera — Noodles Party*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
In lobby trovate noodles istantanei e snack. Disfate le valigie e scendete a prenderli!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 *Domani — Lezione di Giapponese (full day)*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*Partenza dall'hotel puntuali.* Lezione 9:00-11:30 e 13:00-16:30 (Minsai Saiin Campus, aule 2C/2F).
Nello zaino: 📓 quaderno e penna, 🌂 mantellina/k-way + ombrello, maglia e calzini di ricambio, ICOCA sempre.

Buona prima notte in Giappone\\! 🇯🇵"""

# ─── STATO APPELLO ────────────────────────────────────────────────────────────
appello_state: dict[int, dict] = {}
modifiche_log: list[str] = []
conversation_history: dict[int, list] = {}

claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def get_programma_oggi() -> str:
    oggi = date.today()
    if oggi in PROGRAMMA:
        p = PROGRAMMA[oggi]
        return (f"📅 *Oggi — {oggi.strftime('%d/%m/%Y')}*\n*{p['titolo']}*\n\n"
                f"*Attività:* {p['attivita']}\n\n*Info:* {p['descrizione']}")
    return f"Nessun programma registrato per oggi ({oggi.strftime('%d/%m/%Y')})."

def get_programma_data(d: date) -> str:
    if d in PROGRAMMA:
        p = PROGRAMMA[d]
        return (f"📅 *{d.strftime('%d/%m/%Y')}*\n*{p['titolo']}*\n\n"
                f"*Attività:* {p['attivita']}\n\n*Info:* {p['descrizione']}")
    return f"Nessun programma per il {d.strftime('%d/%m/%Y')}."

# ─── COMPLEANNI ───────────────────────────────────────────────────────────────
PARTECIPANTI_DATE = [
    ("ANCONA Alessandro",         date(2007,  2,  7)),
    ("ANSANI Antonio Zhelyazko",  date(2007,  2, 13)),
    ("BIANCO Riccardo",           date(2007,  9, 24)),
    ("BONASIA Ilaria",            date(2008,  5, 21)),
    ("DE BRACO Maria Rita",       date(2008,  9, 17)),
    ("DELLI CARRI Maria",         date(2008,  9, 30)),
    ("FACCILONGO Mariachiara",    date(2009,  5, 24)),
    ("LOJACONO Silvia",           date(2009,  3,  8)),
    ("MARINELLI Egle",            date(2007,  6,  1)),
    ("PALMERI Federico",          date(2008,  7, 14)),
    ("VERRIELLO Giovanni",        date(2008, 10,  6)),
    ("ZOPPI Aurora",              date(2008,  6, 15)),
    ("MILLI Nicholas",            date(2007, 11,  1)),
    ("CLEMENTI Aurelio Rosario",  date(2008,  9, 12)),
    ("COSTA Aurora",              date(2008, 11,  5)),
    ("GENOVESE Andrea",           date(2008,  5,  2)),
    ("LO BARTOLO Carola Maria",   date(2007,  5, 14)),
    ("RIGGI Giorgia",             date(2007, 11, 17)),
    ("D'ANIELLO Giulia",          date(2008,  7,  3)),
    ("D'ORTA Martina",            date(2008,  7, 13)),
    ("DELLA GATTA Salvatore",     date(2008,  5, 28)),
    ("ROSSI Martina",             date(2008,  9, 26)),
    ("BURRIESCI Giuliana",        date(2008,  1,  8)),
    ("LO BAIDO Vittoria",         date(2007, 11, 12)),
    ("TARGIA Francesco",          date(2007,  3, 25)),
    ("ADDESSE Damiano",           date(2008, 11,  9)),
    ("CAPRIOTTI Vittoria",        date(2008,  1, 16)),
    ("DI GIORGIO Sofia",          date(2009,  8, 12)),
    ("DI PAOLO Christian",        date(2011,  4,  7)),
    ("DI VICO Flavia",            date(2008,  4, 20)),
    ("LA VECCHIA Antonio",        date(2009,  5, 12)),
    ("LUCIOLI Maria Vittoria",    date(2011,  1,  1)),
    ("MAFFIA Simone",             date(2007, 10, 24)),
    ("PIANESE Francesca",         date(2007,  8, 31)),
    ("PISANO Raffaele",           date(2008,  5, 11)),
    ("PIZZUTO Oscar",             date(2007, 10, 30)),
    ("PRACILIO Giulio",           date(2007,  3,  2)),
    ("SPINA Daniele",             date(2011, 10,  8)),
    ("SPINA Martina",             date(2008, 10, 13)),
    ("VECCHIOTTI Guenda",         date(2007,  7, 29)),
    ("BARBAGALLO Fabrizio",       date(2006,  3, 26)),
    ("CARULLI Roberto Maria",     date(2007, 10,  9)),
    ("COCCO Asia",                date(2009,  2, 24)),
    ("COSTA Angela",              date(2007,  9, 14)),
    ("DE ANGELIS Lavinia",        date(2007, 12,  3)),
    ("GENTILE Damiano",           date(2008,  2, 16)),
    ("MANNAI Eleonora",           date(2008,  7, 19)),
    ("OTERI Gianluca",            date(2009,  1, 15)),
    ("SPADARO Alessandro",        date(2007,  6, 17)),
    ("PASCOLI Emma",              date(2007,  6,  1)),
    ("PASCOLI Sofia",             date(2005,  6, 12)),
    ("PIAZZO Chiara",             date(1967,  1, 27)),
    ("TORRICELLI Alessandro",     date(2007, 12, 10)),
    ("GARAU Gabriele",            date(2008,  4,  7)),
]

INIZIO_TURNO = date(2026, 7, 16)
FINE_TURNO   = date(2026, 7, 31)

def _compleanni_testo() -> str:
    trovati = [
        (d.replace(year=2026), nome)
        for nome, d in PARTECIPANTI_DATE
        if INIZIO_TURNO <= d.replace(year=2026) <= FINE_TURNO
    ]
    trovati.sort()
    if trovati:
        righe = "\n".join(f"🎂 *{nome}* — {d.strftime('%d/%m')}" for d, nome in trovati)
        return f"*Compleanni durante il turno (16 lug–31 lug):*\n\n{righe}"
    return "Nessun compleanno durante il turno."

# ─── COMANDI ──────────────────────────────────────────────────────────────────
async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.full_name
    await update.message.reply_text(
        f"👤 *{name}*\n🆔 Il tuo ID Telegram è: `{uid}`\n\nMandalo al responsabile per ottenere l'accesso.",
        parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    await update.message.reply_text(
        "👋 Ciao! Sono l'assistente staff *Giappone Discovery - Turno 3*.\n\n"
        "Puoi scrivermi in linguaggio libero oppure usare questi comandi:\n\n"
        "🎌 /briefing — briefing di arrivo (ICOCA, carte, hotel, regole)\n"
        "📅 /oggi — programma e descrizione di oggi\n"
        "📢 /appello — appello del gruppo (tutti verdi)\n"
        "🎂 /compleanni — compleanni durante il turno\n"
        "🎙️ _Vocale_ — trascrive e salva nel diario viaggio\n"
        "📖 /diario — ultime voci del diario\n"
        "📋 /modifiche — vedi le modifiche registrate\n"
        "❓ /help — esempi di domande\n"
        "🔄 /reset — cancella cronologia chat",
        parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    await update.message.reply_text(
        "📌 *Esempi di domande:*\n"
        "• \"In che stanza è PRACILIO Giulio a Kyoto?\"\n"
        "• \"Chi ha allergie?\"\n"
        "• \"Cosa facciamo il 24 luglio?\"\n"
        "• \"Numero carta di Emma Pascoli?\"\n"
        "• \"A che ora è lo Shinkansen per Tokyo?\"\n"
        "• \"Chi parte da Milano?\"\n"
        "• \"A che ora è il volo di rientro da Roma?\"\n\n"
        "Oppure usa /appello per fare l'appello interattivo.",
        parse_mode="Markdown")

async def briefing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    for parte in [BRIEFING_P1, BRIEFING_P2, BRIEFING_P3]:
        await update.message.reply_text(parte, parse_mode="Markdown")

async def oggi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    await update.message.reply_text(get_programma_oggi(), parse_mode="Markdown")

async def compleanni_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    await update.message.reply_text(_compleanni_testo(), parse_mode="Markdown")

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

# ─── APPELLO (gruppo unico) ───────────────────────────────────────────────────
async def appello_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    user_id = update.effective_user.id
    appello_state[user_id] = {
        "gruppo": "🟢 VERDE (tutti)",
        "nomi": PARTECIPANTI_T3.copy(),
        "indice": 0,
        "presenti": [],
        "assenti": [],
        "saltati": [],
        "giro": 1,
    }
    await update.message.reply_text(
        f"📢 *Appello — gruppo unico ({len(PARTECIPANTI_T3)} persone)*",
        parse_mode="Markdown")
    await _invia_prossimo_nome(update.message, user_id)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

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
            stato["saltati"].append(nome_corrente)

        stato["indice"] += 1

        if stato["indice"] >= len(stato["nomi"]):
            saltati_rimasti = stato["saltati"]
            if saltati_rimasti:
                stato["nomi"]    = saltati_rimasti.copy()
                stato["saltati"] = []
                stato["indice"]  = 0
                stato["giro"]   += 1
                avviso = (f"↩️ *Giro {stato['giro']} — Saltati ({len(saltati_rimasti)}):*\n"
                          + "\n".join(f"• {n}" for n in saltati_rimasti))
                await query.message.reply_text(avviso, parse_mode="Markdown")
                await _invia_prossimo_nome(query.message, user_id)
            else:
                presenti = stato["presenti"]
                assenti  = stato["assenti"]
                del appello_state[user_id]
                testo = (
                    f"✅ *Appello completato!*\n\n"
                    f"*Presenti ({len(presenti)}):* {', '.join(presenti) if presenti else '—'}\n\n"
                    f"*Assenti ({len(assenti)}):* {', '.join(assenti) if assenti else '—'}\n")
                await query.message.reply_text(testo, parse_mode="Markdown")
        else:
            await _invia_prossimo_nome(query.message, user_id)

async def _invia_prossimo_nome(message, user_id: int):
    stato = appello_state[user_id]
    idx    = stato["indice"]
    totale = len(stato["nomi"])
    nome   = stato["nomi"][idx]
    giro   = stato.get("giro", 1)

    keyboard = [[
        InlineKeyboardButton("✅ Presente", callback_data="presente"),
        InlineKeyboardButton("❌ Assente",  callback_data="assente"),
        InlineKeyboardButton("⏭ Salta",    callback_data="salta"),
    ]]
    intestazione = f"🟢 — {idx+1}/{totale}"
    if giro > 1:
        intestazione += f"  ♻️ Giro {giro} (saltati)"
    await message.reply_text(
        f"{intestazione}\n\n👤 *{nome}*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown")

# ─── VOCALI / DIARIO ──────────────────────────────────────────────────────────
async def handle_voice_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    msg = update.message
    audio_obj = msg.voice or msg.audio
    if not audio_obj:
        return
    await msg.reply_text("🎙️ Sto trascrivendo il vocale…")
    try:
        tg_file = await context.bot.get_file(audio_obj.file_id)
        suffix = ".ogg" if msg.voice else ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
        await tg_file.download_to_drive(tmp_path)
        testo = trascrivi_audio(tmp_path)
        os.remove(tmp_path)
        user = msg.from_user
        mittente = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or str(user.id)
        link = salva_nel_diario(mittente, testo)
        risposta = (
            f"✅ *Vocale trascritto e salvato nel diario* (Giorno {_giorno_viaggio()} — {_citta_oggi()})\n\n"
            f"📝 _{testo}_\n\n📊 [Apri il diario]({link})")
        await msg.reply_text(risposta, parse_mode="Markdown")
    except Exception as e:
        await msg.reply_text(f"❌ Errore durante la trascrizione: {e}")

async def diario_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    try:
        sh = get_or_create_diary_sheet()
        ws = sh.sheet1
        rows = ws.get_all_values()
        if len(rows) <= 1:
            await update.message.reply_text("📖 Il diario è ancora vuoto. Manda un vocale per iniziare!")
            return
        ultime = rows[1:][-10:]
        testo = f"📖 *Diario Viaggio — ultime {len(ultime)} voci:*\n\n"
        for r in ultime:
            n, data, ora, giorno, citta, mittente, trascrizione, *_ = r + [""] * 8
            testo += f"*G{giorno} — {citta}* | {data} {ora} | _{mittente}_\n{trascrizione[:200]}{'…' if len(trascrizione) > 200 else ''}\n\n"
        link = f"https://docs.google.com/spreadsheets/d/{_diary_sheet_id}"
        testo += f"[📊 Foglio completo]({link})"
        await update.message.reply_text(testo, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")

# ─── MESSAGGI LIBERI (AI) ─────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    user_id = update.effective_user.id

    if user_id in appello_state:
        await update.message.reply_text("Hai un appello in corso — usa i pulsanti per rispondere, o /reset per annullarlo.")
        return

    user_text = update.message.text

    if any(k in user_text.lower() for k in ["cosa facciamo oggi", "programma di oggi", "oggi cosa"]):
        await update.message.reply_text(get_programma_oggi(), parse_mode="Markdown")
        return

    if any(k in user_text.lower() for k in ["complean", "compie gli anni", "festeggia", "nato il", "nata il"]):
        await update.message.reply_text(_compleanni_testo(), parse_mode="Markdown")
        return

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": user_text})
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        programma_testo = "\n".join(
            f"{d.strftime('%d/%m')}: {v['titolo']} — {v['attivita']}"
            for d, v in PROGRAMMA.items())
        system = KNOWLEDGE_BASE + f"\n\nPROGRAMMA COMPLETO:\n{programma_testo}"

        if modifiche_log:
            system += "\n\nMODIFICHE REGISTRATE DALLO STAFF:\n" + "\n".join(f"- {m}" for m in modifiche_log)

        response = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system,
            messages=conversation_history[user_id])

        reply = response.content[0].text

        # T3: rooming di sola lettura — le richieste di spostamento vengono
        # registrate come nota (nessuna scrittura sul foglio).
        if any(k in user_text.lower() for k in ["sposta", "cambia stanza", "trasferisci", "metti in stanza"]):
            modifiche_log.append(f"[{date.today()}] NOTA (manuale): {user_text}")
            reply += ("\n\n📝 Registrato come nota (vedi /modifiche). "
                      "Il foglio rooming va aggiornato a mano su Google Sheets.")

        conversation_history[user_id].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Errore API: {type(e).__name__}: {e}")
        await update.message.reply_text(f"⚠️ Errore: `{type(e).__name__}: {str(e)[:200]}`", parse_mode="Markdown")

# ─── AVVIO ────────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("myid",       myid_command))
    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("help",       help_command))
    app.add_handler(CommandHandler("briefing",   briefing_command))
    app.add_handler(CommandHandler("oggi",       oggi_command))
    app.add_handler(CommandHandler("appello",    appello_command))
    app.add_handler(CommandHandler("diario",     diario_command))
    app.add_handler(CommandHandler("modifiche",  modifiche_command))
    app.add_handler(CommandHandler("compleanni", compleanni_command))
    app.add_handler(CommandHandler("reset",      reset))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_note))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Bot T3 avviato.")
    app.run_polling()

if __name__ == "__main__":
    main()
