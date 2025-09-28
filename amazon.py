# amazon.py (robustificado + Playwright fallback)
from bs4 import BeautifulSoup
import requests
import re
import json
import random
import time
import os
import logging
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Playwright
from playwright.sync_api import sync_playwright

# Logging básico
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("amazon-scraper")

# --- Excepciones ---
class AmazonProductNotFound(Exception):
    pass

class AmazonCaptchaDetected(Exception):
    pass

# --- User agents para rotación ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edg/120.0.0.0",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36"
]

BASE_HEADERS = {
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

# --- Session robusta ---
_session = requests.Session()
retry_strategy = Retry(
    total=3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["HEAD","GET","OPTIONS"]),
    backoff_factor=1
)
_adapter = HTTPAdapter(max_retries=retry_strategy)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)

# Proxies opcionales
_PROXY_LIST = [p.strip() for p in os.environ.get("AMAZON_PROXIES", "").split(",") if p.strip()]

def _choose_proxy():
    return random.choice(_PROXY_LIST) if _PROXY_LIST else None

def _random_delay(min_s=1.0, max_s=4.0):
    delay = random.uniform(min_s, max_s)
    logger.debug(f"Sleeping {delay:.2f}s before request")
    time.sleep(delay)

def _parse_price_number(raw: str):
    if not raw:
        return None
    raw = raw.strip()
    m = re.search(r'[\d\.,]+', raw)
    if not m:
        return None
    num = m.group(0)
    if ',' in num and '.' in num:
        if num.rfind(',') > num.rfind('.'):
            num = num.replace('.', '').replace(',', '.')
        else:
            num = num.replace(',', '')
    elif ',' in num:
        if num.count(',') == 1 and len(num.split(',')[-1]) <= 2:
            num = num.replace(',', '.')
        else:
            num = num.replace(',', '')
    if num.count('.') > 1:
        parts = num.split('.')
        decimal = parts[-1]
        whole = ''.join(parts[:-1])
        num = whole + '.' + decimal
    try:
        return float(num)
    except ValueError:
        return None

def _is_captcha_page(resp_text: str, soup: BeautifulSoup) -> bool:
    text = (resp_text or "").lower()
    captcha_keywords = [
        "captcha", "unusual traffic", "we have detected unusual traffic",
        "type the characters you see in the image", "press and hold",
        "verify you are a human", "pii", "/errors/validateCaptcha"
    ]
    for k in captcha_keywords:
        if k in text:
            return True
    if soup.find("form", attrs={"action": lambda v: v and "/errors/validateCaptcha" in v}):
        return True
    if soup.title and "robot check" in (soup.title.string or "").lower():
        return True
    return False

def _build_referer_from(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        return f"https://{domain}/" if domain else None
    except Exception:
        return None

def _fetch_url(url: str, timeout: float = 20.0):
    _random_delay(1.0, 3.5)
    ua = random.choice(USER_AGENTS)
    headers = dict(BASE_HEADERS)
    headers["User-Agent"] = ua
    referer = _build_referer_from(url)
    if referer:
        headers["Referer"] = referer
    proxies = None
    proxy = _choose_proxy()
    if proxy:
        proxies = {"http": proxy, "https": proxy}
        logger.info(f"Using proxy {proxy}")
    logger.info(f"Fetching URL: {url} (UA: {ua.split(' ')[0]})")
    resp = _session.get(url, headers=headers, timeout=timeout, proxies=proxies)
    logger.info(f"Fetched: {resp.status_code} {resp.url}")
    snippet = resp.text[:800].lower().replace("\n", " ")
    logger.info("HTML snippet: " + snippet[:600])
    return resp

def _fetch_with_playwright(url: str) -> str:
    """Fallback headless browser usando Playwright si CAPTCHA detectado."""
    logger.info("Attempting Playwright headless fetch due to CAPTCHA...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=random.choice(USER_AGENTS))
        page.goto(url, timeout=30000)
        # Esperar a que cargue título o precio
        page.wait_for_selector("span#productTitle, span.a-price-whole", timeout=15000)
        content = page.content()
        browser.close()
        logger.info("Playwright fetch successful")
        return content

class amazon:
    def __init__(self, url: str, timeout: float = 20.0):
        self.url = url
        self.raw_price = None
        self.price = None
        self.name = None

        try:
            resp = _fetch_url(url, timeout)
            soup = BeautifulSoup(resp.content, "lxml")

            if _is_captcha_page(resp.text, soup):
                logger.warning("⚠️ Amazon CAPTCHA detectado. Usando Playwright...")
                html = _fetch_with_playwright(url)
                soup = BeautifulSoup(html, "lxml")
        except AmazonCaptchaDetected:
            logger.error("Playwright fetch falló o CAPTCHA no resuelto")
            raise
        except Exception as e:
            logger.error(f"Error inesperado: {e}")
            raise

        soup = BeautifulSoup(resp.content, "lxml")

        if _is_captcha_page(resp.text, soup):
            logger.warning("⚠️ Amazon CAPTCHA / bloqueo detectado")
            try:
                html = _fetch_with_playwright(url)
                soup = BeautifulSoup(html, "lxml")
            except Exception as e:
                raise AmazonCaptchaDetected(f"Playwright fetch failed: {e}")

        # --- Parseo título ---
        product_html_element = soup.find("span", id="productTitle")
        if not product_html_element:
            alt = soup.select_one("#title, h1#title, h1 span")
            if alt:
                product_html_element = alt
            else:
                with open("debug_amazon_page.html", "wb") as f:
                    f.write(resp.content)
                raise AmazonProductNotFound("Unable to get the product title.")

        self.name = product_html_element.get_text(strip=True)

        # --- Parseo precio ---
        price_text = None
        selectors = [
            "#priceblock_dealprice", "#priceblock_ourprice", "#priceblock_saleprice", "#priceblock_pospromoprice"
        ]
        for sel in selectors:
            elem = soup.select_one(sel)
            if elem:
                price_text = elem.get_text(" ", strip=True)
                break
        if not price_text:
            a_off = soup.select_one("span.a-offscreen")
            if a_off:
                price_text = a_off.get_text(" ", strip=True)
        if not price_text:
            whole = soup.select_one("span.a-price > span.a-price-whole")
            frac = soup.select_one("span.a-price > span.a-price-fraction")
            if whole:
                price_text = whole.get_text(strip=True)
                if frac:
                    price_text = f"{price_text},{frac.get_text(strip=True)}"
        if not price_text:
            meta_price = soup.find("meta", itemprop="price")
            if meta_price and meta_price.get("content"):
                price_text = meta_price["content"]
        if not price_text:
            meta_og = soup.find("meta", property="og:price:amount")
            if meta_og and meta_og.get("content"):
                price_text = meta_og["content"]
        if not price_text:
            scripts = soup.find_all("script", type="application/ld+json")
            for s in scripts:
                if not s.string:
                    continue
                try:
                    data = json.loads(s.string)
                except Exception:
                    continue
                def extract_price_from_ld(d):
                    if isinstance(d, dict):
                        if "offers" in d:
                            offers = d["offers"]
                            if isinstance(offers, dict) and "price" in offers:
                                return offers["price"]
                            if isinstance(offers, list):
                                for o in offers:
                                    if isinstance(o, dict) and "price" in o:
                                        return o["price"]
                        if "price" in d:
                            return d["price"]
                    return None
                if isinstance(data, list):
                    for item in data:
                        p = extract_price_from_ld(item)
                        if p:
                            price_text = str(p)
                            break
                else:
                    p = extract_price_from_ld(data)
                    if p:
                        price_text = str(p)
                if price_text:
                    break
        if not price_text:
            m = re.search(r"(?:€|EUR|Rs\.|₹|\$|USD)\s?[\d\.,]+", resp.text)
            if m:
                price_text = m.group(0)

        self.raw_price = price_text
        self.price = _parse_price_number(price_text) if price_text else None

    def print_product_info(self):
        logger.info("Amazon")
        logger.info(f"Product Name: {self.name}")
        if self.price is not None:
            logger.info(f"Product Price: {self.price}  (raw='{self.raw_price}')")
        else:
            logger.info(f"Product Price: Not found  (raw='{self.raw_price}')")

    @staticmethod
    def search_item(prod_name: str) -> str:
        prod_name = prod_name.replace(" ", "+")
        url = "https://www.amazon.in/s?k=" + prod_name
        resp = _fetch_url(url)
        if resp.status_code != 200:
            raise requests.RequestException(f"Search page returned {resp.status_code}")
        soup = BeautifulSoup(resp.text, "lxml")
        href_attr = soup.find("a", class_="a-link-normal s-underline-text s-underline-link-text s-link-style a-text-normal")
        if not href_attr:
            alt = soup.select_one("div.s-main-slot a.a-link-normal")
            if alt and alt.get("href"):
                href_attr = alt
        if not href_attr:
            raise AmazonProductNotFound("Product not found in search results.")
        link = href_attr.get("href")
        if link.startswith("/"):
            return "https://www.amazon.in" + link
        return link