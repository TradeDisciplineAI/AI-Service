import logging
import os

from newsapi import NewsApiClient

logger = logging.getLogger(__name__)


def fetch_financial_news(ticker: str) -> str:
    logger.info(f"Fetching NewsAPI data for: {ticker}")
    api_key = os.getenv("NEWS_API_KEY")

    if not api_key:
        logger.warning("NEWS_API_KEY is missing.")
        return "No news data available (Missing API Key)."

    try:
        newsapi = NewsApiClient(api_key=api_key)
        response = newsapi.get_everything(
            q=f"{ticker} OR SEBI", language="en", sort_by="relevancy", page_size=15
        )

        articles = response.get("articles", [])
        if not articles:
            return f"No recent news found for {ticker}."

        results = [
            f"- {a.get('title', 'No Title')}: {a.get('description', 'No Desc')}"
            for a in articles
        ]
        return "NEWS DATA:\n" + "\n".join(results)
    except Exception as e:
        logger.error(f"NewsAPI Error: {e}")
        return "Error fetching news data."
