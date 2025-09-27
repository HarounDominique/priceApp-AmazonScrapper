from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from amazon import amazon
from flipkart import flipkart
from utils.urls import canonical_amazon_url_from, expand_url_follow_redirects

app = FastAPI()

class ProductRequest(BaseModel):
    url: str

@app.post("/get_price")
def get_price_endpoint(request: ProductRequest):
    url = request.url

    # expandir short URL
    final = expand_url_follow_redirects(url)

    # canonicalizar Amazon
    canonical = canonical_amazon_url_from(final)

    url_to_scrape = canonical

    try:
        if "amazon" in url_to_scrape:
            product = amazon(url_to_scrape)
            return {
                "source": "Amazon",
                "name": product.name,
                "price": product.price,
                "currency": "EUR"  # ponlo en EUR si scrapeas amazon.es
            }

        elif "flipkart" in url_to_scrape:
            product = flipkart(url_to_scrape)
            return {
                "source": "Flipkart",
                "name": product.name,
                "price": product.price,
                "currency": "INR"
            }

        else:
            raise HTTPException(status_code=400, detail="Solo se admiten URLs de Amazon o Flipkart")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
