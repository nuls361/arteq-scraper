"""Sample Apollo API responses for tests."""

ORG_ENRICHMENT = {
    "organization": {
        "name": "Taxfix",
        "estimated_num_employees": 200,
        "industry": "Financial Technology",
        "founded_year": 2016,
        "city": "Berlin",
        "total_funding": 100000000,
    }
}

PEOPLE_SEARCH_DM = {
    "people": [
        {
            "id": "apollo-001",
            "name": "Max Mustermann",
            "title": "CEO & Founder",
            "email": "max@taxfix.de",
            "linkedin_url": "https://www.linkedin.com/in/maxmustermann",
        },
        {
            "id": "apollo-002",
            "name": "Anna Schmidt",
            "title": "CFO",
            "email": "anna@taxfix.de",
            "linkedin_url": "https://www.linkedin.com/in/annaschmidt",
        },
    ]
}

PEOPLE_SEARCH_EMPTY = {"people": []}

PEOPLE_MATCH = {
    "person": {
        "name": "Max Mustermann",
        "email": "max@taxfix.de",
        "email_status": "verified",
        "title": "CEO & Founder",
        "linkedin_url": "https://www.linkedin.com/in/maxmustermann",
        "phone_numbers": [{"sanitized_number": "+49123456789"}],
        "employment_history": [
            {
                "organization_name": "Taxfix",
                "title": "CEO & Founder",
                "start_date": "2016-01",
                "end_date": None,
                "current": True,
            },
            {
                "organization_name": "OldStartup",
                "title": "COO",
                "start_date": "2012-06",
                "end_date": "2015-12",
                "current": False,
            },
        ],
    }
}

PEOPLE_MATCH_NO_RESULT = {"person": None}

PEOPLE_SEARCH_CANDIDATES = {
    "people": [
        {
            "name": "Dr. Klaus Fischer",
            "title": "Interim CFO",
            "email": "klaus@example.com",
            "linkedin_url": "https://www.linkedin.com/in/klausfischer",
            "city": "Berlin",
            "country": "Germany",
        },
        {
            "name": "A",  # Too short, should be filtered
            "title": "Test",
            "email": None,
            "linkedin_url": None,
        },
    ]
}
