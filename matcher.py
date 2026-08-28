import re
from datetime import datetime, date
from geo_distance import calculate_geo_proximity

def normalize_text(text):
    """Clean and standardize strings for matching."""
    if not text:
        return ""
    text = str(text).lower()
    text = re.sub(r'[^\w\s\+\#\.]', ' ', text)
    return text.strip()

def extract_skill_tokens(skill_str):
    """
    Extract individual skill keywords from comma/newline/slash separated strings.
    Handles common tech variations like react/reactjs, node/nodejs, etc.
    """
    if not skill_str:
        return set()
    
    raw = str(skill_str).lower()
    # Split on commas, semicolons, pipes, slashes, newlines, and bullet points
    parts = re.split(r'[,;|\/\n•\*\+\&]+', raw)
    tokens = set()
    
    for p in parts:
        cleaned = p.strip()
        if cleaned and len(cleaned) > 1:
            tokens.add(cleaned)
            # Add normalized aliases
            alias = re.sub(r'[\.\s\-_]', '', cleaned)
            if alias:
                tokens.add(alias)
                
    return tokens

def calculate_skill_match(job_skills_str, candidate_skills_str, candidate_other_text=""):
    """
    Calculates skills match score (0 to 40 points).
    Returns (score, matched_skills, missing_skills, match_ratio).
    """
    job_skills = extract_skill_tokens(job_skills_str)
    if not job_skills:
        return 40.0, [], [], 1.0  # If job specifies no required skills, default full score
    
    cand_skills = extract_skill_tokens(candidate_skills_str)
    cand_context = normalize_text(f"{candidate_skills_str} {candidate_other_text}")
    
    matched = []
    missing = []
    
    for js in job_skills:
        # Check direct token match or substring presence
        if js in cand_skills or js in cand_context:
            matched.append(js)
        else:
            # Check partial word containment (e.g. 'python' in 'python developer')
            if any(js in cs or cs in js for cs in cand_skills if len(cs) > 2):
                matched.append(js)
            else:
                missing.append(js)
                
    # Deduplicate while preserving order
    matched = list(dict.fromkeys(matched))
    missing = list(dict.fromkeys(missing))
    
    ratio = len(matched) / len(job_skills) if job_skills else 1.0
    score = min(40.0, ratio * 40.0)
    return round(score, 1), matched, missing, ratio

def calculate_experience_match(job_min_exp, job_max_exp, cand_years, cand_months=0):
    """
    Calculates experience match score (0 to 25 points).
    Returns (score, message).
    """
    try:
        j_min = float(job_min_exp or 0)
        j_max = float(job_max_exp or 0)
        if j_max < j_min and j_max > 0:
            j_min, j_max = j_max, j_min
    except (ValueError, TypeError):
        j_min, j_max = 0.0, 0.0
        
    try:
        c_exp = float(cand_years or 0) + (float(cand_months or 0) / 12.0)
    except (ValueError, TypeError):
        c_exp = 0.0
        
    # If no experience requirement specified on job
    if j_min == 0 and j_max == 0:
        return 25.0, f"{round(c_exp, 1)} Yrs (No specific exp required)"
        
    # If candidate fits perfectly in range
    if (j_max == 0 and c_exp >= j_min) or (j_min <= c_exp <= j_max):
        return 25.0, f"{round(c_exp, 1)} Yrs (Fits {j_min}-{j_max} Yrs)"
        
    # If candidate has slightly less exp (within 1.5 years of min)
    if c_exp < j_min:
        gap = j_min - c_exp
        if gap <= 1.0:
            return 18.0, f"{round(c_exp, 1)} Yrs (~1 Yr below min {j_min} Yrs)"
        elif gap <= 2.0:
            return 10.0, f"{round(c_exp, 1)} Yrs (~2 Yrs below min {j_min} Yrs)"
        else:
            return 0.0, f"{round(c_exp, 1)} Yrs (Below min {j_min} Yrs)"
            
    # If candidate is overqualified (exceeds max by reasonable amount)
    if j_max > 0 and c_exp > j_max:
        gap = c_exp - j_max
        if gap <= 2.0:
            return 22.0, f"{round(c_exp, 1)} Yrs (Slightly above max {j_max} Yrs)"
        elif gap <= 4.0:
            return 15.0, f"{round(c_exp, 1)} Yrs (Above max {j_max} Yrs)"
        else:
            return 8.0, f"{round(c_exp, 1)} Yrs (Significantly above {j_max} Yrs)"
            
    return 15.0, f"{round(c_exp, 1)} Yrs"

def calculate_budget_match(job_min_pay, job_max_pay, cand_expected_ctc, cand_current_ctc=None):
    """
    Calculates budget/CTC match score (0 to 20 points).
    Returns (score, message).
    """
    try:
        j_max = float(job_max_pay or 0)
        j_min = float(job_min_pay or 0)
    except (ValueError, TypeError):
        j_max, j_min = 0.0, 0.0
        
    try:
        c_exp = float(cand_expected_ctc or 0)
    except (ValueError, TypeError):
        c_exp = 0.0
        
    try:
        c_curr = float(cand_current_ctc or 0)
    except (ValueError, TypeError):
        c_curr = 0.0
        
    # If job has no budget specified or candidate has no CTC specified
    if j_max == 0 or c_exp == 0:
        return 20.0, "Budget Open / Not Specified"
        
    # Normalize if candidate entered in Lakhs (e.g., 12) while job is in full INR (e.g. 1200000) or vice versa
    if j_max > 1000 and c_exp < 100:
        c_exp_comp = c_exp * 100000
    elif j_max < 100 and c_exp > 1000:
        c_exp_comp = c_exp / 100000
    else:
        c_exp_comp = c_exp
        
    if j_min > 1000 and c_exp < 100:
        j_min_comp = j_min
    elif j_min < 100 and c_exp > 1000:
        j_min_comp = j_min * 100000
    else:
        j_min_comp = j_min

    # Exact budget fit (expected CTC <= job max pay)
    if c_exp_comp <= j_max:
        return 20.0, f"₹{cand_expected_ctc} (Within Budget)"
        
    # If expected CTC is slightly above budget (within 15%)
    over_ratio = (c_exp_comp - j_max) / j_max
    if over_ratio <= 0.15:
        return 14.0, f"₹{cand_expected_ctc} (~15% above budget)"
    elif over_ratio <= 0.30:
        return 7.0, f"₹{cand_expected_ctc} (~30% above budget)"
    else:
        return 0.0, f"₹{cand_expected_ctc} (Exceeds budget)"

def calculate_location_match(job_location, cand_location):
    """
    Computes geographic proximity score (0-15 pts) and distance using Haversine Geodesics.
    """
    score, msg, dist_km, tier = calculate_geo_proximity(job_location, cand_location)
    return score, msg

def parse_date_safely(date_val):
    if not date_val:
        return None
    if isinstance(date_val, date) and not isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, datetime):
        return date_val.date()
    try:
        clean_time = str(date_val).split(".")[0].split("+")[0].replace("Z", "").strip()
        if "T" in clean_time:
            return datetime.strptime(clean_time, "%Y-%m-%dT%H:%M:%S").date()
        elif " " in clean_time:
            return datetime.strptime(clean_time, "%Y-%m-%d %H:%M:%S").date()
        else:
            return datetime.strptime(clean_time, "%Y-%m-%d").date()
    except Exception:
        return None

def calculate_candidate_match(
    job,
    candidate,
    exp_min_override=None,
    exp_max_override=None,
    exp_leeway_years=0.0,
    budget_max_override=None,
    budget_stretch_pct=0.0,
    skills_boost="",
    **kwargs
):
    """
    Computes a comprehensive match percentage between a Job and a Candidate.
    Supports recruiter overrides, search extensions, and time-adjusted dynamic experience.
    
    Returns a dictionary with match breakdown, score components, and badges.
    """
    # 1. Skills Match (40 pts)
    base_job_skills = job.get("skills_required", "")
    if skills_boost and str(skills_boost).strip():
        job_skills = f"{base_job_skills}, {skills_boost}"
    else:
        job_skills = base_job_skills

    cand_skills = candidate.get("skills", "")
    cand_context = f"{candidate.get('current_designation', '')} {candidate.get('qualification', '')} {candidate.get('education_details', '')}"
    skill_score, matched_skills, missing_skills, skill_ratio = calculate_skill_match(job_skills, cand_skills, cand_context)
    
    # 2. Time-Adjusted Dynamic Experience (25 pts)
    record_date_str = candidate.get("created_on") or candidate.get("created_at")
    record_date = parse_date_safely(record_date_str)
    elapsed_years = 0.0
    if record_date:
        elapsed_days = (date.today() - record_date).days
        if elapsed_days > 180:
            elapsed_years = round(elapsed_days / 365.25, 1)

    cand_base_years = float(candidate.get("experience_years", 0) or 0)
    cand_base_months = float(candidate.get("experience_months", 0) or 0)
    base_total_exp = round(cand_base_years + (cand_base_months / 12.0), 1)
    dynamic_exp = round(base_total_exp + elapsed_years, 1)

    # Dynamic Age Calculation (Real-time from approx_dob or DOB)
    dob_str = candidate.get("approx_dob") or candidate.get("date_of_birth")
    dynamic_age = None
    if dob_str:
        cand_dob = parse_date_safely(dob_str)
        if cand_dob:
            today = date.today()
            dynamic_age = today.year - cand_dob.year - ((today.month, today.day) < (cand_dob.month, cand_dob.day))

    if dynamic_age is None:
        base_age = candidate.get("approx_age")
        if base_age:
            try:
                dynamic_age = int(round(float(base_age) + elapsed_years))
            except Exception:
                dynamic_age = int(round(22 + dynamic_exp))
        else:
            dynamic_age = int(round(22 + dynamic_exp))

    is_high_seniority = (dynamic_exp >= 38.0) or (dynamic_age >= 58)

    if exp_min_override is not None:
        job_min_exp = float(exp_min_override)
    else:
        job_min_exp = float(job.get("experience_min_year", 0) or 0)

    if exp_max_override is not None:
        job_max_exp = float(exp_max_override)
    else:
        job_max_exp = float(job.get("experience_max_year", 0) or 0)

    # Apply leeway buffer if configured (e.g. +/- 1, 2, 3 years)
    if exp_leeway_years > 0:
        job_min_exp = max(0.0, job_min_exp - exp_leeway_years)
        if job_max_exp > 0:
            job_max_exp = job_max_exp + exp_leeway_years

    exp_score, raw_exp_msg = calculate_experience_match(job_min_exp, job_max_exp, dynamic_exp, 0)
    if elapsed_years > 0:
        exp_msg = f"{dynamic_exp} Yrs ({base_total_exp} Yrs base + {elapsed_years} Yrs progression) | {raw_exp_msg}"
    else:
        exp_msg = f"{dynamic_exp} Yrs | {raw_exp_msg}"
    
    # 3. Budget / CTC Match (20 pts) with Stretch & Overrides
    job_min_pay = float(job.get("pay_min", 0) or 0)
    if budget_max_override is not None and float(budget_max_override) > 0:
        job_max_pay = float(budget_max_override)
    else:
        job_max_pay = float(job.get("pay_max", 0) or 0)

    # Apply percentage stretch if recruiter is open to extended budgets (e.g. +20%)
    if budget_stretch_pct > 0 and job_max_pay > 0:
        job_max_pay = job_max_pay * (1.0 + (budget_stretch_pct / 100.0))

    cand_expected = candidate.get("expected_ctc", 0)
    cand_current = candidate.get("current_ctc", 0)
    budget_score, budget_msg = calculate_budget_match(job_min_pay, job_max_pay, cand_expected, cand_current)
    
    # 4. Location Match (15 pts) with Haversine Geodesic Proximity
    job_loc = job.get("location", "")
    cand_loc = candidate.get("current_location", "")
    loc_score, loc_msg, dist_km, loc_tier = calculate_geo_proximity(job_loc, cand_loc)
    
    total_score = round(skill_score + exp_score + budget_score + loc_score, 1)
    total_pct = int(min(100, max(0, round(total_score))))
    
    # Tier classification
    if total_pct >= 80:
        badge_color = "#16A34A"  # Green
        match_tier = "Excellent Match"
    elif total_pct >= 65:
        badge_color = "#0284C7"  # Blue
        match_tier = "Good Match"
    elif total_pct >= 45:
        badge_color = "#EAB308"  # Yellow/Gold
        match_tier = "Moderate Match"
    else:
        badge_color = "#64748B"  # Slate Gray
        match_tier = "Low Match"
        
    return {
        "total_match_pct": total_pct,
        "skill_score": skill_score,
        "exp_score": exp_score,
        "budget_score": budget_score,
        "loc_score": loc_score,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "base_exp": base_total_exp,
        "elapsed_years": elapsed_years,
        "dynamic_exp": dynamic_exp,
        "approx_age": dynamic_age,
        "is_high_seniority": is_high_seniority,
        "exp_msg": exp_msg,
        "budget_msg": budget_msg,
        "loc_msg": loc_msg,
        "loc_dist_km": dist_km,
        "loc_tier": loc_tier,
        "badge_color": badge_color,
        "match_tier": match_tier
    }

def get_top_matched_candidates(
    job,
    candidates_list,
    limit=None,
    min_score=35,
    ranking_preference="Balanced",
    recency_years=None,
    include_inactive=False,
    **match_kwargs
):
    """
    Scores and ranks candidate records against a job with flexible parameters,
    automatic deactivation filtering, recency constraints, and preference sorting.
    """
    inactive_statuses = {"retired", "deceased", "blacklisted", "inactive", "inactive / left market"}
    scored = []

    for cand in candidates_list:
        # Exclude deactivated / deceased / blacklisted profiles unless include_inactive is explicitly requested
        c_status = (cand.get("candidate_status") or "").strip().lower()
        c_stage = (cand.get("current_stage") or "").strip().lower()
        is_inact = c_status in inactive_statuses or c_stage in inactive_statuses
        if is_inact and not include_inactive:
            continue

        match_res = calculate_candidate_match(job, cand, **match_kwargs)
        
        # Apply recency filter if requested
        if recency_years is not None and recency_years > 0:
            if match_res["elapsed_years"] > recency_years:
                continue

        if match_res["total_match_pct"] >= min_score:
            scored.append({
                "candidate": cand,
                "match": match_res
            })
            
    # Apply Ranking Preference Sort
    pref = str(ranking_preference).lower()
    if "young" in pref or "growth" in pref or "fast-track" in pref:
        scored.sort(
            key=lambda x: (
                round(x["match"]["total_match_pct"] - (0.8 * min(25.0, max(0.0, x["match"]["approx_age"] - 22))), 1),
                -x["match"]["approx_age"],
                x["match"]["skill_score"]
            ),
            reverse=True
        )
    elif "senior" in pref or "veteran" in pref or "leadership" in pref:
        scored.sort(
            key=lambda x: (
                round(x["match"]["total_match_pct"] + (0.6 * min(25.0, max(0.0, x["match"]["approx_age"] - 25))), 1),
                x["match"]["approx_age"],
                x["match"]["skill_score"]
            ),
            reverse=True
        )
    else:
        scored.sort(
            key=lambda x: (x["match"]["total_match_pct"], x["match"]["skill_score"]),
            reverse=True
        )
    
    if limit is not None and limit > 0:
        return scored[:limit]
    return scored
