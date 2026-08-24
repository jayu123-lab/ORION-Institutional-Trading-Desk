"""ORION Auto Translation (P20-P23).

Default UI language: SPANISH. Initial languages: ES EN FR DE IT PT.
Architecture is extensible: add entries to UI_CATALOGS / GLOSSARY.

Rules:
- Critical financial terms stay recognizable (P21): "Liquidity Sweep ->
  Barrido de liquidez (Liquidity Sweep)", "Managed Money" stays
  "Managed Money", symbols/prices/URLs/tickers/IDs are NEVER touched.
- Chat translation is deterministic glossary replacement (no LLM):
  when nothing applies, the ORIGINAL text is returned untouched (P23).
- A translator failure NEVER blocks the CIO: every public function
  swallows unexpected errors and falls back to the original text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LANGUAGES: tuple[str, ...] = ("es", "en", "fr", "de", "it", "pt")
DEFAULT_LANGUAGE = "es"

LANGUAGE_NAMES = {
    "es": "ESPAÑOL", "en": "ENGLISH", "fr": "FRANÇAIS",
    "de": "DEUTSCH", "it": "ITALIANO", "pt": "PORTUGUÊS",
}


# --------------------------------------------------------------------- UI
# Keys used by the Command Center UI. `es` is canonical; others mirror it.
UI_CATALOGS: dict[str, dict[str, str]] = {
    "command_center": {"es": "CENTRO DE MANDO", "en": "COMMAND CENTER",
                       "fr": "CENTRE DE COMMANDE", "de": "KOMMANDOZENTRALE",
                       "it": "CENTRO DI COMANDO", "pt": "CENTRO DE COMANDO"},
    "institutional_desk": {"es": "MESA INSTITUCIONAL", "en": "INSTITUTIONAL DESK",
                           "fr": "BUREAU INSTITUTIONNEL", "de": "INSTITUTIONELLER DESK",
                           "it": "SCRIVANIA ISTITUZIONALE",
                           "pt": "MESA INSTITUCIONAL"},
    "analyze_gold": {"es": "ANALIZAR ORO", "en": "ANALYZE GOLD",
                     "fr": "ANALYSER L'OR", "de": "GOLD ANALYSIEREN",
                     "it": "ANALIZZA ORO", "pt": "ANALISAR OURO"},
    "analyze_xrp": {"es": "ANALIZAR XRP", "en": "ANALYZE XRP",
                    "fr": "ANALYSER XRP", "de": "XRP ANALYSIEREN",
                    "it": "ANALIZZA XRP", "pt": "ANALISAR XRP"},
    "analyze_nasdaq": {"es": "ANALIZAR NASDAQ", "en": "ANALYZE NASDAQ",
                       "fr": "ANALYSER NASDAQ", "de": "NASDAQ ANALYSIEREN",
                       "it": "ANALIZZA NASDAQ", "pt": "ANALISAR NASDAQ"},
    "pre_london": {"es": "PRE-LONDRES", "en": "PRE-LONDON",
                   "fr": "PRÉ-LONDRES", "de": "VOR-LONDON",
                   "it": "PRE-LONDRA", "pt": "PRÉ-LONDRES"},
    "pre_ny": {"es": "PRE-NUEVA YORK", "en": "PRE-NY",
               "fr": "PRÉ-NY", "de": "VOR-NY", "it": "PRE-NY", "pt": "PRÉ-NY"},
    "convene_desk": {"es": "CONVOCAR MESA", "en": "CONVENE DESK",
                     "fr": "CONVOQUER LE BUREAU", "de": "DESK EINBERUFEN",
                     "it": "CONVOCARE LA SCRIVANIA", "pt": "CONVOCAR A MESA"},
    "risk_check": {"es": "CHEQUEO DE RIESGO", "en": "RISK CHECK",
                   "fr": "VÉRIFICATION RISQUE", "de": "RISIKOPRÜFUNG",
                   "it": "CONTROLLO RISCHIO", "pt": "CHECAGEM DE RISCO"},
    "system_status": {"es": "ESTADO DEL SISTEMA", "en": "SYSTEM STATUS",
                      "fr": "ÉTAT DU SYSTÈME", "de": "SYSTEMSTATUS",
                      "it": "STATO DEL SISTEMA", "pt": "ESTADO DO SISTEMA"},
    "agent_activity": {"es": "ACTIVIDAD DE AGENTES", "en": "AGENT ACTIVITY",
                       "fr": "ACTIVITÉ DES AGENTS", "de": "AGENTENAKTIVITÄT",
                       "it": "ATTIVITÀ AGENTI", "pt": "ATIVIDADE DOS AGENTES"},
    "intelligence": {"es": "INTELIGENCIA", "en": "INTELLIGENCE",
                     "fr": "RENSEIGNEMENTS", "de": "NACHRICHTENLAGE",
                     "it": "INTELLIGENCE", "pt": "INTELIGÊNCIA"},
    "auto_translate": {"es": "AUTO TRADUCIR", "en": "AUTO TRANSLATE",
                       "fr": "TRADUCTION AUTO", "de": "AUTO-ÜBERSETZEN",
                       "it": "TRADUZIONE AUTO", "pt": "TRADUÇÃO AUTOMÁTICA"},
    "view_original": {"es": "VER ORIGINAL", "en": "VIEW ORIGINAL",
                      "fr": "VOIR L'ORIGINAL", "de": "ORIGINAL ANZEIGEN",
                      "it": "VEDI ORIGINALE", "pt": "VER ORIGINAL"},
    "terminal": {"es": "TERMINAL", "en": "TERMINAL", "fr": "TERMINAL",
                 "de": "TERMINAL", "it": "TERMINALE", "pt": "TERMINAL"},
    "send": {"es": "ENVIAR", "en": "SEND", "fr": "ENVOYER",
             "de": "SENDEN", "it": "INVIA", "pt": "ENVIAR"},
    "api_offline": {"es": "API FUERA DE SERVICIO", "en": "API OFFLINE",
                    "fr": "API HORS LIGNE", "de": "API OFFLINE",
                    "it": "API OFFLINE", "pt": "API OFFLINE"},
    "feed_degraded": {"es": "FEED DEGRADADO", "en": "FEED DEGRADED",
                      "fr": "FLUX DÉGRADÉ", "de": "FEED BEEINTRÄCHTIGT",
                      "it": "FEED DEGRADATO", "pt": "FEED DEGRADADO"},
    "translator_unavailable": {
        "es": "TRADUCTOR NO DISPONIBLE", "en": "TRANSLATOR UNAVAILABLE",
        "fr": "TRADUCTEUR INDISPONIBLE", "de": "ÜBERSETZER NICHT VERFÜGBAR",
        "it": "TRADUTTORE NON DISPONIBILE", "pt": "TRADUTOR INDISPONÍVEL"},
}


def ui_string(key: str, lang: str = DEFAULT_LANGUAGE) -> str:
    """UI label in the requested language with graceful fallback chain
    lang -> es -> key itself."""
    entry = UI_CATALOGS.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get(DEFAULT_LANGUAGE) or key


def catalogs_payload() -> dict:
    """Everything the frontend needs to switch language at runtime."""
    return {
        "default_language": DEFAULT_LANGUAGE,
        "languages": [
            {"code": code, "name": LANGUAGE_NAMES[code]} for code in LANGUAGES
        ],
        "catalogs": {key: dict(val) for key, val in UI_CATALOGS.items()},
    }


# ------------------------------------------------------------------ chat
# Canonical English -> target language glossary. Multi-word first.
GLOSSARY: dict[str, dict[str, str]] = {
    "liquidity sweep": {
        "es": "barrido de liquidez (liquidity sweep)", "en": "liquidity sweep",
        "fr": "balayage de liquidité (liquidity sweep)",
        "de": "Liquiditätssweep (Liquidity Sweep)",
        "it": "spazzata di liquidità (liquidity sweep)",
        "pt": "varredura de liquidez (liquidity sweep)"},
    "buy-side liquidity": {
        "es": "liquidez del lado comprador", "en": "buy-side liquidity",
        "fr": "liquidité côté acheteur", "de": "Kaufseiten-Liquidität",
        "it": "liquidità lato acquirente", "pt": "liquidez do lado comprador"},
    "sell-side liquidity": {
        "es": "liquidez del lado vendedor", "en": "sell-side liquidity",
        "fr": "liquidité côté vendeur", "de": "Verkaufsseiten-Liquidität",
        "it": "liquidità lato venditore", "pt": "liquidez do lado vendedor"},
    "risk-off": {
        "es": "Risk-Off (aversión al riesgo)", "en": "risk-off",
        "fr": "Risk-Off (aversion au risque)", "de": "Risk-Off (Risikoaversion)",
        "it": "Risk-Off (avversione al rischio)", "pt": "Risk-Off (aversão ao risco)"},
    "open interest": {
        "es": "open interest (interés abierto)", "en": "open interest",
        "fr": "open interest (intérêt ouvert)", "de": "Open Interest",
        "it": "open interest (interesse aperto)", "pt": "open interest (interesse aberto)"},
    "managed money": {lang: "Managed Money" for lang in LANGUAGES},
    "no trade": {
        "es": "NO OPERAR (NO TRADE)", "en": "NO TRADE", "fr": "NE PAS TRADER",
        "de": "NICHT HANDELN", "it": "NON TRADARE", "pt": "NÃO OPERAR"},
    "wait": {"es": "ESPERAR", "en": "WAIT", "fr": "ATTENDRE",
             "de": "WARTEN", "it": "ASPETTARE", "pt": "AGUARDAR"},
    "bias score": {
        "es": "puntaje de sesgo (bias score)", "en": "bias score",
        "fr": "score de biais", "de": "Bias-Score",
        "it": "punteggio di bias", "pt": "pontuação de viés"},
    "trade quality": {
        "es": "calidad de operación (trade quality)", "en": "trade quality",
        "fr": "qualité du trade", "de": "Trade-Qualität",
        "it": "qualità del trade", "pt": "qualidade da operação"},
    "session high": {"es": "máximo de sesión", "en": "session high",
                     "fr": "plus haut de session", "de": "Sitzungshoch",
                     "it": "massimo di sessione", "pt": "máxima da sessão"},
    "session low": {"es": "mínimo de sesión", "en": "session low",
                    "fr": "plus bas de session", "de": "Sitzungstief",
                    "it": "minimo di sessione", "pt": "mínima da sessão"},
    "desk read": {"es": "lectura de mesa", "en": "desk read",
                  "fr": "lecture du bureau", "de": "Desk-Lesart",
                  "it": "lettura della scrivania", "pt": "leitura da mesa"},
    "bias:": {"es": "sesgo:", "en": "bias:", "fr": "biais:",
              "de": "Bias:", "it": "bias:", "pt": "viés:"},
    "decision:": {"es": "decisión:", "en": "decision:", "fr": "décision:",
                  "de": "Entscheidung:", "it": "decisione:", "pt": "decisão:"},
    "confidence:": {"es": "confianza:", "en": "confidence:", "fr": "confiance:",
                    "de": "Konfidenz:", "it": "fiducia:", "pt": "confiança:"},
    "market state:": {"es": "estado del mercado:", "en": "market state:",
                       "fr": "état du marché:", "de": "Marktzustand:",
                       "it": "stato del mercato:", "pt": "estado do mercado:"},
    "facts:": {"es": "hechos:", "en": "facts:", "fr": "faits:",
               "de": "Fakten:", "it": "fatti:", "pt": "fatos:"},
    "inferences (per specialist):": {
        "es": "inferencias (por especialista):", "en": "inferences (per specialist):",
        "fr": "inférences (par spécialiste):", "de": "Schlussfolgerungen (pro Spezialist):",
        "it": "inferenze (per specialista):", "pt": "inferências (por especialista):"},
    "risk:": {"es": "riesgo:", "en": "risk:", "fr": "risque:",
              "de": "Risiko:", "it": "rischio:", "pt": "risco:"},
    "plan:": {"es": "plan:", "en": "plan:", "fr": "plan:",
              "de": "Plan:", "it": "piano:", "pt": "plano:"},
    "data gaps:": {"es": "vacíos de datos:", "en": "data gaps:",
                   "fr": "lacunes de données:", "de": "Datenlücken:",
                   "it": "lacune di dati:", "pt": "lacunas de dados:"},
    "sessions active:": {"es": "sesiones activas:", "en": "sessions active:",
                          "fr": "sessions actives:", "de": "Aktive Sitzungen:",
                          "it": "sessioni attive:", "pt": "sessões ativas:"},
    "missing inputs": {"es": "datos faltantes", "en": "missing inputs",
                        "fr": "données manquantes", "de": "Fehlende Eingaben",
                        "it": "dati mancanti", "pt": "dados faltantes"},
    "regime=": {"es": "régimen=", "en": "regime=", "fr": "régime=",
                "de": "Regime=", "it": "regime=", "pt": "regime="},
    "volatility=": {"es": "volatilidad=", "en": "volatility=", "fr": "volatilité=",
                    "de": "Volatilität=", "it": "volatilità=", "pt": "volatilidade="},
    "risk_mode=": {lang: "risk_mode=" for lang in LANGUAGES},
    "data_quality=": {lang: "data_quality=" for lang in LANGUAGES},
    "no trade — veto active": {
        "es": "no operar — veto activo", "en": "no trade — veto active",
        "fr": "pas de trade — veto actif", "de": "kein Handel — Veto aktiv",
        "it": "non tradare — veto attivo", "pt": "não operar — veto ativo"},
    "re-evaluate after conditions clear": {
        "es": "reevaluar cuando las condiciones se despejen",
        "en": "re-evaluate after conditions clear",
        "fr": "réévaluer une fois les conditions clarifiées",
        "de": "neu bewerten, sobald sich die Bedingungen klären",
        "it": "rivalutare dopo che le condizioni si chiariscono",
        "pt": "reavaliar após as condições se esclarecerem"},
    "doctrine gate": {"es": "puerta de doctrina", "en": "doctrine gate",
                       "fr": "portail de doctrine", "de": "Doktrin-Gate",
                       "it": "cancello dottrinale", "pt": "portão de doutrina"},
    "a bias is not an entry": {
        "es": "un sesgo no es una entrada", "en": "a bias is not an entry",
        "fr": "un biais n'est pas une entrée", "de": "ein Bias ist kein Einstieg",
        "it": "un bias non è un ingresso", "pt": "um viés não é uma entrada"},
    "no edge worth institutional risk right now": {
        "es": "ninguna ventaja justifica riesgo institucional ahora mismo",
        "en": "no edge worth institutional risk right now",
        "fr": "aucun avantage ne justifie un risque institutionnel actuellement",
        "de": "derzeit kein Vorteil, der institutionelles Risiko rechtfertigt",
        "it": "nessun vantaggio giustifica rischio istituzionale ora",
        "pt": "nenhuma vantagem justifica risco institucional agora"},
    "preliminary": {"es": "preliminar", "en": "preliminary", "fr": "préliminaire",
                    "de": "vorläufig", "it": "preliminare", "pt": "preliminar"},
    "setup (internal label, not advice)": {
        "es": "setup (etiqueta interna, no es consejo)",
        "en": "setup (internal label, not advice)",
        "fr": "setup (étiquette interne, pas un conseil)",
        "de": "Setup (interne Bezeichnung, keine Beratung)",
        "it": "setup (etichetta interna, non è un consiglio)",
        "pt": "setup (rótulo interno, não é conselho)"},
    "reference entry zone": {
        "es": "zona de entrada de referencia", "en": "reference entry zone",
        "fr": "zone d'entrée de référence", "de": "Referenz-Einstiegszone",
        "it": "zona di ingresso di riferimento", "pt": "zona de entrada de referência"},
    "structural invalidation": {
        "es": "invalidación estructural", "en": "structural invalidation",
        "fr": "invalidation structurelle", "de": "strukturelle Invalidierung",
        "it": "invalidazione strutturale", "pt": "invalidação estrutural"},
    "activation: only after human approval + fresh quote re-check": {
        "es": "activación: solo tras aprobación humana + reverificación de cotización",
        "en": "activation: only after human approval + fresh quote re-check",
        "fr": "activation : uniquement après approbation humaine + revérification de la cotation",
        "de": "Aktivierung: nur nach menschlicher Freigabe + erneuter Kursprüfung",
        "it": "attivazione: solo dopo approvazione umana + riverifica della quotazione",
        "pt": "ativação: somente após aprovação humana + reverificação da cotação"},
    "none — all checked fields verified": {
        "es": "ninguno — todos los campos verificados", "en": "none — all checked fields verified",
        "fr": "aucun — tous les champs vérifiés", "de": "keine — alle geprüften Felder verifiziert",
        "it": "nessuno — tutti i campi verificati", "pt": "nenhum — todos os campos verificados"},
    "none (thin liquidity caution)": {
        "es": "ninguno (precaución por liquidez baja)",
        "en": "none (thin liquidity caution)",
        "fr": "aucun (prudence liquidité faible)",
        "de": "keine (Vorsicht wegen geringer Liquidität)",
        "it": "nessuno (cautela per liquidità sottile)",
        "pt": "nenhum (cautela por liquidez baixa)"},
    "gate": {"es": "puerta", "en": "gate", "fr": "portail",
             "de": "Gate", "it": "cancello", "pt": "portão"},
    "veto active": {"es": "veto activo", "en": "veto active", "fr": "veto actif",
                    "de": "Veto aktiv", "it": "veto attivo", "pt": "veto ativo"},
    "buy": {"es": "compra", "en": "buy", "fr": "achat",
            "de": "Kauf", "it": "acquisto", "pt": "compra"},
    "sell": {"es": "venta", "en": "sell", "fr": "vente",
             "de": "Verkauf", "it": "vendita", "pt": "venda"},
    "long": {"es": "largo", "en": "long", "fr": "long",
             "de": "Long", "it": "long", "pt": "comprado"},
    "short": {"es": "corto", "en": "short", "fr": "court",
              "de": "Short", "it": "short", "pt": "vendido"},
    "neutral": {"es": "neutral", "en": "neutral", "fr": "neutre",
                "de": "neutral", "it": "neutrale", "pt": "neutro"},
    "bullish": {"es": "alcista", "en": "bullish", "fr": "haussier",
                "de": "bullisch", "it": "rialzista", "pt": "altista"},
    "bearish": {"es": "bajista", "en": "bearish", "fr": "baissier",
                "de": "bärisch", "it": "ribassista", "pt": "baixista"},
    "trending": {"es": "tendencial", "en": "trending", "fr": "tendanciel",
                 "de": "trendig", "it": "in tendenza", "pt": "em tendência"},
    "ranging": {"es": "en rango", "en": "ranging", "fr": "en range",
                "de": "in Spanne", "it": "in range", "pt": "em faixa"},
    "normal": {"es": "normal", "en": "normal", "fr": "normal",
               "de": "normal", "it": "normale", "pt": "normal"},
    "moderate": {"es": "moderado", "en": "moderate", "fr": "modéré",
                 "de": "moderat", "it": "moderato", "pt": "moderado"},
    "strong": {"es": "fuerte", "en": "strong", "fr": "fort",
               "de": "stark", "it": "forte", "pt": "forte"},
    "weak": {"es": "débil", "en": "weak", "fr": "faible",
             "de": "schwach", "it": "debole", "pt": "fraco"},
    "approved": {"es": "aprobado", "en": "approved", "fr": "approuvé",
                 "de": "genehmigt", "it": "approvato", "pt": "aprovado"},
    "rejected": {"es": "rechazado", "en": "rejected", "fr": "rejeté",
                 "de": "abgelehnt", "it": "rifiutato", "pt": "rejeitado"},
    "pending": {"es": "pendiente", "en": "pending", "fr": "en attente",
                "de": "ausstehend", "it": "in sospeso", "pt": "pendente"},
    "confirmed": {"es": "confirmado", "en": "confirmed", "fr": "confirmé",
                  "de": "bestätigt", "it": "confermato", "pt": "confirmado"},
    "armed": {"es": "armado", "en": "armed", "fr": "armé",
              "de": "scharfgeschaltet", "it": "armato", "pt": "armado"},
    "invalidated": {"es": "invalidado", "en": "invalidated", "fr": "invalidé",
                    "de": "invalidiert", "it": "invalidato", "pt": "invalidado"},
    "live": {"es": "en vivo", "en": "live", "fr": "en direct",
             "de": "live", "it": "in diretta", "pt": "ao vivo"},
    "stale": {"es": "desactualizado", "en": "stale", "fr": "obsolète",
              "de": "veraltet", "it": "obsoleto", "pt": "desatualizado"},
    "healthy": {"es": "saludable", "en": "healthy", "fr": "sain",
                "de": "gesund", "it": "sano", "pt": "saudável"},
    "operational": {"es": "operativo", "en": "operational", "fr": "opérationnel",
                     "de": "betriebsbereit", "it": "operativo", "pt": "operacional"},
    "degraded": {"es": "degradado", "en": "degraded", "fr": "dégradé",
                 "de": "beeinträchtigt", "it": "degradato", "pt": "degradado"},
    "below": {"es": "por debajo", "en": "below", "fr": "en dessous",
              "de": "unterhalb", "it": "sotto", "pt": "abaixo"},
    "above": {"es": "por encima", "en": "above", "fr": "au-dessus",
              "de": "oberhalb", "it": "sopra", "pt": "acima"},
    "near": {"es": "cerca de", "en": "near", "fr": "près de",
             "de": "nahe", "it": "vicino a", "pt": "perto de"},
}

# Bare uppercase tokens that must be preserved as tickers/symbols and never
# passed through the glossary, even though they match the token regex below.
_KNOWN_TICKERS = frozenset({
    "XAUUSD", "XAGUSD", "SI", "HG", "GC",
    "CL", "BZ", "NG", "ZW", "ZC", "KC",
    "ES", "NQ", "SPX", "VIX", "DXY",
    "BTCUSD", "ETHUSD", "XRPUSD", "SOLUSD", "XLM", "HBAR",
    "BTC", "ETH", "XRP", "SOL",
    "EURUSD", "GBPUSD", "USDJPY",
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "JPM", "KO",
})

# Spanish source phrases that map back to the canonical English terms above.
_ES_SOURCE_ALIASES: list[tuple[str, str]] = [
    ("barrido de liquidez", "liquidity sweep"),
    ("liquidez del lado comprador", "buy-side liquidity"),
    ("liquidez del lado vendedor", "sell-side liquidity"),
    ("aversión al riesgo", "risk-off"),
    ("interés abierto", "open interest"),
    ("puntaje de sesgo", "bias score"),
    ("calidad de operacion", "trade quality"),
    ("calidad de operación", "trade quality"),
    ("máximo de sesión", "session high"),
    ("maximo de sesion", "session high"),
    ("mínimo de sesión", "session low"),
    ("minimo de sesion", "session low"),
]

_TOKEN_RE = re.compile(
    r"(\$?\b[A-Z]{2,10}(?:USD)?\b(?:[=F])?"   # candidate tickers/symbols — filtered in _protect()
    r"|\b\d+(?:[.,]\d+)?\b"                    # numbers/prices
    r"|https?://\S+"                           # URLs
    r"|\b[a-z0-9_-]+@[a-z0-9_-]+\b)"           # ids
)

_PLACEHOLDER = "\u0001{}\u0001"


@dataclass(frozen=True)
class TranslationResult:
    text: str
    source_lang: str
    target_lang: str
    applied_rules: int
    translated: bool
    engine: str = "glossary-v1"

    def to_dict(self) -> dict:
        return {
            "text": self.text, "source_lang": self.source_lang,
            "target_lang": self.target_lang, "applied_rules": self.applied_rules,
            "engine": self.engine, "translated": self.translated,
            "note": None if self.translated else
            "translation unavailable — original preserved (fallback)",
        }


def _normalize(lang: str | None) -> str:
    if not lang:
        return DEFAULT_LANGUAGE
    code = lang.lower().strip()[:2]
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def translate_text(text: str, target_lang: str | None,
                   source_lang: str | None = None) -> TranslationResult:
    """Glossary-based deterministic translation.

    - Symbols, prices, URLs and technical IDs are tokenized OUT and restored
      verbatim (never 'translated').
    - Known desk phrases are replaced by their target-language equivalents;
      critical financial terms keep the English anchor in parentheses (P21).
    - If nothing applies, the original is returned unchanged (P23 fallback).
    - Never raises: unexpected failures return the original text.
    """
    try:
        target = _normalize(target_lang)
        src = _normalize(source_lang)
        if not isinstance(text, str) or not text.strip():
            return TranslationResult(text or "", src, target, 0, translated=False)
        if target == src == DEFAULT_LANGUAGE and target == "es":
            # ES output already default: still run glossary so technical terms
            # get anchors, but mark as translated only when rules fire.
            pass

        protected: list[str] = []

        def _protect(match: re.Match) -> str:
            token = match.group(0)
            if token.isalpha() and token.isupper() and token not in _KNOWN_TICKERS:
                return token
            protected.append(token)
            return _PLACEHOLDER.format(len(protected) - 1)

        work = _TOKEN_RE.sub(_protect, text)

        rules_applied = 0

        def _apply(phrase: str, canonical: str) -> None:
            nonlocal rules_applied, work
            replacement = GLOSSARY.get(canonical, {}).get(target)
            if not replacement or replacement.lower() == phrase.lower():
                return
            escaped = re.escape(phrase)
            prefix = r"\b" if phrase[0].isalnum() else ""
            suffix = r"\b" if phrase[-1].isalnum() else ""
            pattern = re.compile(prefix + escaped + suffix, re.IGNORECASE)
            work, n = pattern.subn(replacement, work)
            rules_applied += n if n else 0

        for alias, canonical in _ES_SOURCE_ALIASES:
            _apply(alias, canonical)
        for phrase in GLOSSARY:
            _apply(phrase, phrase)

        # restore protected tokens
        def _restore(match: re.Match) -> str:
            return protected[int(match.group(1))]

        final = re.sub(_PLACEHOLDER.format(r"(\d+)"), _restore, work)
        translated = rules_applied > 0
        return TranslationResult(final, src, target, rules_applied,
                                 translated=translated)
    except Exception:  # noqa: BLE001 — P23: fallback must be unbreakable
        return TranslationResult(text or "", "es", _normalize(target_lang), 0,
                                 translated=False, engine="fallback")


def health() -> dict:
    return {
        "status": "ok", "engine": "glossary-v1",
        "languages": list(LANGUAGES),
        "default_language": DEFAULT_LANGUAGE,
        "ui_keys": len(UI_CATALOGS),
        "glossary_entries": len(GLOSSARY),
    }
