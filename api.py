from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from amazon import amazon
from flipkart import flipkart

app = FastAPI()

class ProductRequest(BaseModel):
    url: str


@app.post("/get_price")
def get_price_endpoint(request: ProductRequest):
    url = request.url

    try:
        if "amazon" in url:
            product = amazon(url)
            return {
                "source": "Amazon",
                "name": product.name,
                "price": product.price,
                "currency": "INR"  # cámbialo a EUR si scrapeas amazon.es
            }

        elif "flipkart" in url:
            product = flipkart(url)
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
