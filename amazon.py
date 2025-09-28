from bs4 import BeautifulSoup
import requests
import sys

header = {
    'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0',
    'Accept-Language': 'en-US,en;q=0.5',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1'
}


class amazon:
    def __init__(self, url):
        self.url = url
        response = requests.get(url, headers=header)
        if response.status_code != 200:
            sys.exit(f"Unable to get the page. Error code: {response.status_code}")

        html_text = response.content
        soup = BeautifulSoup(html_text, 'lxml')

        product_html_element = soup.find('span', id='productTitle')

        if self.__check_if_product_exists(product_html_element):
            self.name = product_html_element.text.strip()

            # 🔎 Buscar el precio en distintos elementos (deal, normal, fallback)
            price_element = (
                    soup.find(id="priceblock_dealprice")
                    or soup.find(id="priceblock_ourprice")
                    or soup.select_one("span.a-price > span.a-price-whole")
            )

            if price_element:
                self.price = price_element.text.strip()
            else:
                self.price = None  # No se encontró precio
        else:
            sys.exit("Unable to get the product. Please check the URL and try again.")

    def __check_if_product_exists(self, soup):
        return soup is not None

    def print_product_info(self):
        print("Amazon")
        print(f"Product Name: {self.name}")
        if self.price:
            print(f"Product Price: {self.price}")
        else:
            print("Product Price: Not found")
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

        href_attr = soup.find('a',
                              class_="a-link-normal s-underline-text s-underline-link-text s-link-style a-text-normal")
        link = ""
        if not href_attr:
            print(
                '''We were unable to find the product on Amazon. Please paste the link of the product if you have any. Else type "exit"''')
            link = input("> ")
            return link
        if link == "exit":
            return link

        link = "https://www.amazon.in" + href_attr['href']
        return link