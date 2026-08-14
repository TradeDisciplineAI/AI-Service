import os
import pytest

# Ensure dummy environment variables are set for testing before modules import external connections
os.environ.setdefault("GOOGLE_API_KEY", "mock-google-api-key-for-testing")
os.environ.setdefault("GEMINI_API_KEY", "mock-gemini-api-key-for-testing")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
