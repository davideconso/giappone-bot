"""
Bot Telegram - Giappone Discovery Turno 2
Staff assistant per il viaggio 14/07/2026 - 28/07/2026

SETUP:
1. Crea un bot su Telegram tramite @BotFather → ottieni il TOKEN
2. Variabili d'ambiente: TELEGRAM_TOKEN, ANTHROPIC_API_KEY, GROQ_API_KEY,
   GOOGLE_CREDENTIALS_JSON, (opz.) DIARY_SHEET_ID
3. Avvio: python giappone_bot_t2.py

NOTA T2: niente gruppi colore — appello unico (braccialetti tutti verdi).
Il rooming è di sola lettura (hardcoded + Google Sheet in tempo reale).
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
# Rooming T2 (Google Sheet, sola lettura)
ROOMING_SHEET_IDS = [
    "1IAhObp4MgHhYrlyKhBXPmhuCS5WNcFJrO5TQzKjyeL8",  # Rooming turno 2
]
# Cartella Drive staff Turno 2
STAFF_FOLDER_ID = "1dWfbO9qJtwIrfKSrsaB0fQgI_8QKameL"
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
INIZIO_VIAGGIO = date(2026, 7, 15)  # arrivo a Osaka/Kyoto
FINE_VIAGGIO   = date(2026, 7, 28)  # rientro

def _citta_oggi() -> str:
    oggi = date.today()
    if oggi < date(2026, 7, 26):
        return "Kyoto"
    elif oggi <= date(2026, 7, 28):
        return "Tokyo"
    return "—"

def _giorno_viaggio() -> int:
    delta = (date.today() - INIZIO_VIAGGIO).days + 1
    return max(1, min(delta, 14))

def get_or_create_diary_sheet() -> gspread.Spreadsheet:
    """Restituisce il foglio diario; lo crea se non esiste ancora."""
    global _diary_sheet_id
    gc = get_sheets_client()
    if _diary_sheet_id:
        return gc.open_by_key(_diary_sheet_id)
    sh = gc.create("Diario Viaggio — Giappone Discovery T2")
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

# ─── GRUPPO UNICO (T2: braccialetti tutti VERDI, nessuna divisione colore) ────
PARTECIPANTI_T2 = [
    "ALONZI Chiara", "ALONZI Giulia", "ATTANASIO Matteo", "CARUSO Giulio",
    "CHIOCCA Pasquale Alessandro", "COSENZA Anna", "DE CARO Arianna",
    "DE FAZIO Sara", "DE LUCIA Maddalena", "DOLCE Riccardo", "FERRI Beatrice",
    "FRAU Ludovica", "GUERRIERO Paolo", "LO PORTO Giulia", "MACALUSO Noemi",
    "MALATIA Teresa", "MINELLI Margherita", "NUCCIO Alessandro Maria",
    "PAGANO Mario", "PALA Riccardo", "PALOMBA Giuseppe", "RICCIARDI Rosa",
    "SABATINI Agnese", "SAVIANO Michele", "SCANDINO Amelia",
    "SCANDINO Raffaele", "VILLANO Francesco Pio", "VITALE Dafne",
]
GRUPPI = {"🟢 VERDE (tutti)": PARTECIPANTI_T2}

# ─── PROGRAMMA GIORNALIERO T2 ─────────────────────────────────────────────────
PROGRAMMA = {
    date(2026, 7, 15): {
        "titolo": "✈️ Arrivo a Osaka + Noodles Party",
        "attivita": "Arrivo a Osaka Kansai alle 19:05 (volo TK086). Trasferimento in bus all'Oriental Hotel Kyoto Rokujo. Cena: Noodles Party in hotel.",
        "descrizione": "Dopo il lungo viaggio via Istanbul, atterrate nell'area metropolitana di Osaka-Kyoto. Il tragitto in bus (~1h30) offre i primi scorci del Giappone reale. La Noodles Party è la prima cena giapponese: instant noodles in hotel per iniziare l'immersione nella cultura locale."
    },
    date(2026, 7, 16): {
        "titolo": "📚 Scuola full day",
        "attivita": "Corso di giapponese 6 ore (Campus Plaza, aula R5 F6, 9:00-11:50 e 13:10-16:00).",
        "descrizione": "Prima giornata alla Kyoto Minsai Japanese Language School: grammatica di base, saluti, conversazione. Portare quaderno e penna. Le 6 ore includono attività interattive."
    },
    date(2026, 7, 17): {
        "titolo": "📚 Scuola full day",
        "attivita": "Corso di giapponese 6 ore (Campus Plaza, aula R5 F7, 9:00-11:50 e 13:10-16:00).",
        "descrizione": "Seconda giornata intera di scuola. I ragazzi consolidano la routine: hiragana, frasi utili per negozi e ristoranti."
    },
    date(2026, 7, 18): {
        "titolo": "🏯 Osaka",
        "attivita": "Gita a Osaka (Keihan line): Castello (TKT) → Kuromon Market (pranzo) → Tsutenkaku → Nipponbashi → Dotonbori. Rientro con Hankyu line fino a Omiya.",
        "descrizione": "Osaka è la città più vivace del Giappone, famosa per il cibo. Il Castello è la ricostruzione del 1931 dell'originale del 1583. Kuromon è il 'ventre di Osaka': 170 bancarelle di street food. Dotonbori è il cuore della movida con le insegne luminose giganti (il famoso Glico Man)."
    },
    date(2026, 7, 19): {
        "titolo": "📚 Scuola full day (sede Saiin)",
        "attivita": "Corso 6 ore (Minsai Saiin Campus, 9:00-11:30 e 13:00-16:30).",
        "descrizione": "Giornata di scuola nella sede principale Minsai di Saiin. Lezioni con calligrafia e lavori di gruppo con studenti giapponesi."
    },
    date(2026, 7, 20): {
        "titolo": "🦌 Uji + Nara",
        "attivita": "Uji: Byodoin Temple + pranzo e matcha nella via principale. Poi Nara: parco dei cervi + salita alla collina.",
        "descrizione": "Uji è la capitale del tè matcha; il Byodoin è il tempio stampato sulla moneta da 10 yen. Nara fu la prima capitale del Giappone (710-784): il parco ospita ~1.200 cervi liberi considerati sacri, che si sfamano con crackers appositi."
    },
    date(2026, 7, 21): {
        "titolo": "📚 Scuola + Arashiyama",
        "attivita": "Corso 3 ore (Campus Plaza, aula R5 F6, 9:00-12:00). Pomeriggio: Monkey Forest o Gioji Temple + Arashiyama.",
        "descrizione": "Arashiyama è il quartiere del bambù di Kyoto: il boschetto di bambù gigante è uno dei simboli del Giappone. Lungo il fiume Oi il Tempio Tenryu-ji (UNESCO) e il ponte Togetsukyo. La Monkey Forest è la collina delle scimmie libere con vista sulla città."
    },
    date(2026, 7, 22): {
        "titolo": "🏯 Nijo + Scuola pomeridiana",
        "attivita": "Mattina: Castello Nijo. Corso 3 ore (Campus Plaza, aula R6 F6, 14:40-17:40). Sera: Aeon Mall + Karaoke.",
        "descrizione": "Il Castello Nijo fu residenza degli shogun Tokugawa nel XVII secolo, famoso per i 'corridoi usignolo' che scricchiolano per rivelare gli intrusi (UNESCO). Sera libera tra shopping all'Aeon Mall e karaoke."
    },
    date(2026, 7, 23): {
        "titolo": "📚 Scuola + TeamLab + Fushimi Inari",
        "attivita": "Corso 3 ore (Campus Plaza, aula R6 F6, 9:00-12:00). Pomeriggio: TeamLab Biovortex (ingresso 14:00-14:30) + Fushimi Inari.",
        "descrizione": "TeamLab Biovortex è una delle installazioni di arte digitale immersiva più spettacolari del Giappone. ATTENZIONE: un biglietto QR a testa, niente foto di gruppo, arrivo con mezzi pubblici. Fushimi Inari è il santuario dei migliaia di torii arancioni sulla collina."
    },
    date(2026, 7, 24): {
        "titolo": "⛩️ Kiyomizudera + Gion + Scuola pomeridiana",
        "attivita": "Mattina: Kiyomizudera + Yasaka Pagoda + Yasaka Temple + Gion. Corso 3 ore (Campus Plaza, aula R1 F5, 14:40-17:40).",
        "descrizione": "Kiyomizudera (778 d.C.) è costruito su una scarpata con terrazza di legno a strapiombo. Gion è il quartiere delle geishe con le stradine di pietra e le case da tè del periodo Edo. Ultima lezione: attestato di frequenza."
    },
    date(2026, 7, 25): {
        "titolo": "🍵 Kyoto sacra",
        "attivita": "Alba facoltativa al Nishi Hongan-ji (cerimonia ore 6:00) + Cerimonia del Tè ore 10:30 + Pranzo Mercato Nishiki + Padiglione d'Oro (Kinkaku-ji) + uscita in centro.",
        "descrizione": "Nishi Hongan-ji è il tempio madre del Buddhismo Shin, cerimonia mattutina alle 6:00 aperta al pubblico. La cerimonia del tè (chado) è codificata da 500 anni. Nishiki è 'la cucina di Kyoto'. Il Kinkaku-ji è il monumento più fotografato del Giappone."
    },
    date(2026, 7, 26): {
        "titolo": "🚄 Shinkansen → Tokyo",
        "attivita": "Shinkansen Kyoto→Tokyo ore 08:54. Check-in Oriental Hotel Tokyo Bay. Pomeriggio: Asakusa + Akihabara + Tokyo Metropolitan Government Building + Shinjuku.",
        "descrizione": "Prima esperienza sullo Shinkansen: 300 km/h, puntualità al secondo. Asakusa è il quartiere più antico di Tokyo (Tempio Sensoji, via Nakamise). Akihabara è il paradiso di elettronica e anime/manga. La sera, terrazza gratuita del Metropolitan Government Building: vista a 360° dalla quota 243 m."
    },
    date(2026, 7, 27): {
        "titolo": "🗼 Tokyo",
        "attivita": "Mattina: Tokyo Tower + Shibuya + Tempio Meiji + Harajuku. Pomeriggio/sera: Crociera Odaiba + cena a Odaiba Bay.",
        "descrizione": "Shibuya Crossing è l'incrocio pedonale più trafficato del mondo. Il Tempio Meiji è un'oasi di foresta nella metropoli. Harajuku è la capitale della moda giovanile. La crociera nella baia di Odaiba al tramonto: skyline e Rainbow Bridge."
    },
    date(2026, 7, 28): {
        "titolo": "🏠 Check-out + Rientro a Roma",
        "attivita": "Check-out e trasferimento a Tokyo Narita. Volo TK051 NRT 10:25 → Istanbul 17:40. Volo TK1361 Istanbul 21:50 → Roma FCO T3 23:35.",
        "descrizione": "Partenza di prima mattina per Narita (Terminal 1). Scalo a Istanbul, arrivo a Fiumicino Terminal 3 alle 23:35 dove i ragazzi saranno accolti dalle famiglie. Conservare TUTTE le carte d'imbarco (obbligo INPS)."
    },
}

# ─── BASE DI CONOSCENZA ───────────────────────────────────────────────────────
KNOWLEDGE_BASE = """
Sei l'assistente ufficiale dello staff del viaggio GIAPPONE DISCOVERY - TURNO 2 organizzato da Accademia Britannica / Travel Experts.
Rispondi sempre in italiano, in modo chiaro e conciso. Sei riservato a uso interno staff.
Il rooming è di SOLA LETTURA: se lo staff chiede di spostare qualcuno di stanza, rispondi che le modifiche al foglio vanno fatte a mano su Google Sheets, ma puoi registrare la variazione come nota.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INFORMAZIONI GENERALI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Viaggio: Giappone Discovery - Turno 2
Date: 14 luglio 2026 → 28 luglio 2026
Partecipanti: 28 ragazzi + 3 TL = 31 pax
Booking ref: YFY685 | Flight ref: WDK7PW
TL Staff: Paolo Marmaglio, Salvatore Persico, Francesca Guerrato
Assistenza voli (solo mattina partenze) WhatsApp Francesca: +39 349 871 0515
Braccialetti: TUTTI VERDI — nessuna divisione in gruppi colore.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VOLI - TURKISH AIRLINES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANDATA:
  TK1864 | 14/07 | Roma FCO T3 20:00 → Istanbul 23:35 (ritrovo ore 17:00, banco Turkish T3)
  TK086  | 15/07 | Istanbul 02:25 → Osaka Kansai T1 19:05
RITORNO:
  TK051  | 28/07 | Tokyo Narita T1 10:25 → Istanbul 17:40
  TK1361 | 28/07 | Istanbul 21:50 → Roma FCO T3 23:35
Bagaglio: 1 stiva max 20 kg (somma dimensioni ≤160 cm) + 1 zaino max 8 kg.
Carte d'imbarco: conservarle TUTTE fino al rientro (obbligo portale INPS).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOTEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KYOTO (15→26/07): Oriental Hotel Kyoto Rokujo — 181 Bokumikanabutsucho, Shimogyo Ward
  Tel +81 75-343-8111 | inquiry@kyotorokujo.oriental-hotels.com
  Camere: triple (+2 doppie ragazze). Colazione 6:45→9:30 (consigliata dopo le 7:45).
TOKYO (26→28/07): Oriental Hotel Tokyo Bay — 1-8-2 Mihama, Urayasu, Chiba
  Tel +81 47-350-8111 | info@oriental-hotel.co.jp
  Camere: quadruple.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROOMING KYOTO (triple/doppie) - Oriental Hotel Kyoto Rokujo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stanza 1 [F]: ALONZI Chiara | ALONZI Giulia | RICCIARDI Rosa
Stanza 2 [F]: COSENZA Anna | DE CARO Arianna | DE LUCIA Maddalena
Stanza 3 [F]: FERRI Beatrice | FRAU Ludovica | LO PORTO Giulia
Stanza 4 [F]: MACALUSO Noemi | MALATIA Teresa | MINELLI Margherita
Stanza 5 [F, doppia]: SABATINI Agnese | SCANDINO Amelia
Stanza 6 [F, doppia]: DE FAZIO Sara | VITALE Dafne
Stanza 7 [M]: ATTANASIO Matteo | CARUSO Giulio | CHIOCCA Pasquale Alessandro
Stanza 8 [M]: DOLCE Riccardo | GUERRIERO Paolo | SAVIANO Michele
Stanza 9 [M]: NUCCIO Alessandro Maria | PAGANO Mario | PALA Riccardo
Stanza 10 [M]: VILLANO Francesco Pio | PALOMBA Giuseppe | SCANDINO Raffaele
TL: MARMAGLIO Paolo, PERSICO Salvatore, GUERRATO Francesca (singole)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROOMING TOKYO (quadruple) - Oriental Hotel Tokyo Bay
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stanza 1 [F]: ALONZI Chiara | ALONZI Giulia | RICCIARDI Rosa | FRAU Ludovica
Stanza 2 [F]: COSENZA Anna | DE CARO Arianna | DE LUCIA Maddalena | FERRI Beatrice
Stanza 3 [F]: LO PORTO Giulia | MACALUSO Noemi | MALATIA Teresa | MINELLI Margherita
Stanza 4 [F]: SABATINI Agnese | SCANDINO Amelia | DE FAZIO Sara | VITALE Dafne
Stanza 5 [M]: CARUSO Giulio | DOLCE Riccardo | GUERRIERO Paolo | SAVIANO Michele
Stanza 6 [M]: ATTANASIO Matteo | CHIOCCA Pasquale Alessandro | NUCCIO Alessandro Maria | PAGANO Mario
Stanza 7 [M]: PALA Riccardo | VILLANO Francesco Pio | PALOMBA Giuseppe | SCANDINO Raffaele
TL: MARMAGLIO Paolo, PERSICO Salvatore, GUERRATO Francesca

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INFO MEDICHE / ATTENZIONI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RICCIARDI Rosa      → Art. 3 comma 3, no accompagnatori. Lieve ritardo cognitivo (sfera relazionale/emotiva): va spronata e coinvolta, i primi giorni può essere schiva. Nessuna allergia né terapia. Già viaggiato (Dubai).
DE LUCIA Maddalena  → Allergia agli acari della polvere
FERRI Beatrice      → Allergia da contatto al nichel; fluifort sciroppo
MALATIA Teresa      → ALLERGIA AL FARMACO amoxicillina + acido clavulanico (es. Augmentin) — NON somministrare
Nessuna segnalazione: Alonzi C., Alonzi G., Attanasio, Caruso, Chiocca, Cosenza, De Caro, De Fazio, Dolce, Frau, Guerriero, Lo Porto, Macaluso, Minelli, Nuccio, Pagano, Pala, Palomba, Sabatini, Saviano, Scandino A., Scandino R., Villano, Vitale

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RUBRICA PARTECIPANTI (data nascita | cell partecipante | cell genitore/intestatario | email)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALONZI Chiara            | 05/04/2011 | 3289624891 | 3289624891 | monicalenoci1@gmail.com
ALONZI Giulia            | 15/09/2008 | 3289624891 | 3289624891 | monicalenoci1@gmail.com
ATTANASIO Matteo         | 02/07/2008 | 3515017377 | 3486751883 | attanasio.maurizio@gmail.com
CARUSO Giulio            | 22/04/2009 | —          | 3493247337 | simonanilletti333@outlook.it
CHIOCCA Pasquale Aless.  | 13/08/2007 | 3403506498 | 3403506498 | saverio974@hotmail.it
COSENZA Anna             | 02/12/2007 | 3313281942 | 3284368048 | carmencorrado@aseec.it
DE CARO Arianna          | 07/12/2007 | —          | 3468830076 | martes@inwind.it
DE FAZIO Sara            | 11/03/2009 | 3421477099 | 3397755072 | minaerrico75@icloud.com
DE LUCIA Maddalena       | 17/06/2008 | 3312555114 | 3496432745 | filomenasalzillo75@gmail.com
DOLCE Riccardo           | 09/01/2009 | 3920645193 | 3927416111 | Mariarosariabuanne@gmail.com
FERRI Beatrice           | 21/06/2008 | 3426810153 | 3403543742 | faddamarianna94@gmail.com
FRAU Ludovica            | 27/02/2009 | 3311546022 | 3392000874 | f.roberto2022@virgilio.it
GUERRIERO Paolo          | 26/11/2008 | 3491206874 | 3404716473 | fiorenzo.guerriero@yahoo.com
LO PORTO Giulia          | 22/02/2009 | 3924782637 | 3924782637 | s.loporto@alice.it
MACALUSO Noemi           | 11/05/2008 | 3921334014 | 3883231506 | hopss1@gmail.com
MALATIA Teresa           | 27/02/2009 | 3519326099 | 3476514025 | fabiomalatia@hotmail.com
MINELLI Margherita       | 04/07/2008 | —          | 3286758657 | benedetta.arezzi@gmail.com
NUCCIO Alessandro Maria  | 03/07/2008 | 3480405090 | 3284557943 | mariateresa.camizzi@scuola.istruzione.it
PAGANO Mario             | 19/05/2008 | 3923975513 | 3289073120 | griffiloredana@gmail.com
PALA Riccardo            | 03/04/2008 | 3421987478 | 3313655312 | palagianluca@tiscali.it
PALOMBA Giuseppe         | 05/06/2007 | 3518900396 | 3381126425 | palomba.antonio@gdf.it
RICCIARDI Rosa           | 25/11/2009 | 3516605363 | 3317670949 | maddalena-ricciardi@virgilio.it
SABATINI Agnese          | 05/05/2008 | 3714821371 | 3472221282 | nicola.sabatini@micso.net
SAVIANO Michele          | 04/10/2011 | 3283667674 | 3283667684 | marinella.liccardo@gmail.com
SCANDINO Amelia          | 23/10/2008 | 3515344666 | 3337772585 | arianna.martinis@gmail.com
SCANDINO Raffaele        | 21/04/2007 | 3519468855 | 3337772585 | arianna.martinis@gmail.com
VILLANO Francesco Pio    | 21/12/2007 | 3713852021 | 3456162860 | villano.rossella@libero.it
VITALE Dafne             | 23/06/2009 | 3201839918 | 3804771028 | danilo.vitale79@gmail.com

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MATERIALE CONSEGNATO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ogni partecipante riceve: carta prepagata 3I4IM Mastercard Business (€220) + carta ICOCA trasporti + braccialetto VERDE.
Numeri carta (in ordine di stanza Kyoto): 00849 ALONZI Chiara → 00876 SCANDINO Raffaele.
00849 ALONZI Chiara | 00850 ALONZI Giulia | 00851 RICCIARDI Rosa | 00852 COSENZA Anna
00853 DE CARO Arianna | 00854 DE LUCIA Maddalena | 00855 FERRI Beatrice | 00856 FRAU Ludovica
00857 LO PORTO Giulia | 00858 MACALUSO Noemi | 00859 MALATIA Teresa | 00860 MINELLI Margherita
00861 SABATINI Agnese | 00862 SCANDINO Amelia | 00863 DE FAZIO Sara | 00864 VITALE Dafne
00865 ATTANASIO Matteo | 00866 CARUSO Giulio | 00867 CHIOCCA Pasquale A. | 00868 DOLCE Riccardo
00869 GUERRIERO Paolo | 00870 SAVIANO Michele | 00871 NUCCIO Alessandro M. | 00872 PAGANO Mario
00873 PALA Riccardo | 00874 VILLANO Francesco Pio | 00875 PALOMBA Giuseppe | 00876 SCANDINO Raffaele
Saldo carta: getmybalance.com

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCUOLA DI GIAPPONESE - Kyoto Minsai (Group 2, max 28, 1 classe)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
16/07 gio │ 6 ore │ 9:00-11:50 / 13:10-16:00 │ Campus Plaza, R5 F6
17/07 ven │ 6 ore │ 9:00-11:50 / 13:10-16:00 │ Campus Plaza, R5 F7
18/07 sab │ NIENTE SCUOLA (Osaka)
19/07 dom │ 6 ore │ 9:00-11:30 / 13:00-16:30 │ Minsai Saiin Campus
20/07 lun │ NIENTE SCUOLA (Uji + Nara)
21/07 mar │ 3 ore │ 9:00-12:00  │ Campus Plaza, R5 F6
22/07 mer │ 3 ore │ 14:40-17:40 │ Campus Plaza, R6 F6
23/07 gio │ 3 ore │ 9:00-12:00  │ Campus Plaza, R6 F6
24/07 ven │ 3 ore │ 14:40-17:40 │ Campus Plaza, R1 F5
Indirizzo Minsai: 69 Nishikyogoku Kitaooiri-cho, Ukyo-ku, Kyoto | Tel: 075-316-0190

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EVENTI PRENOTATI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- TeamLab Biovortex Kyoto: 23/07 ingresso 14:00-14:30, biglietti QR individuali (PDF su Drive). No foto di gruppo, no bus privati.
- Cerimonia del Tè (AN KYOTO): 25/07 ore 10:30, 30 pax, programma SHARED. Tel +81-80-9307-1873.
- Shinkansen Kyoto→Tokyo: 26/07 ore 08:54. QR ticket nella cartella Drive 'Qr-code Ticket Shinkansen'.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOTE OPERATIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Tutti i 28 partecipanti partono e rientrano su ROMA (nessun avvicinamento gestito da noi).
- Fuso: +7h rispetto all'Italia. Cambio: ~168 yen per euro.
- SIM: eSIM Holafly/Airalo consigliata, oppure SIM in aeroporto. Wi-fi in hotel.
- ICOCA precaricata per i trasporti col gruppo. NON trasferirla nel wallet iPhone.
- Modifiche a programma o rooming: lo staff le comunica via chat, il bot le registra e le riporta.
"""

# ─── BRIEFING ARRIVO ──────────────────────────────────────────────────────────
BRIEFING_P1 = """🎌 *BRIEFING ARRIVO KYOTO — Giappone Discovery T2*

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

Nella bustina c'è anche il *braccialetto verde* — quest'anno siamo un gruppo unico, tenetelo al polso: serve a riconoscervi nei luoghi affollati. Non toglietevelo."""

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
*Partenza dall'hotel alle 8:30 puntuali.* Lezione 9:00-11:50 e 13:10-16:00 (Campus Plaza, aula R5 F6).
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
    ("ALONZI Chiara",               date(2011,  4,  5)),
    ("ALONZI Giulia",               date(2008,  9, 15)),
    ("ATTANASIO Matteo",            date(2008,  7,  2)),
    ("CARUSO Giulio",               date(2009,  4, 22)),
    ("CHIOCCA Pasquale Alessandro", date(2007,  8, 13)),
    ("COSENZA Anna",                date(2007, 12,  2)),
    ("DE CARO Arianna",             date(2007, 12,  7)),
    ("DE FAZIO Sara",               date(2009,  3, 11)),
    ("DE LUCIA Maddalena",          date(2008,  6, 17)),
    ("DOLCE Riccardo",              date(2009,  1,  9)),
    ("FERRI Beatrice",              date(2008,  6, 21)),
    ("FRAU Ludovica",               date(2009,  2, 27)),
    ("GUERRIERO Paolo",             date(2008, 11, 26)),
    ("LO PORTO Giulia",             date(2009,  2, 22)),
    ("MACALUSO Noemi",              date(2008,  5, 11)),
    ("MALATIA Teresa",              date(2009,  2, 27)),
    ("MINELLI Margherita",          date(2008,  7,  4)),
    ("NUCCIO Alessandro Maria",     date(2008,  7,  3)),
    ("PAGANO Mario",                date(2008,  5, 19)),
    ("PALA Riccardo",               date(2008,  4,  3)),
    ("PALOMBA Giuseppe",            date(2007,  6,  5)),
    ("RICCIARDI Rosa",              date(2009, 11, 25)),
    ("SABATINI Agnese",             date(2008,  5,  5)),
    ("SAVIANO Michele",             date(2011, 10,  4)),
    ("SCANDINO Amelia",             date(2008, 10, 23)),
    ("SCANDINO Raffaele",           date(2007,  4, 21)),
    ("VILLANO Francesco Pio",       date(2007, 12, 21)),
    ("VITALE Dafne",                date(2009,  6, 23)),
]

INIZIO_TURNO = date(2026, 7, 14)
FINE_TURNO   = date(2026, 7, 28)

def _compleanni_testo() -> str:
    trovati = [
        (d.replace(year=2026), nome)
        for nome, d in PARTECIPANTI_DATE
        if INIZIO_TURNO <= d.replace(year=2026) <= FINE_TURNO
    ]
    trovati.sort()
    if trovati:
        righe = "\n".join(f"🎂 *{nome}* — {d.strftime('%d/%m')}" for d, nome in trovati)
        return f"*Compleanni durante il turno (14–28 luglio):*\n\n{righe}"
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
        "👋 Ciao! Sono l'assistente staff *Giappone Discovery - Turno 2*.\n\n"
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
        "• \"In che stanza è FERRI Beatrice a Kyoto?\"\n"
        "• \"Chi ha allergie?\"\n"
        "• \"Cosa facciamo il 23 luglio?\"\n"
        "• \"Numero carta di Rosa Ricciardi?\"\n"
        "• \"A che ora parte lo Shinkansen?\"\n"
        "• \"A che ora è il volo di rientro?\"\n\n"
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
        "nomi": PARTECIPANTI_T2.copy(),
        "indice": 0,
        "presenti": [],
        "assenti": [],
        "saltati": [],
        "giro": 1,
    }
    await update.message.reply_text(
        f"📢 *Appello — gruppo unico ({len(PARTECIPANTI_T2)} persone)*",
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

        # T2: rooming di sola lettura — le richieste di spostamento vengono
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

    logger.info("🤖 Bot T2 avviato.")
    app.run_polling()

if __name__ == "__main__":
    main()
