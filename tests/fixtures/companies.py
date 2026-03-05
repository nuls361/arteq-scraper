"""Sample company data for tests."""

TAXFIX = {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "Taxfix",
    "domain": "taxfix.de",
    "industry": "FinTech",
    "funding_stage": "Series C",
    "headcount": "200",
    "status": "lead",
    "enrichment_status": "complete",
    "hq_city": "Berlin",
    "funding_amount": "$100,000,000",
    "composite_score": 85,
    "arteq_fit": "high",
}

PERSONIO = {
    "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "name": "Personio GmbH",
    "domain": "personio.de",
    "industry": "HR Tech",
    "funding_stage": "Series E",
    "headcount": "1800",
    "status": "prospect",
    "enrichment_status": "complete",
    "hq_city": "Munich",
    "funding_amount": "$270,000,000",
    "composite_score": 70,
    "arteq_fit": "medium",
}

NOVATECH = {
    "id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
    "name": "NovaTech AG",
    "domain": "novatech.ch",
    "industry": "Deep Tech",
    "funding_stage": "Series A",
    "headcount": "45",
    "status": "lead",
    "enrichment_status": "pending",
    "hq_city": "Zurich",
    "funding_amount": "$12,000,000",
    "composite_score": None,
    "arteq_fit": None,
}

COMPANY_LIST = [TAXFIX, PERSONIO, NOVATECH]

COMPANY_LIST_SLIM = [
    {"id": TAXFIX["id"], "name": "Taxfix", "domain": "taxfix.de"},
    {"id": PERSONIO["id"], "name": "Personio GmbH", "domain": "personio.de"},
    {"id": NOVATECH["id"], "name": "NovaTech AG", "domain": "novatech.ch"},
]
