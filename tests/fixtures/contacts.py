"""Sample contact data for tests."""

DM_CEO = {
    "id": "contact-001",
    "name": "Max Mustermann",
    "title": "CEO & Founder",
    "email": "max@taxfix.de",
    "phone": "+49123456789",
    "linkedin_url": "https://www.linkedin.com/in/maxmustermann",
    "decision_maker_score": 95,
    "enrichment_status": "complete",
    "source": "apollo_search",
}

DM_CFO = {
    "id": "contact-002",
    "name": "Anna Schmidt",
    "title": "CFO",
    "email": "anna@personio.de",
    "phone": "+49987654321",
    "linkedin_url": "https://www.linkedin.com/in/annaschmidt",
    "decision_maker_score": 85,
    "enrichment_status": "complete",
    "source": "apollo_search",
}

CONTACT_NO_EMAIL = {
    "id": "contact-003",
    "name": "Hans Weber",
    "title": "Head of People",
    "email": None,
    "phone": None,
    "linkedin_url": "https://www.linkedin.com/in/hansweber",
    "decision_maker_score": 60,
    "enrichment_status": "pending",
    "source": "apollo_search",
}

CANDIDATE_INTERIM_CFO = {
    "id": "cand-001",
    "full_name": "Dr. Klaus Fischer",
    "email": "klaus.fischer@gmail.com",
    "phone": "+49111222333",
    "linkedin_url": "https://www.linkedin.com/in/klausfischer",
    "current_title": "Interim CFO | Fractional Finance Executive",
    "function": "cfo",
    "employment_type": "interim",
    "location_city": "Berlin",
    "location_country": "germany",
    "source": "pdl",
    "source_url": "https://www.linkedin.com/in/klausfischer",
    "skills": ["strategy", "m&a", "fundraising", "p&l", "financial controlling"],
    "score": 85,
    "tier": "available",
}

CANDIDATE_FRACTIONAL_CTO = {
    "id": "cand-002",
    "full_name": "Lisa Berger",
    "email": "lisa@berger-tech.de",
    "phone": None,
    "linkedin_url": "https://www.linkedin.com/in/lisaberger",
    "current_title": "Fractional CTO & Engineering Advisor",
    "function": "cto",
    "employment_type": "fractional",
    "location_city": "Munich",
    "location_country": "germany",
    "source": "substack",
    "source_url": "https://lisaberger.substack.com",
    "skills": ["leadership", "scaling", "digital transformation"],
    "score": 75,
    "tier": "available",
}

CANDIDATE_LOW_SCORE = {
    "id": "cand-003",
    "full_name": "Tom Brown",
    "email": None,
    "phone": None,
    "linkedin_url": None,
    "current_title": "Consultant",
    "function": "other",
    "employment_type": "freelance",
    "location_city": "London",
    "location_country": "uk",
    "source": "apollo",
    "source_url": None,
    "skills": [],
    "score": 10,
    "tier": "research",
}

COMPANY_CONTACT_LINK = {
    "company_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "contact_id": "contact-001",
    "is_decision_maker": True,
    "role_at_company": "CEO & Founder",
    "contact": DM_CEO,
}
