from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from amazon import amazon, AmazonProductNotFound
from flipkart import flipkart
from utils.urls import canonical_amazon_url_from, expand_url_follow_redirects
import requests
import logging

logger = logging.getLogger("startup")

app = FastAPI()

@app.on_event("startup")
def check_playwright():
    # Solo log informativo: Chromium debe instalarse en build con
    # `playwright install chromium`
    logger.info("✅ API iniciada. Asegúrate de que Chromium está instalado en el build (playwright install chromium).")


class ProductRequest(BaseModel):
    url: str
    compare_platform: bool = False  # si True, también buscamos en la otra plataforma


@app.post("/get_price")
def get_price_endpoint(request: ProductRequest):
    url = request.url

    # expandir short URL
    try:
        final = expand_url_follow_redirects(url)
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error al expandir la URL: {e}")

    result = {}

    try:
        if "amazon" in final:
            canonical = canonical_amazon_url_from(final)
            product_amazon = amazon(canonical)
            result["Amazon"] = {
                "name": product_amazon.name,
                "price": product_amazon.price,
                "currency": "EUR"
            }

            if request.compare_platform:
                # Buscar en Flipkart automáticamente
                flipkart_link = flipkart.search_item(product_amazon.name)
                if flipkart_link != "exit":
                    product_flipkart = flipkart(flipkart_link)
                    result["Flipkart"] = {
                        "name": product_flipkart.name,
                        "price": product_flipkart.price,
                        "currency": "INR"
                    }

        elif "flipkart" in final:
            product_flipkart = flipkart(final)
            result["Flipkart"] = {
                "name": product_flipkart.name,
                "price": product_flipkart.price,
                "currency": "INR"
            }

            if request.compare_platform:
                # Buscar en Amazon automáticamente
                amazon_link = amazon.search_item(product_flipkart.name)
                if amazon_link != "exit":
                    product_amazon = amazon(amazon_link)
                    result["Amazon"] = {
                        "name": product_amazon.name,
                        "price": product_amazon.price,
                        "currency": "EUR"
                    }

        else:
            raise HTTPException(status_code=400, detail="Solo se admiten URLs de Amazon o Flipkart")

        return result

    except AmazonProductNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except requests.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Error de red: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inesperado: {e}")
