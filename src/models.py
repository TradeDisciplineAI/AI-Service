from typing import Any, TypedDict

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
    overall_sentiment: str = Field(
        description="Must be 'Bullish', 'Bearish', or 'Neutral'"
    )
    conviction_score: int = Field(description="Confidence score from 1 to 10")
    summary: str = Field(
        description="A concise 2-sentence summary of the market sentiment"
    )
    top_headlines: list[str] = Field(
        description="A list of the 3 most important news headlines or tweets we found."
    )


# Memory state for Agent 3 (Strategy Engine)
class Agent3State(TypedDict):
    ticker: str
    market_scan_json: dict[str, Any] | None
    sentiment_analysis_json: dict[str, Any] | None
    rag_context_json: dict[str, Any] | None
    technicals_json: dict[str, Any] | None
    final_trade_signal: dict[str, Any] | None
    errors: list[str] | None
