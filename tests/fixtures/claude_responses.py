"""Sample Claude API responses for tests."""

CLASSIFY_ROLES_HOT_WARM = """{
  "roles": [
    {
      "index": 1,
      "score": 82,
      "is_disqualified": false,
      "score_breakdown": {
        "engagement_type_pts": 55,
        "role_type_pts": 20,
        "structural_pts": 12,
        "company_stage_pts": 10,
        "deductions_bonuses": -15,
        "agency_capped": false
      },
      "reason": "Explicit Interim CFO title at funded startup",
      "engagement_type": "Interim",
      "role_function": "Finance",
      "role_level": "C-Level"
    },
    {
      "index": 2,
      "score": 45,
      "is_disqualified": false,
      "score_breakdown": {
        "engagement_type_pts": 25,
        "role_type_pts": 8,
        "structural_pts": 8,
        "company_stage_pts": 10,
        "deductions_bonuses": -6,
        "agency_capped": false
      },
      "reason": "Head-level finance role at scale-up, no interim signal",
      "engagement_type": "Full-time",
      "role_function": "Finance",
      "role_level": "Head/Director"
    }
  ]
}"""

CLASSIFY_ROLES_ALL_COLD = """{
  "roles": [
    {"index": 1, "classification": "cold", "reason": "Junior role"}
  ]
}"""

CLASSIFY_ROLES_ALL_DISQUALIFIED = """{
  "roles": [
    {"index": 1, "score": 0, "is_disqualified": true, "score_breakdown": {"engagement_type_pts": 0, "role_type_pts": 0, "structural_pts": 0, "company_stage_pts": 0, "deductions_bonuses": 0, "agency_capped": false}, "reason": "Junior intern role", "engagement_type": "Full-time", "role_function": "Other", "role_level": "Other"},
    {"index": 2, "score": 0, "is_disqualified": true, "score_breakdown": {"engagement_type_pts": 0, "role_type_pts": 0, "structural_pts": 0, "company_stage_pts": 0, "deductions_bonuses": 0, "agency_capped": false}, "reason": "Non-DACH role", "engagement_type": "Full-time", "role_function": "Other", "role_level": "Other"}
  ]
}"""

CLASSIFY_ROLES_PARK = """{
  "roles": [
    {
      "index": 1,
      "score": 25,
      "is_disqualified": false,
      "score_breakdown": {
        "engagement_type_pts": 8,
        "role_type_pts": 5,
        "structural_pts": 8,
        "company_stage_pts": 6,
        "deductions_bonuses": -2,
        "agency_capped": false
      },
      "reason": "VP-level role at established company, low interim fit",
      "engagement_type": "Full-time",
      "role_function": "Finance",
      "role_level": "VP"
    }
  ]
}"""

CLASSIFY_ROLES_AGENCY_CAPPED = """{
  "roles": [
    {
      "index": 1,
      "score": 8,
      "is_disqualified": false,
      "score_breakdown": {
        "engagement_type_pts": 55,
        "role_type_pts": 20,
        "structural_pts": 8,
        "company_stage_pts": 10,
        "deductions_bonuses": 0,
        "agency_capped": true
      },
      "reason": "Agency posting for Interim CFO, capped at 8",
      "engagement_type": "Interim",
      "role_function": "Finance",
      "role_level": "C-Level"
    }
  ]
}"""

CLASSIFY_ROLES_MARKDOWN_FENCED = """```json
{
  "roles": [
    {
      "index": 1,
      "score": 82,
      "is_disqualified": false,
      "score_breakdown": {
        "engagement_type_pts": 55,
        "role_type_pts": 20,
        "structural_pts": 12,
        "company_stage_pts": 10,
        "deductions_bonuses": -15,
        "agency_capped": false
      },
      "reason": "Interim in title",
      "engagement_type": "Interim",
      "role_function": "Finance",
      "role_level": "C-Level"
    }
  ]
}
```"""

CLASSIFY_SIGNALS_HOT = """{
  "articles": [
    {
      "index": 1,
      "is_hot": true,
      "interim_relevance": "hot",
      "signal_type": "funding_round",
      "relevance_score": 90,
      "urgency": "high",
      "description": "Series C funding signals rapid growth and likely need for interim leadership."
    }
  ]
}"""

CLASSIFY_SIGNALS_IRRELEVANT = """{
  "articles": [
    {
      "index": 1,
      "is_hot": false,
      "interim_relevance": "irrelevant",
      "signal_type": "other",
      "relevance_score": 10,
      "urgency": "low",
      "description": "Award announcement, not relevant for interim placement."
    }
  ]
}"""

OUTREACH_EMAIL = """{
  "subject": "A-Line x Taxfix: Interim CFO aus unserem Netzwerk",
  "body_html": "<p>Hi Max,</p><p>wir haben gesehen, dass Taxfix einen Interim CFO sucht.</p><p>Beste Gr\\u00fc\\u00dfe,\\nNiels</p>"
}"""

COMPANY_SYNTHESIS = """{
  "composite_score": 85,
  "arteq_fit": "high",
  "revenue_estimate": "EUR 20-30M",
  "summary": "Taxfix is a FinTech startup focused on automated tax filing. Recent Series C funding and rapid growth signal need for interim leadership.",
  "recommended_status": "prospect",
  "outreach_priority": 8,
  "dossier_html": "<h3>Company Dossier: Taxfix</h3><p>Summary...</p>"
}"""

DM_SCORING = """{
  "decision_maker_score": 90,
  "personal_hooks": ["Serial entrepreneur with fintech background", "Speaker at FinTech Summit 2025"]
}"""

ROLE_REQUIREMENTS = """{
  "required_function": "cfo",
  "required_skills": ["financial controlling", "fundraising", "m&a"],
  "seniority": "C-Level",
  "industry_preference": "FinTech",
  "location_requirement": "Germany",
  "engagement_type": "Interim",
  "key_challenges": ["Series C growth management", "IPO readiness"]
}"""

CANDIDATE_SCORING = """[
  {
    "candidate_id": "cand-001",
    "match_score": 85,
    "reasoning": "Strong CFO match with interim experience and FinTech background",
    "function_match": true,
    "location_match": true,
    "skills_overlap": ["fundraising", "m&a", "financial controlling"]
  }
]"""

SENTIMENT_INTERESTED = "interested"
SENTIMENT_NEGATIVE = "negative"
SENTIMENT_NEUTRAL = "neutral"

MEETING_BRIEFING = """{
  "briefing_html": "<h2>Meeting Briefing: Taxfix</h2><p>...</p>",
  "stakeholders": ["Max Mustermann - CEO - Serial Entrepreneur"],
  "hypotheses": ["Need interim CFO for IPO preparation"],
  "talking_points": ["How is the finance team structured?", "What is the timeline for the IPO?"],
  "red_flags": ["Large enterprise, may prefer permanent hire"]
}"""

PROPOSAL_DRAFT = """{
  "title": "Proposal: Interim CFO for Taxfix",
  "content_html": "<h2>Proposal: Taxfix</h2><p>...</p>",
  "executive_profile": {
    "title": "Interim CFO",
    "experience_years": "15+",
    "industry_focus": "FinTech",
    "key_skills": ["Fundraising", "Financial Controlling"]
  },
  "engagement_model": {
    "type": "interim",
    "days_per_week": "5",
    "estimated_duration": "6 Monate",
    "start_availability": "sofort"
  }
}"""
