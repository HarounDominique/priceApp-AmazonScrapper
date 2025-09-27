# utils/urls.py  (o pégalo en api.py)
import re
import time
from urllib.parse import urlparse

import requests

# Cabeceras parecidas a las que ya usas para scraping
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
}

# Simple cache en memoria con TTL para evitar resolver la misma short-url cada vez
_RESOLVE_CACHE = {}
_CACHE_TTL_SECONDS = 24 * 3600  # 24h, ajustar según necesidad


def _cache_get(key):
    rec = _RESOLVE_CACHE.get(key)
    if not rec:
        return None
    value, ts = rec
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _RESOLVE_CACHE.pop(key, None)
        return None
    return value


def _cache_set(key, value):
    _RESOLVE_CACHE[key] = (value, time.time())


def expand_url_follow_redirects(url: str, timeout: float = 15.0, headers: dict = None) -> str:
    """
    Sigue redirects y devuelve la URL final. Usa GET con stream=True (más fiable que HEAD).
    Si algo falla, devuelve la URL original.
    """
    headers = headers or DEFAULT_HEADERS

    cached = _cache_get(url)
    if cached:
        return cached

    try:
        # Usamos stream=True para no descargar el body entero si no hace falta
        with requests.get(url, headers=headers, allow_redirects=True, timeout=timeout, stream=True) as resp:
            final = resp.url  # URL final después de redirecciones
            # Guardamos en cache
            _cache_set(url, final)
            return final
    except requests.RequestException:
        # En fallo de red devolvemos la original (el caller deberá manejar el error)
        return url


_ASIN_RE = re.compile(
    r"(?:/dp/|/gp/product/|/gp/aw/d/|/product/|/gp/offer-listing/)([A-Z0-9]{10})",
    re.IGNORECASE
)


def extract_asin(url: str) -> str | None:
    """
    Extrae ASIN de la URL si existe.
    """
    m = _ASIN_RE.search(url)
    if m:
        return m.group(1)
    # A veces la ASIN aparece como /product-reviews/ASIN/... o en query params.
    # Intentamos un fallback: buscar 10-char alfanumérico
    m2 = re.search(r"/([A-Z0-9]{10})(?:[/?]|$)", url, re.IGNORECASE)
    if m2:
        return m2.group(1)
    return None


def canonical_amazon_url_from(final_url: str) -> str:
    """
    Dada una URL final (resuelta), construye una URL canónica tipo https://www.amazon.<tld>/dp/ASIN.
    Si no encuentra ASIN, devuelve la final_url sin cambiar.
    """
    asin = extract_asin(final_url)
    if not asin:
        return final_url

    # intentar sacar el TLD/región del host (ej: amazon.es -> amazon.es)
    parsed = urlparse(final_url)
    host = parsed.netloc.lower()
    # priorizamos amazon.* host en la final_url; si no se detecta amazon, default a amazon.es
    tld = "amazon.es"
    if "amazon." in host:
        # tomamos la parte 'amazon.xx' o 'amazon.co.uk'
        # buscamos "amazon." y extraemos lo que viene hasta la primera /
        # simplificamos: host puede ser 'www.amazon.es' -> usamos last two components
        parts = host.split(".")
        # construir 'amazon.xx' o 'amazon.co.uk' (hasta 3 partes)
        if len(parts) >= 2:
            # tomar las últimas 2 o 3 partes si el penúltimo es 'co' -> 'co.uk'
            if parts[-2] == "co" and len(parts) >= 3:
                tld = "amazon." + parts[-2] + "." + parts[-1]  # amazon.co.uk
            else:
                tld = "amazon." + parts[-1]  # amazon.es, amazon.com, amazon.in, etc.
    else:
        # si no aparece amazon en host, quizá redireccionó a amazon vía path; por seguridad fallback amazon.es
        tld = "amazon.es"

    return f"https://www.{tld}/dp/{asin}"