import logging
import os

import tweepy

logger = logging.getLogger(__name__)


def fetch_twitter_sentiment(ticker: str) -> str:
    logger.info(f"Fetching Twitter data for: {ticker}")
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN")

    if not bearer_token:
        logger.warning("TWITTER_BEARER_TOKEN missing.")
        return "No Twitter data available (Missing API Key)."

    try:
        client = tweepy.Client(bearer_token=bearer_token)
        response = client.search_recent_tweets(
            query=f"{ticker} -is:retweet lang:en", max_results=10
        )

        if not response.data:
            return f"No recent tweets found for {ticker}."

        results = [f"- {tweet.text}" for tweet in response.data]
        return "TWITTER DATA:\n" + "\n".join(results)
    except Exception as e:
        logger.error(f"Tweepy Error: {e}")
        return "Error fetching Twitter data."
