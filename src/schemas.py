from pydantic import BaseModel

# This blueprint ensures the user sends a valid stock ticker
class AnalyzeRequest(BaseModel):
    ticker: str