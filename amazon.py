# amazon.py (modificado)
from bs4 import BeautifulSoup
import requests
import sys
import re
import json

header = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36',
    'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1'
}


def _parse_price_number(raw: str):
    """
    Extrae un número flotante a partir de un texto de precio (p. ej. "€1.234,56", "Rs. 1,499", "$149.99").
    Devuelve float o None.
    """
    if not raw:
        return None
    raw = raw.strip()
    m = re.search(r'[\d\.,]+', raw)
    if not m:
        return None
    num = m.group(0)

    # Si hay ambos separadores, decidimos cuál es decimal atendiendo al que aparece más a la derecha
    if ',' in num and '.' in num:
        if num.rfind(',') > num.rfind('.'):
            # coma decimal, punto separador de miles
            num = num.replace('.', '')
            num = num.replace(',', '.')
        else:
            # punto decimal, coma separador de miles
            num = num.replace(',', '')
    elif ',' in num:
        # solo comas: si hay una sola coma y los decimales <= 2 asumimos coma decimal
        if num.count(',') == 1 and len(num.split(',')[-1]) <= 2:
            num = num.replace(',', '.')
        else:
            # varias comas -> probablemente separadores de miles
            num = num.replace(',', '')
    # si hay más de un punto, asumimos el último como decimal
    if num.count('.') > 1:
        parts = num.split('.')
        decimal = parts[-1]
        whole = ''.join(parts[:-1])
        num = whole + '.' + decimal

    try:
        return float(num)
    except ValueError:
        return None


class amazon:
    def __init__(self, url, timeout=15):
        self.url = url
        try:
            resp = requests.get(url, headers=header, timeout=timeout)
        except requests.RequestException as e:
            sys.exit(f"Unable to get the page. {e}")

        if resp.status_code != 200:
            sys.exit(f"Unable to get the page. Error code: {resp.status_code}")

        soup = BeautifulSoup(resp.content, 'lxml')

        product_html_element = soup.find('span', id='productTitle')
        if not product_html_element:
            # Para debug: opcionalmente guardar el HTML en fichero si quieres inspeccionar
            # with open("debug_amazon_page.html","wb") as f: f.write(resp.content)
            sys.exit("Unable to get the product. Please check the URL and try again.")

        self.name = product_html_element.get_text(strip=True)

        price_text = None

        # 1) ids clásicos (dealprice / ourprice / saleprice)
        price_elem = soup.select_one(
            '#priceblock_dealprice, #priceblock_ourprice, #priceblock_saleprice, #priceblock_pospromoprice'
        )
        if price_elem:
            price_text = price_elem.get_text(" ", strip=True)

        # 2) span.a-offscreen (muy común en Amazon para accesibilidad)
        if not price_text:
            a_off = soup.select_one('span.a-offscreen')
            if a_off:
                price_text = a_off.get_text(" ", strip=True)

        # 3) fallback whole + fraction (ej: <span class="a-price-whole">149</span><span class="a-price-fraction">,99</span>)
        if not price_text:
            whole = soup.select_one('span.a-price > span.a-price-whole')
            frac = soup.select_one('span.a-price > span.a-price-fraction')
            if whole:
                price_text = whole.get_text(strip=True)
                if frac:
                    # cuidamos decimales como aparece en el HTML (normalmente coma en ES)
                    price_text = f"{price_text},{frac.get_text(strip=True)}"

        # 4) meta itemprop / og price
        if not price_text:
            meta_price = soup.find('meta', itemprop='price')
            if meta_price and meta_price.get('content'):
                price_text = meta_price['content']

        if not price_text:
            meta_og = soup.find('meta', property='og:price:amount')
            if meta_og and meta_og.get('content'):
                price_text = meta_og['content']

        # 5) JSON-LD structured data
        if not price_text:
            scripts = soup.find_all('script', type='application/ld+json')
            for s in scripts:
                if not s.string:
                    continue
                try:
                    data = json.loads(s.string)
                except Exception:
                    continue

                def extract_price_from_ld(d):
                    if isinstance(d, dict):
                        if 'offers' in d:
                            offers = d['offers']
                            if isinstance(offers, dict) and 'price' in offers:
                                return offers['price']
                            if isinstance(offers, list):
                                for o in offers:
                                    if isinstance(o, dict) and 'price' in o:
                                        return o['price']
                        if 'price' in d:
                            return d['price']
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

        # 6) fallback regex buscando símbolo + número en el HTML (último recurso)
        if not price_text:
            m = re.search(r'(?:€|EUR|Rs\.|₹|\$|USD)\s?[\d\.,]+', resp.text)
            if m:
                price_text = m.group(0)

        self.raw_price = price_text
        self.price = _parse_price_number(price_text) if price_text else None

    def print_product_info(self):
        print("Amazon")
        print(f"Product Name: {self.name}")
        if self.price is not None:
            print(f"Product Price: {self.price}  (raw='{self.raw_price}')")
        else:
            print(f"Product Price: Not found  (raw='{self.raw_price}')")
        print("-----------------------------------------------------------------------------------------")

    @staticmethod
    def search_item(prod_name):
        prod_name = prod_name.replace(" ", "+")
        url = "https://www.amazon.in/s?k=" + prod_name

        response = requests.get(url, headers=header)
        if response.status_code != 200:
            sys.exit(f"Unable to get the page. Error code: {response.status_code}")

        html_text = response.text
        soup = BeautifulSoup(html_text, 'lxml')

        href_attr = soup.find('a', class_="a-link-normal s-underline-text s-underline-link-text s-link-style a-text-normal")
        link = ""
        if not href_attr:
            print('''We were unable to find the product on Amazon. Please paste the link of the product if you have any. Else type "exit"''')
            link = input("> ")
            return link
        if link == "exit":
            return link

        link = "https://www.amazon.in" + href_attr['href']
        return link