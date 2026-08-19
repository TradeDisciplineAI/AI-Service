from pydantic import BaseModel
from typing import List

# This blueprint ensures the user sends a valid stock ticker
class AnalyzeRequest(BaseModel):
    ticker: str

class BatchAnalyzeRequest(BaseModel):
    tickers: List[str]