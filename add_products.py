import requests

products = [
    {
        "name": "iPhone 15 Pro Max",
        "description": "Latest iPhone with A17 Pro chip",
        "price": 189999,
        "category": "phones",
        "brand": "Apple",
        "stock_quantity": 50,
        "image_url": "https://images.unsplash.com/photo-1695048133142-1a20484d2569?w=500",
        "featured": True
    },
    # Add more products...
]

for product in products:
    response = requests.post("http://localhost:8001/api/products", json=product)
    print(f"Added: {product['name']} - Status: {response.status_code}")