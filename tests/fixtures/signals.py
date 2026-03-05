"""Sample signal/article data for tests."""

RSS_ARTICLE_FUNDING = {
    "company_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "company_name": "Taxfix",
    "title": "Taxfix raises $100M Series C to expand across Europe",
    "summary": "Berlin-based fintech Taxfix has raised $100 million in a Series C funding round led by Index Ventures.",
    "source_url": "https://techcrunch.com/taxfix-series-c",
    "source": "rss_techcrunch",
    "published": "2026-03-01",
}

DDG_ARTICLE_LEADERSHIP = {
    "company_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "company_name": "Personio GmbH",
    "title": "Personio CFO steps down after 5 years",
    "summary": "The CFO of Personio has announced their departure, leaving the company searching for a replacement.",
    "source_url": "https://handelsblatt.com/personio-cfo",
    "source": "web_search",
    "published": "2026-02-28",
}

IRRELEVANT_ARTICLE = {
    "company_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
    "company_name": "NovaTech AG",
    "title": "NovaTech wins Best Deep Tech Startup award",
    "summary": "NovaTech AG has been named Best Deep Tech Startup at the Swiss Innovation Awards.",
    "source_url": "https://startupticker.ch/novatech-award",
    "source": "rss_gruenderszene",
    "published": "2026-02-27",
}

HOT_SIGNAL = {
    "id": "sig-001",
    "company_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "company_name": "Taxfix",
    "type": "funding_round",
    "title": "Taxfix raises $100M Series C",
    "description": "Berlin-based fintech Taxfix raised $100M in Series C.",
    "is_hot": True,
    "interim_relevance": "hot",
    "relevance_score": 90,
    "urgency": "high",
    "source": "rss_techcrunch",
    "source_url": "https://techcrunch.com/taxfix-series-c",
    "processed": False,
}

WARM_SIGNAL = {
    "id": "sig-002",
    "company_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "company_name": "Personio GmbH",
    "type": "expansion",
    "title": "Personio expands to France",
    "description": "Personio opens new office in Paris.",
    "is_hot": False,
    "interim_relevance": "warm",
    "relevance_score": 55,
    "urgency": "medium",
    "source": "web_search",
    "source_url": "https://example.com/personio-france",
    "processed": False,
}

ARTICLES_MIXED = [
    RSS_ARTICLE_FUNDING,
    DDG_ARTICLE_LEADERSHIP,
    IRRELEVANT_ARTICLE,
]
