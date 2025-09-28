from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from amazon import amazon, AmazonProductNotFound
from flipkart import flipkart
from utils.urls import canonical_amazon_url_from, expand_url_follow_redirects
import requests

# 👇 Extra: intentar instalar Chromium en runtime si no existe
import asyncio
import logging
import pathlib
from playwright.__main__ import main as playwright_main

logger = logging.getLogger("startup")

try:
    chromium_path = pathlib.Path.home() / ".cache/ms-playwright"
    if not chromium_path.exists() or not any(chromium_path.rglob("headless_shell")):
        logger.warning("⚠️ Chromium no encontrado, instalando con Playwright...")
        # Ejecutar instalación de chromium en un thread para no bloquear
        asyncio.run(asyncio.to_thread(playwright_main, ["install", "chromium"]))
        asyncio.run(asyncio.to_thread(playwright_main, ["install-deps", "chromium"]))
    else:
        logger.info("✅ Chromium ya está instalado")
except Exception as e:
    logger.error(f"❌ Fallo al intentar instalar Chromium automáticamente: {e}")

app = FastAPI()


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