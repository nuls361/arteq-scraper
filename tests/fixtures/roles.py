"""Sample role data for tests."""

JSEARCH_RAW = {
    "employer_name": "Taxfix",
    "employer_logo": "https://logo.taxfix.de/logo.png",
    "employer_company_type": "Startup",
    "job_title": "Interim CFO",
    "job_city": "Berlin",
    "job_state": "Berlin",
    "job_country": "DE",
    "job_is_remote": False,
    "job_posted_at_datetime_utc": "2026-03-01T08:00:00.000Z",
    "job_description": "We are looking for an experienced Interim CFO to lead our finance team during a transition period.",
    "job_employment_type": "CONTRACT",
    "job_apply_link": "https://taxfix.jobs/interim-cfo",
    "job_google_link": "https://google.com/job/123",
    "job_required_experience": {"required_experience_in_months": 120},
    "job_highlights": {},
}

JSEARCH_RAW_REMOTE = {
    "employer_name": "RemoteCo",
    "employer_logo": "",
    "employer_company_type": "",
    "job_title": "Fractional CTO",
    "job_city": "",
    "job_state": "",
    "job_country": "",
    "job_is_remote": True,
    "job_posted_at_datetime_utc": "2026-02-28T12:00:00.000Z",
    "job_description": "Fractional CTO for scaling engineering team.",
    "job_employment_type": "CONTRACTOR",
    "job_apply_link": "",
    "job_google_link": "https://google.com/job/456",
    "job_required_experience": None,
    "job_highlights": None,
}

JSEARCH_RAW_MINIMAL = {
    "employer_name": "Unknown",
    "job_title": "",
}

HOT_ROLE = {
    "id": "role-001",
    "title": "Interim CFO",
    "company": "Taxfix",
    "company_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "location": "Berlin, Germany",
    "is_remote": False,
    "description": "Looking for an experienced Interim CFO.",
    "url": "https://taxfix.jobs/interim-cfo",
    "posted": "2026-03-01",
    "source": "jsearch",
    "is_hot": True,
    "classification": "hot",
    "classification_reason": "Explicit interim in title, C-Level role at funded startup",
    "engagement_type": "Interim",
    "role_function": "Finance",
    "role_level": "C-Level",
    "tier": "hot",
    "status": "active",
}

WARM_ROLE = {
    "id": "role-002",
    "title": "Head of Finance",
    "company": "Personio GmbH",
    "company_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "location": "Munich, Germany",
    "is_remote": False,
    "description": "Personio is hiring a Head of Finance.",
    "url": "https://personio.jobs/head-of-finance",
    "posted": "2026-02-28",
    "source": "arbeitnow",
    "is_hot": False,
    "classification": "warm",
    "classification_reason": "Head-level finance role at scale-up, no explicit interim signal",
    "engagement_type": "Full-time",
    "role_function": "Finance",
    "role_level": "Head/Director",
    "tier": "warm",
    "status": "active",
}

EXCLUDED_ROLE_COMPANY = {
    "company": "Hays",
    "title": "CFO",
    "location": "Berlin, Germany",
    "url": "https://hays.de/cfo",
    "source": "jsearch",
}

EXCLUDED_ROLE_TITLE = {
    "company": "Taxfix",
    "title": "Finance Intern",
    "location": "Berlin, Germany",
    "url": "https://taxfix.jobs/intern",
    "source": "jsearch",
}

SCRAPED_JOBS = [
    {
        "company": "Taxfix",
        "title": "Interim CFO",
        "location": "Berlin, Germany",
        "is_remote": False,
        "description": "Looking for an experienced Interim CFO.",
        "url": "https://taxfix.jobs/interim-cfo",
        "posted": "2026-03-01",
        "source": "jsearch",
    },
    {
        "company": "Personio GmbH",
        "title": "Head of Finance",
        "location": "Munich, Germany",
        "is_remote": False,
        "description": "Personio is hiring a Head of Finance.",
        "url": "https://personio.jobs/head-of-finance",
        "posted": "2026-02-28",
        "source": "arbeitnow",
    },
    {
        "company": "NovaTech AG",
        "title": "Fractional CTO",
        "location": "Zurich, Switzerland",
        "is_remote": True,
        "description": "Fractional CTO for deep tech company.",
        "url": "https://novatech.ch/cto",
        "posted": "2026-03-02",
        "source": "jsearch",
    },
]
