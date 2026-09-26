import re
import os
import streamlit as st
from db import supabase
from datetime import datetime, date
from matcher import extract_skill_tokens, normalize_text, calculate_experience_match, calculate_budget_match, parse_date_safely
from geo_distance import calculate_geo_proximity
from common import get_unified_candidate_pool

def get_all_candidates_pool():
    """
    Delegates to the unified, shared candidate pool in common.py.
    Eliminates duplicated in-memory fetches and synchronizes cache.
    """
    return get_unified_candidate_pool()

# Common Indian cities & states for location detection in queries
LOCATIONS_LOOKUP = [
    "hyderabad", "secunderabad", "warangal", "telangana", "andhra pradesh", "andhra",
    "vijayawada", "guntur", "visakhapatnam", "vizag", "tirupati", "kurnool", "nizamabad",
    "khammam", "karimnagar", "mahabubnagar", "bengaluru", "bangalore", "karnataka", "mysore",
    "mumbai", "pune", "maharashtra", "nagpur", "nashik", "aurangabad", "thane",
    "delhi", "new delhi", "delhi ncr", "noida", "gurgaon", "gurugram", "faridabad", "ghaziabad",
    "chennai", "tamil nadu", "coimbatore", "madurai", "kolkata", "west bengal",
    "ahmedabad", "gujarat", "surat", "vadodara", "rajkot", "indore", "bhopal", "madhya pradesh",
    "jaipur", "rajasthan", "lucknow", "kanpur", "uttar pradesh", "patna", "bihar", "chandigarh", "punjab"
]

def parse_natural_language_query(query_text):
    """
    Parses natural language recruiter prompts into structured query filters:
    - skills_keywords (list of strings)
    - exp_min (float or None)
    - exp_max (float or None)
    - target_location (str or None)
    - budget_max (float or None in LPA)
    - raw_query (str)
    """
    if not query_text or not str(query_text).strip():
        return {
            "skills_keywords": [],
            "exp_min": None,
            "exp_max": None,
            "target_location": None,
            "budget_max": None,
            "raw_query": ""
        }

    raw = str(query_text).strip()
    lower_query = raw.lower()

    # 1. Extract Experience Range (e.g. "5+ yrs", "3 to 7 years", "min 4 yrs", "fresher")
    exp_min = None
    exp_max = None

    if "fresher" in lower_query or "0 year" in lower_query or "entry level" in lower_query:
        exp_min = 0.0
        exp_max = 1.5
    else:
        # Pattern: "3 to 6 yrs", "3-6 years", "3 - 6 yrs"
        range_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*(?:yrs?|years?|year)', lower_query)
        if range_match:
            exp_min = float(range_match.group(1))
            exp_max = float(range_match.group(2))
        else:
            # Pattern: "5+ yrs", "5+ years", "at least 5 yrs", "min 5 yrs", "more than 5 yrs"
            plus_match = re.search(r'(?:min(?:imum)?|at least|more than|>)?\s*(\d+(?:\.\d+)?)\s*(?:\+|plus)\s*(?:yrs?|years?)?', lower_query)
            if plus_match:
                exp_min = float(plus_match.group(1))
                exp_max = exp_min + 5.0
            else:
                # Pattern: "5 yrs", "5 years experience"
                single_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:yrs?|years?|yr)', lower_query)
                if single_match:
                    val = float(single_match.group(1))
                    exp_min = max(0.0, val - 1.5)
                    exp_max = val + 2.5

    # 2. Extract Budget / CTC (e.g. "under 8 LPA", "under 8 lakhs", "upto 12 lacs", "6-10 LPA", "8LPA")
    budget_max = None
    # Pattern: "under 8 LPA", "upto 10 lacs", "max 12 lakh", "< 10 LPA"
    budget_match = re.search(r'(?:under|upto|up to|max(?:imum)?|below|<|within)?\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?|lacs?|lac|l)', lower_query)
    if budget_match:
        val = float(budget_match.group(1))
        # Ensure it's not the experience number (if > 30, it might be full figure like 800000)
        if val <= 100:
            budget_max = val

    # 3. Extract Location
    target_location = None
    for loc in LOCATIONS_LOOKUP:
        # Match whole word
        if re.search(r'\b' + re.escape(loc) + r'\b', lower_query):
            target_location = loc.title()
            break

    # 4. Extract Skills / Keywords
    # Clean out parsed numbers and stop words from the query
    cleaned_query = lower_query
    # Remove experience and budget fragments
    cleaned_query = re.sub(r'\b\d+(?:\.\d+)?\s*(?:to|-)?\s*\d*(?:\.\d+)?\s*(?:yrs?|years?|year|\+|plus)\b', ' ', cleaned_query)
    cleaned_query = re.sub(r'\b(?:under|upto|up to|max|below|<|within)?\s*\d+(?:\.\d+)?\s*(?:lpa|lakhs?|lacs?|lac|l)\b', ' ', cleaned_query)
    if target_location:
        cleaned_query = re.sub(r'\b' + re.escape(target_location.lower()) + r'\b', ' ', cleaned_query)

    # Remove standard recruiter filler words
    stop_words = {
        "find", "me", "a", "an", "the", "with", "having", "looking", "for", "in", "at", "who",
        "knows", "experience", "candidate", "candidates", "profile", "profiles", "resume", "resumes",
        "and", "or", "to", "from", "based", "around", "near", "required", "good", "strong", "expert",
        "level", "years", "year", "yrs", "yr", "under", "max", "min", "lpa", "lakhs", "lacs"
    }

    tokens = [t.strip() for t in re.split(r'[,;|\/\s+]+', cleaned_query) if t.strip() and len(t.strip()) > 1]
    skill_keywords = [t for t in tokens if t not in stop_words]

    return {
        "skills_keywords": skill_keywords,
        "exp_min": exp_min,
        "exp_max": exp_max,
        "target_location": target_location,
        "budget_max": budget_max,
        "raw_query": raw
    }

def search_candidates_semantic(query_text, candidate_pool, min_score=30, limit=50, ranking_preference="Balanced"):
    """
    Executes an AI Semantic query against candidate records with dynamic time-adjusted experience
    and ranking preference sorting.
    """
    params = parse_natural_language_query(query_text)
    skills = params["skills_keywords"]
    exp_min = params["exp_min"]
    exp_max = params["exp_max"]
    target_loc = params["target_location"]
    budget_max = params["budget_max"]

    if not skills and exp_min is None and not target_loc and budget_max is None:
        keywords = [w.lower() for w in query_text.split() if len(w) > 2]
    else:
        keywords = skills

    results = []

    # Pre-filtering optimization: skip profiles grossly out of range before heavy text/geo calculations
    filtered_pool = candidate_pool
    if exp_min is not None and exp_min > 2.0:
        filtered_pool = [
            c for c in filtered_pool
            if (float(c.get("experience_years", 0) or 0) + 2.5) >= exp_min
        ]
    if budget_max is not None and budget_max > 0:
        max_ctc_cap = budget_max * 100000 * 2.5 if budget_max < 100 else budget_max * 2.5
        filtered_pool = [
            c for c in filtered_pool
            if float(c.get("expected_ctc", 0) or 0) <= max_ctc_cap
        ]

    for c in filtered_pool:
        reasons = []
        score = 0.0

        # 1. Skill / Keyword Match (up to 45 pts)
        cand_text = normalize_text(f"{c.get('first_name', '')} {c.get('last_name', '')} {c.get('current_designation', '')} {c.get('current_company', '')} {c.get('skills', '')} {c.get('qualification', '')} {c.get('education_details', '')} {c.get('resume_name', '')}")
        cand_skills = extract_skill_tokens(c.get("skills", ""))

        if keywords:
            matched_kw = []
            for kw in keywords:
                if kw in cand_skills or kw in cand_text:
                    matched_kw.append(kw)
                elif any(kw in cs or cs in kw for cs in cand_skills if len(cs) > 2):
                    matched_kw.append(kw)
            
            kw_ratio = len(matched_kw) / len(keywords)
            skill_pts = kw_ratio * 45.0
            score += skill_pts
            if matched_kw:
                reasons.append(f"🛠️ Matched keywords: {', '.join(matched_kw)}")
        else:
            score += 35.0

        # 2. Time-Adjusted Dynamic Experience Match (up to 25 pts)
        record_date_str = c.get("created_on") or c.get("created_at")
        record_date = parse_date_safely(record_date_str)
        elapsed_years = 0.0
        if record_date:
            elapsed_days = (date.today() - record_date).days
            if elapsed_days > 180:
                elapsed_years = round(elapsed_days / 365.25, 1)

        cand_base_years = float(c.get("experience_years", 0) or 0)
        cand_base_months = float(c.get("experience_months", 0) or 0)
        base_total_exp = round(cand_base_years + (cand_base_months / 12.0), 1)
        dynamic_exp = round(base_total_exp + elapsed_years, 1)

        if exp_min is not None:
            e_min = float(exp_min)
            e_max = float(exp_max) if exp_max is not None else (e_min + 5.0)
            exp_score, raw_exp_msg = calculate_experience_match(e_min, e_max, dynamic_exp, 0)
            score += exp_score
            if elapsed_years > 0:
                reasons.append(f"⏳ Exp: {dynamic_exp} Yrs ({base_total_exp} base + {elapsed_years} Yrs career progression) | {raw_exp_msg}")
            else:
                reasons.append(f"⏳ Exp: {dynamic_exp} Yrs | {raw_exp_msg}")
        else:
            score += 20.0

        # 3. Location Match (up to 15 pts) with Geographic Proximity
        cand_loc = c.get("current_location", "")
        if target_loc:
            loc_score, loc_msg, dist_km, loc_tier = calculate_geo_proximity(target_loc, cand_loc)
            score += loc_score
            reasons.append(f"📍 Location: {loc_msg}")
        else:
            score += 15.0

        # 4. Budget / CTC Match (up to 15 pts)
        cand_ctc = float(c.get("expected_ctc", 0) or 0)
        if budget_max is not None and budget_max > 0:
            bud_score, bud_msg = calculate_budget_match(0, budget_max, cand_ctc)
            score += (bud_score * 0.75)
            reasons.append(f"💰 CTC: {bud_msg}")
        else:
            score += 15.0

        final_pct = int(min(100, max(0, round(score))))

        if final_pct >= min_score:
            if final_pct >= 80:
                tier = "Excellent Fit"
                badge_color = "#16A34A"
            elif final_pct >= 65:
                tier = "Good Fit"
                badge_color = "#0284C7"
            elif final_pct >= 45:
                tier = "Moderate Fit"
                badge_color = "#EAB308"
            else:
                tier = "Potential Fit"
                badge_color = "#64748B"

            results.append({
                "candidate": c,
                "score": final_pct,
                "tier": tier,
                "badge_color": badge_color,
                "reasons": reasons,
                "dynamic_exp": dynamic_exp,
                "parsed_params": params
            })

    # Ranking Preference Sort
    pref = str(ranking_preference).lower()
    if "young" in pref or "growth" in pref or "fast-track" in pref:
        results.sort(key=lambda x: (x["score"], -x["dynamic_exp"]), reverse=True)
    elif "senior" in pref or "veteran" in pref:
        results.sort(key=lambda x: (x["score"], x["dynamic_exp"]), reverse=True)
    else:
        results.sort(key=lambda x: x["score"], reverse=True)

    if limit is not None and limit > 0:
        return results[:limit], params
    return results, params
