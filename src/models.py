from typing import TypedDict, List
from pydantic import BaseModel, Field


class Agent1State(TypedDict):
    ticker: str
    market_data: str
    final_scan_json: dict


# The memory bucket for Agent 2's workflow
class Agent2State(TypedDict):
    ticker: str
    news_data: str
    reddit_data: str
    twitter_data: str
    final_analysis_json: dict

# The strict JSON structure Agent 3 needs to receive
class SentimentReport(BaseModel):
    ticker: str = Field(description="The stock ticker symbol")
    overall_sentiment: str = Field(description="Must be 'Bullish', 'Bearish', or 'Neutral'")
    conviction_score: int = Field(description="Confidence score from 1 to 10")
    summary: str = Field(description="A concise 2-sentence summary of the market sentiment")
    top_headlines: List[str] = Field(description="A list of the 3 most important news headlines or tweets we found.")