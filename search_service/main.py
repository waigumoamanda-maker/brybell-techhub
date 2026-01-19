# search_service/main.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from elasticsearch import Elasticsearch
from pydantic import BaseModel
from typing import List, Optional
import os

# Elasticsearch Configuration
ES_HOST = os.getenv("ELASTICSEARCH_HOST", "localhost:9200")
ES_INDEX = "products"

es = Elasticsearch([ES_HOST])

# Pydantic Schemas
class ProductIndex(BaseModel):
    id: int
    name: str
    description: str
    price: float
    category: str
    brand: str
    image_url: str

class SearchResult(BaseModel):
    id: int
    name: str
    description: str
    price: float
    category: str
    brand: str
    image_url: str
    score: float

class SearchResponse(BaseModel):
    total: int
    results: List[SearchResult]
    suggestions: List[str] = []

# FastAPI App
app = FastAPI(title="Search Service", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Elasticsearch Index
@app.on_event("startup")
async def startup_event():
    if not es.indices.exists(index=ES_INDEX):
        es.indices.create(
            index=ES_INDEX,
            body={
                "settings": {
                    "analysis": {
                        "analyzer": {
                            "product_analyzer": {
                                "type": "custom",
                                "tokenizer": "standard",
                                "filter": ["lowercase", "stop", "snowball"]
                            }
                        }
                    }
                },
                "mappings": {
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {
                            "type": "text",
                            "analyzer": "product_analyzer",
                            "fields": {
                                "keyword": {"type": "keyword"}
                            }
                        },
                        "description": {
                            "type": "text",
                            "analyzer": "product_analyzer"
                        },
                        "price": {"type": "float"},
                        "category": {"type": "keyword"},
                        "brand": {"type": "keyword"},
                        "image_url": {"type": "keyword"}
                    }
                }
            }
        )

# API Endpoints
@app.get("/")
def root():
    return {"service": "Search Service", "status": "running"}

@app.get("/api/search", response_model=SearchResponse)
def search_products(
    q: str = Query(..., min_length=1),
    category: Optional[str] = None,
    brand: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    skip: int = 0,
    limit: int = 20
):
    # Build query
    must_queries = [
        {
            "multi_match": {
                "query": q,
                "fields": ["name^3", "description", "brand^2", "category"],
                "fuzziness": "AUTO"
            }
        }
    ]
    
    filter_queries = []
    
    if category:
        filter_queries.append({"term": {"category": category}})
    
    if brand:
        filter_queries.append({"term": {"brand": brand}})
    
    if min_price or max_price:
        price_range = {}
        if min_price:
            price_range["gte"] = min_price
        if max_price:
            price_range["lte"] = max_price
        filter_queries.append({"range": {"price": price_range}})
    
    # Execute search
    search_body = {
        "query": {
            "bool": {
                "must": must_queries,
                "filter": filter_queries
            }
        },
        "from": skip,
        "size": limit,
        "sort": [
            {"_score": {"order": "desc"}},
            {"price": {"order": "asc"}}
        ]
    }
    
    try:
        response = es.search(index=ES_INDEX, body=search_body)
        
        results = []
        for hit in response['hits']['hits']:
            source = hit['_source']
            results.append(SearchResult(
                id=source['id'],
                name=source['name'],
                description=source.get('description', ''),
                price=source['price'],
                category=source['category'],
                brand=source.get('brand', ''),
                image_url=source.get('image_url', ''),
                score=hit['_score']
            ))
        
        return SearchResponse(
            total=response['hits']['total']['value'],
            results=results
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/api/search/suggestions")
def get_suggestions(q: str = Query(..., min_length=2)):
    try:
        response = es.search(
            index=ES_INDEX,
            body={
                "suggest": {
                    "product-suggest": {
                        "prefix": q,
                        "completion": {
                            "field": "name.keyword",
                            "size": 5,
                            "skip_duplicates": True
                        }
                    }
                }
            }
        )
        
        suggestions = []
        if 'suggest' in response:
            for option in response['suggest']['product-suggest'][0]['options']:
                suggestions.append(option['text'])
        
        return {"suggestions": suggestions}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Suggestions failed: {str(e)}")

@app.get("/api/search/filters")
def get_available_filters():
    try:
        # Get categories
        category_agg = es.search(
            index=ES_INDEX,
            body={
                "size": 0,
                "aggs": {
                    "categories": {
                        "terms": {"field": "category", "size": 20}
                    }
                }
            }
        )
        
        # Get brands
        brand_agg = es.search(
            index=ES_INDEX,
            body={
                "size": 0,
                "aggs": {
                    "brands": {
                        "terms": {"field": "brand", "size": 50}
                    }
                }
            }
        )
        
        # Get price range
        price_agg = es.search(
            index=ES_INDEX,
            body={
                "size": 0,
                "aggs": {
                    "price_stats": {
                        "stats": {"field": "price"}
                    }
                }
            }
        )
        
        categories = [
            bucket['key'] 
            for bucket in category_agg['aggregations']['categories']['buckets']
        ]
        
        brands = [
            bucket['key'] 
            for bucket in brand_agg['aggregations']['brands']['buckets']
        ]
        
        price_stats = price_agg['aggregations']['price_stats']
        
        return {
            "categories": categories,
            "brands": brands,
            "price_range": {
                "min": price_stats['min'],
                "max": price_stats['max']
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Filter fetch failed: {str(e)}")

@app.post("/api/search/index")
def index_product(product: ProductIndex):
    try:
        es.index(
            index=ES_INDEX,
            id=product.id,
            body=product.dict()
        )
        return {"message": "Product indexed successfully", "id": product.id}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")

@app.post("/api/search/index/bulk")
def index_products_bulk(products: List[ProductIndex]):
    try:
        bulk_data = []
        for product in products:
            bulk_data.append({
                "index": {
                    "_index": ES_INDEX,
                    "_id": product.id
                }
            })
            bulk_data.append(product.dict())
        
        response = es.bulk(body=bulk_data)
        
        return {
            "message": "Bulk indexing completed",
            "indexed": len(products),
            "errors": response.get('errors', False)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulk indexing failed: {str(e)}")

@app.delete("/api/search/index/{product_id}")
def delete_from_index(product_id: int):
    try:
        es.delete(index=ES_INDEX, id=product_id)
        return {"message": "Product removed from index"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

