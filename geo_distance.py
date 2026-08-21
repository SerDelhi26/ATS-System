import math
import re

# Comprehensive Coordinate Index for Indian Metros, Cities, and Districts
# Format: (Latitude, Longitude, State)
INDIAN_CITIES_COORDS = {
    # Odisha
    "bhubaneswar": (20.2961, 85.8245, "Odisha"),
    "cuttack": (20.4625, 85.8828, "Odisha"),
    "rourkela": (22.2604, 84.8536, "Odisha"),
    "berhampur": (19.3150, 84.7941, "Odisha"),
    "sambalpur": (21.4669, 83.9812, "Odisha"),
    "puri": (19.8135, 85.8312, "Odisha"),
    "balasore": (21.4934, 86.9135, "Odisha"),
    "bhadrak": (21.0543, 86.4955, "Odisha"),
    "angul": (20.8407, 85.1011, "Odisha"),
    "jharsuguda": (21.8554, 84.0062, "Odisha"),

    # Telangana & Andhra Pradesh
    "hyderabad": (17.3850, 78.4867, "Telangana"),
    "secunderabad": (17.4399, 78.4983, "Telangana"),
    "warangal": (17.9689, 79.5941, "Telangana"),
    "karimnagar": (18.4386, 79.1288, "Telangana"),
    "nizamabad": (18.6725, 78.0941, "Telangana"),
    "khammam": (17.2473, 80.1514, "Telangana"),
    "mahbubnagar": (16.7488, 77.9864, "Telangana"),
    "visakhapatnam": (17.6868, 83.2185, "Andhra Pradesh"),
    "vizag": (17.6868, 83.2185, "Andhra Pradesh"),
    "vijayawada": (16.5062, 80.6480, "Andhra Pradesh"),
    "guntur": (16.3067, 80.4365, "Andhra Pradesh"),
    "tirupati": (13.6288, 79.4192, "Andhra Pradesh"),
    "nellore": (14.4426, 79.9865, "Andhra Pradesh"),
    "kurnool": (15.8281, 78.0373, "Andhra Pradesh"),
    "kakinada": (16.9891, 82.2475, "Andhra Pradesh"),
    "rajahmundry": (17.0005, 81.8040, "Andhra Pradesh"),

    # Delhi NCR & North India
    "delhi": (28.7041, 77.1025, "Delhi NCR"),
    "new delhi": (28.6139, 77.2090, "Delhi NCR"),
    "noida": (28.5355, 77.3910, "Delhi NCR"),
    "greater noida": (28.4744, 77.5040, "Delhi NCR"),
    "gurgaon": (28.4595, 77.0266, "Delhi NCR"),
    "gurugram": (28.4595, 77.0266, "Delhi NCR"),
    "faridabad": (28.4089, 77.3178, "Delhi NCR"),
    "ghaziabad": (28.6692, 77.4538, "Delhi NCR"),
    "chandigarh": (30.7333, 76.7794, "Punjab/Haryana"),
    "mohali": (30.7046, 76.7179, "Punjab"),
    "panchkula": (30.6942, 76.8606, "Haryana"),
    "ludhiana": (30.9010, 75.8573, "Punjab"),
    "amritsar": (31.6340, 74.8723, "Punjab"),
    "jalandhar": (31.3260, 75.5762, "Punjab"),
    "dehradun": (30.3165, 78.0322, "Uttarakhand"),
    "jaipur": (26.9124, 75.7873, "Rajasthan"),
    "jodhpur": (26.2389, 73.0243, "Rajasthan"),
    "udaipur": (24.5854, 73.7125, "Rajasthan"),
    "kota": (25.2138, 75.8648, "Rajasthan"),
    "lucknow": (26.8467, 80.9462, "Uttar Pradesh"),
    "kanpur": (26.4499, 80.3319, "Uttar Pradesh"),
    "varanasi": (25.3176, 82.9739, "Uttar Pradesh"),
    "agra": (27.1767, 78.0081, "Uttar Pradesh"),
    "prayagraj": (25.4358, 81.8463, "Uttar Pradesh"),
    "allahabad": (25.4358, 81.8463, "Uttar Pradesh"),
    "meerut": (28.9845, 77.7064, "Uttar Pradesh"),

    # Maharashtra & West India
    "mumbai": (19.0760, 72.8777, "Maharashtra"),
    "navi mumbai": (19.0330, 73.0297, "Maharashtra"),
    "thane": (19.2183, 72.9781, "Maharashtra"),
    "pune": (18.5204, 73.8567, "Maharashtra"),
    "pcmc": (18.6279, 73.8131, "Maharashtra"),
    "nagpur": (21.1458, 79.0882, "Maharashtra"),
    "nashik": (19.9975, 73.7898, "Maharashtra"),
    "aurangabad": (19.8762, 75.3433, "Maharashtra"),
    "chhatrapati sambhajinagar": (19.8762, 75.3433, "Maharashtra"),
    "kolhapur": (16.7050, 74.2433, "Maharashtra"),
    "solapur": (17.6599, 75.9064, "Maharashtra"),
    "ahmedabad": (23.0225, 72.5714, "Gujarat"),
    "gandhinagar": (23.2156, 72.6369, "Gujarat"),
    "surat": (21.1702, 72.8311, "Gujarat"),
    "vadodara": (22.3072, 73.1812, "Gujarat"),
    "rajkot": (22.3039, 70.8022, "Gujarat"),
    "bhavnagar": (21.7645, 72.1519, "Gujarat"),
    "goa": (15.2993, 74.1240, "Goa"),
    "panaji": (15.4909, 73.8278, "Goa"),

    # Karnataka, Tamil Nadu & South India
    "bengaluru": (12.9716, 77.5946, "Karnataka"),
    "bangalore": (12.9716, 77.5946, "Karnataka"),
    "mysuru": (12.2958, 76.6394, "Karnataka"),
    "mysore": (12.2958, 76.6394, "Karnataka"),
    "hubli": (15.3647, 75.1240, "Karnataka"),
    "dharwad": (15.4589, 75.0078, "Karnataka"),
    "mangalore": (12.9141, 74.8560, "Karnataka"),
    "mangaluru": (12.9141, 74.8560, "Karnataka"),
    "belgaum": (15.8497, 74.4977, "Karnataka"),
    "chennai": (13.0827, 80.2707, "Tamil Nadu"),
    "madras": (13.0827, 80.2707, "Tamil Nadu"),
    "coimbatore": (11.0168, 76.9558, "Tamil Nadu"),
    "madurai": (9.9252, 78.1198, "Tamil Nadu"),
    "trichy": (10.7905, 78.7047, "Tamil Nadu"),
    "tiruchirappalli": (10.7905, 78.7047, "Tamil Nadu"),
    "salem": (11.6643, 78.1460, "Tamil Nadu"),
    "kochi": (9.9312, 76.2673, "Kerala"),
    "cochin": (9.9312, 76.2673, "Kerala"),
    "thiruvananthapuram": (8.5241, 76.9366, "Kerala"),
    "trivandrum": (8.5241, 76.9366, "Kerala"),
    "calicut": (11.2588, 75.7804, "Kerala"),
    "kozhikode": (11.2588, 75.7804, "Kerala"),

    # East & Central India
    "kolkata": (22.5726, 88.3639, "West Bengal"),
    "calcutta": (22.5726, 88.3639, "West Bengal"),
    "howrah": (22.5958, 88.2636, "West Bengal"),
    "siliguri": (26.7271, 88.3953, "West Bengal"),
    "durgapur": (23.5204, 87.3119, "West Bengal"),
    "asansol": (23.6739, 86.9524, "West Bengal"),
    "patna": (25.5941, 85.1376, "Bihar"),
    "gaya": (24.7914, 85.0002, "Bihar"),
    "muzaffarpur": (26.1209, 85.3647, "Bihar"),
    "ranchi": (23.3441, 85.3096, "Jharkhand"),
    "jamshedpur": (22.8046, 86.2029, "Jharkhand"),
    "dhanbad": (23.7957, 86.4304, "Jharkhand"),
    "indore": (22.7196, 75.8577, "Madhya Pradesh"),
    "bhopal": (23.2599, 77.4126, "Madhya Pradesh"),
    "jabalpur": (23.1815, 79.9864, "Madhya Pradesh"),
    "gwalior": (26.2183, 78.1828, "Madhya Pradesh"),
    "raipur": (21.2514, 81.6296, "Chhattisgarh"),
    "bilaspur": (22.0797, 82.1409, "Chhattisgarh"),
    "guwahati": (26.1445, 91.7362, "Assam")
}

# Alias / Short-form Normalizer
LOCATION_ALIASES = {
    "bbsr": "bhubaneswar",
    "ctc": "cuttack",
    "hyd": "hyderabad",
    "secunderabad": "secunderabad",
    "cyb": "hyderabad",
    "cyberabad": "hyderabad",
    "blr": "bengaluru",
    "bangalore": "bengaluru",
    "bengaluru": "bengaluru",
    "bom": "mumbai",
    "bombay": "mumbai",
    "delhi ncr": "delhi",
    "ncr": "delhi",
    "ggn": "gurugram",
    "ggm": "gurugram",
    "gurgaon": "gurugram",
    "gurugram": "gurugram",
    "maa": "chennai",
    "madras": "chennai",
    "ccu": "kolkata",
    "calcutta": "kolkata",
    "pnq": "pune",
    "vizag": "visakhapatnam",
    "cochin": "kochi",
    "trivandrum": "thiruvananthapuram"
}

def normalize_loc_string(loc_str):
    """Cleans location string and maps aliases."""
    if not loc_str:
        return ""
    clean = str(loc_str).lower().strip()
    clean = re.sub(r'[,\.\-\/\(\)]', ' ', clean)
    words = clean.split()
    
    for word in words:
        if word in LOCATION_ALIASES:
            return LOCATION_ALIASES[word]
            
    for alias, standard in LOCATION_ALIASES.items():
        if alias in clean:
            return standard
            
    return clean

def extract_best_city_coords(loc_text):
    """Finds matching city entry in INDIAN_CITIES_COORDS."""
    if not loc_text:
        return None, None
        
    norm = normalize_loc_string(loc_text)
    
    if norm in INDIAN_CITIES_COORDS:
        return norm, INDIAN_CITIES_COORDS[norm]
        
    for city, data in INDIAN_CITIES_COORDS.items():
        if city in norm or norm in city:
            return city, data
            
    for token in norm.split():
        if token in INDIAN_CITIES_COORDS:
            return token, INDIAN_CITIES_COORDS[token]
        if token in LOCATION_ALIASES:
            std = LOCATION_ALIASES[token]
            if std in INDIAN_CITIES_COORDS:
                return std, INDIAN_CITIES_COORDS[std]
                
    return None, None

def calculate_haversine_distance(coord1, coord2):
    """Calculates great-circle distance in kilometers."""
    lat1, lon1 = coord1[0], coord1[1]
    lat2, lon2 = coord2[0], coord2[1]
    
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    distance_km = R * c
    return round(distance_km, 1)

def calculate_geo_proximity(job_location, candidate_location):
    """
    Computes distance-tiered geographic proximity score (0.0 to 15.0 pts).
    """
    if not job_location or not candidate_location:
        return 5.0, f"{candidate_location or 'N/A'} (Location Unspecified)", None, "Unspecified"
        
    j_raw = str(job_location).lower().strip()
    c_raw = str(candidate_location).lower().strip()
    
    flexible_terms = ["remote", "work from home", "wfh", "any", "pan india", "flexible", "all india", "hybrid"]
    if any(term in j_raw or term in c_raw for term in flexible_terms):
        return 15.0, f"{candidate_location} (🌐 Remote / Pan-India Flexible)", 0.0, "Remote / Flexible"
        
    j_city, j_data = extract_best_city_coords(job_location)
    c_city, c_data = extract_best_city_coords(candidate_location)
    
    if j_data and c_data:
        distance_km = calculate_haversine_distance((j_data[0], j_data[1]), (c_data[0], c_data[1]))
        j_state = j_data[2]
        c_state = c_data[2]
        
        # Tier 1: 0 - 35 km (Same City / Metro / Direct Commute)
        if distance_km <= 35:
            return 15.0, f"📍 {candidate_location} (Same Metro - {int(distance_km)} km)", distance_km, "Same City / Metro"
            
        # Tier 2: 35 - 150 km (Nearby District / Commutable Region)
        elif distance_km <= 150:
            return 12.0, f"🚗 {candidate_location} (Nearby District ~{int(distance_km)} km from {j_city.title()})", distance_km, "Nearby District"
            
        # Tier 3: 150 - 450 km (Same State / Regional Hub)
        elif distance_km <= 450 or j_state == c_state:
            return 8.0, f"🚆 {candidate_location} (Regional State ~{int(distance_km)} km)", distance_km, "Regional State"
            
        # Tier 4: 450+ km (Relocation Required / Outstation)
        else:
            return 3.0, f"🗺️ {candidate_location} (Relocation Required ~{int(distance_km)} km)", distance_km, "Relocation Required"
            
    if j_raw in c_raw or c_raw in j_raw:
        return 15.0, f"📍 {candidate_location} (Exact Match)", 0.0, "Same City / Metro"
        
    return 3.0, f"🗺️ {candidate_location} (Different Region)", None, "Different Region"
