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


@app.post("/get_price")
def get_price_endpoint(request: ProductRequest):
    url = request.url

    # expandir short URL
    try:
        final = expand_url_follow_redirects(url)
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error al expandir la URL: {e}")

    # canonicalizar Amazon
    canonical = canonical_amazon_url_from(final)
    url_to_scrape = canonical

    try:
        if "amazon" in url_to_scrape:
            try:
                product = amazon(url_to_scrape)
                return {
                    "source": "Amazon",
                    "name": product.name,
                    "price": product.price,
                    "currency": "EUR"  # ponlo en EUR si scrapeas amazon.es
                }
            except AmazonProductNotFound as e:
                raise HTTPException(status_code=404, detail=str(e))
            except requests.RequestException as e:
                raise HTTPException(status_code=503, detail=f"Error de red al acceder a Amazon: {e}")

        elif "flipkart" in url_to_scrape:
            try:
                product = flipkart(url_to_scrape)
                return {
                    "source": "Flipkart",
                    "name": product.name,
                    "price": product.price,
                    "currency": "INR"
                }
            except requests.RequestException as e:
                raise HTTPException(status_code=503, detail=f"Error de red al acceder a Flipkart: {e}")

        else:
            raise HTTPException(status_code=400, detail="Solo se admiten URLs de Amazon o Flipkart")

    except HTTPException:
        raise  # Dejar que FastAPI maneje las HTTPException
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inesperado: {e}")