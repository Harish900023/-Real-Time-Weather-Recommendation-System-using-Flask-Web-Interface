from flask import Flask, request, jsonify, render_template, send_from_directory
import json
import requests
import os
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import time

app = Flask(__name__)

API_KEY = "aadcc496e340e8dc5354c34c33272ed2"
GEMINI_API_KEY = "AIzaSyBBPPH12Aq9cCBdHTiR7ECv4T1ZqiYcgAI"
ELEVENLABS_API_KEY = "sk_b226370e39fe817bc2d7d635b64addd6565fb1878f4f692e"
SARVAM_API_KEY = "sk_wykv4bxb_9sbzNyXh1VDJBvxQPJyhRHpA"
VOICE_ID = "21m00Tcm4TlvDq8ikWAM" # Rachel (better multilingual)

# -------------------------------
# AI MODEL (UPGRADED: Risk Score Probability)
# Features: [Temp, Humidity, Wind, Pressure, RainProb]
# -------------------------------
X = np.array([
    [40, 70, 5, 1010, 10], # High Heat
    [10, 50, 2, 1020, 0],  # Cold Clear
    [25, 60, 3, 1015, 20], # Neutral
    [35, 90, 12, 1005, 80],# Extreme Risk (Storm)
    [20, 40, 2, 1018, 5]   # Perfect
])
y = np.array([1, 2, 2, 0, 2]) # 2: Stable, 1: Caution, 0: High Risk

model = RandomForestClassifier(n_estimators=100)
model.fit(X, y)

# Ensure static directory exists for audio files
if not os.path.exists('static'):
    os.makedirs('static')

# -------------------------------
# WEATHER FUNCTION
# -------------------------------
def get_weather(city, api_key):
    try:
        # Use HTTPS to prevent connection timeouts on port 80
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
        res = requests.get(url, timeout=15) # Increased timeout for stability
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"WEATHER API ERROR for city '{city}':", e)
        return {"error": "API failed to connect"}

# -------------------------------
# TELEGRAM & HELPERS
# -------------------------------
def get_uv_index(lat, lon, api_key):
    try:
        url = f"https://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={api_key}"
        res = requests.get(url, timeout=10)
        # Simplified: Use components or similar if UV direct isn't available on free tier easily
        return res.json().get('list', [{}])[0].get('main', {}).get('aqi', 1) 
    except: return 1

def optimize_telugu(text):
    # --- Speech-Friendly Splitting ---
    text = text.replace("ఈరోజు", "ఈ రోజు")
    text = text.replace("మంచినీళ్లు", "మంచి నీళ్లు")
    
    # Common suffix splitting (helps cadence)
    text = text.replace("లో", " లో") 
    text = text.replace("తో", " తో")
    
    # Add natural pauses for Telugu
    text = text.replace("\n", " ... ")
    text = text.replace(".", " ... ")
    text = text.replace(",", " , ")
    
    # Pronunciation Hints for symbols
    text = text.replace("°C", " డిగ్రీలు సెల్సియస్ ")
    text = text.replace("%", " శాతం ")

    # Ensure spacing
    text = " ".join(text.split())
    return text

def sarvam_telugu_fix(text):
    # Break compound words (VERY IMPORTANT for native synthesis)
    text = text.replace("ఈరోజు", "ఈ రోజు")
    text = text.replace("విజయవాడలో", "విజయవాడ లో")
    text = text.replace("మంచినీళ్లు", "మంచి నీళ్లు")
    text = text.replace("తప్పించుకోవడానికి", "తప్పించుకోవడానికి")

    # Convert to spoken Telugu (simplify vocabulary for phonetic clarity)
    text = text.replace("ఉష్ణోగ్రత", "వేడి")
    text = text.replace("పరిస్థితులు", "స్థితి")

    # Remove English characters completely (regex)
    import re
    text = re.sub(r'[A-Za-z]', '', text)

    # Clean redundant spacing
    text = " ".join(text.split())
    return text

def telugu_to_phonetic(text):
    # Mapping for common weather/interface terms to trick English voices
    mapping = {
        "వాతావరణం": "vaathavaranam",
        "ఉష్ణోగ్రత": "ushnogratha",
        "చాలా": "chaala",
        "మంచిగా": "manchiga",
        "ఉంది": "undi",
        "ఈ రోజు": "ee roju",
        "తేమ": "tema",
        "గాలి": "gaali",
        "శాతం": "shatham",
        "వర్షం": "varsham",
        "ఎండ": "enda",
        "చలి": "chali",
        "మేఘాలు": "meghalu",
        "రేపు": "repu",
        "ఎల్లుండి": "ellundi",
        "జాగ్రత్త": "jagratta",
        "క్షేమం": "kshemam",
        "ప్రమాదం": "pramadam",
        "నీళ్లు": "neellu",
        "బయటికి": "bayatiki",
        "వెళ్లేటప్పుడు": "velletappudu"
    }

    # First optimize pauses/symbols
    text = optimize_telugu(text)

    # Convert to phonetics
    for tel, eng in mapping.items():
        text = text.replace(tel, eng)
    
    # Andhra accent tricks (aa -> aah, oo -> ooh)
    text = text.replace("aa", "aah").replace("oo", "ooh")
    
    # Remove any remaining Telugu characters for pure phonetic flow to English voice
    import re
    text = re.sub(r'[\u0c00-\u0c7f]+', '', text)
    
    # Clear redundant dots
    text = " ".join(text.split())
    return text

def send_telegram(token, chatid, msg):
    if not token or not chatid:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={"chat_id": chatid, "text": msg})
    except Exception as e:
        print("Telegram Error:", e)

def generate_sarvam_voice(text, lang):
    if not SARVAM_API_KEY:
        return None
    try:
        url = "https://api.sarvam.ai/text-to-speech"
        headers = {
            "api-subscription-key": SARVAM_API_KEY, # Sarvam often uses this header or Bearer
            "Content-Type": "application/json"
        }
        
        # Mapping for Sarvam locales
        sarvam_lang = "te-IN" if lang == "te" else "hi-IN"
        
        # Apply Exact Telugu Fix (Spoken Normalization)
        if lang == "te":
            text = sarvam_telugu_fix(text)
        else:
            text = text.replace(" ... ", " ").replace(" , ", " ")

        data = {
            "inputs": [text],
            "target_language_code": sarvam_lang,
            "speaker": "arya", # Upgraded to 'arya' for natural Telugu cadence
            "model": "bulbul:v3",
            "speech_sample_rate": 22050,
            "enable_preprocessing": False # Disabled to prevent incorrect syllable merging/compression
        }

        response = requests.post(url, json=data, headers=headers, timeout=20)
        response.raise_for_status()
        
        result = response.json()
        audio_base64 = result.get('audios', [None])[0]
        
        if not audio_base64:
            return None

        import base64
        audio_data = base64.b64decode(audio_base64)
        
        file_name = f"sarvam_{lang}_{int(time.time())}.wav"
        file_path = os.path.join('static', file_name)
        
        with open(file_path, "wb") as f:
            f.write(audio_data)
            
        return f"/static/{file_name}"
    except Exception as e:
        print(f"Sarvam AI Error ({lang}):", e)
        return None

def generate_voice(text, lang='en'):
    # Detect language type for routing
    is_indian = lang in ['te', 'hi']
    
    if is_indian:
        # Re-clean for pure script (Sarvam prefers native characters)
        clean_text = optimize_telugu(text) if lang == 'te' else text
        return generate_sarvam_voice(clean_text, lang)
    
    # Else use ElevenLabs for English
    if not ELEVENLABS_API_KEY:
        return None
    try:
        # --- Speech Formatting Layer (Natural Pauses for AI) ---
        clean_text = text.replace('\n', '. ').replace(',', ', ').replace(' and ', ' ... and ')
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        data = {
            "text": f"<speak><prosody rate='medium'>{clean_text}</prosody></speak>",
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.4,
                "similarity_boost": 0.8
            }
        }
        response = requests.post(url, json=data, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Unique mapping to avoid overlaps
        file_name = f"voice_{int(time.time())}.mp3"
        file_path = os.path.join('static', file_name)
        
        with open(file_path, "wb") as f:
            f.write(response.content)
            
        return f"/static/{file_name}" # Return web-accessible path
    except Exception as e:
        print("ElevenLabs Error:", e)
        return None

# -------------------------------
# RESPONSE CACHE
# -------------------------------
chat_cache = {}

# -------------------------------
# ROUTES
# -------------------------------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/templates/<path:filename>')
def serve_static(filename):
    return send_from_directory('templates', filename)

@app.route('/weather')
def weather():
    city = request.args.get('city')
    user_type = request.args.get('user_type', 'general')
    lang = request.args.get('lang', 'en')
    telegram_token = request.args.get('telegram_token', '')
    telegram_chatid = request.args.get('telegram_chatid', '')
    user_api_key = request.args.get('api_key', '')

    # Prioritize user key, fallback to system key
    active_weather_key = user_api_key if user_api_key else API_KEY
    data = get_weather(city, active_weather_key)
    print("Weather API Fetch for:", city)

    if 'main' not in data:
        return jsonify({"error": data.get("message", "API error - Location not found")})

    # Handles missing or incorrect values safely
    temp = data.get('main', {}).get('temp', 0)
    hum = data.get('main', {}).get('humidity', 0)
    wind = data.get('wind', {}).get('speed', 0)
    
    weather_desc = data['weather'][0]['description']
    pressure = data.get('main', {}).get('pressure', 1013)
    rain_prob = data.get('clouds', {}).get('all', 0) # Cloud cover as rain proxy for sample
    lat = data.get('coord', {}).get('lat', 0)
    lon = data.get('coord', {}).get('lon', 0)

    # Fetch Air Quality Index (AQI)
    aqi = 1
    pm25 = 0
    try:
        aqi_url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={active_weather_key}"
        aqi_res = requests.get(aqi_url, timeout=5)
        if aqi_res.status_code == 200:
            aqi_data = aqi_res.json()
            if 'list' in aqi_data and len(aqi_data['list']) > 0:
                aqi = aqi_data['list'][0]['main']['aqi']
                pm25 = aqi_data['list'][0]['components'].get('pm2_5', 0)
    except Exception as e:
        print("AQI Fetch Error:", e)

    # ML RISK SCORE (0-100)
    # Get probabilites for [High Risk, Caution, Stable]
    probs = model.predict_proba([[temp, hum, wind, pressure, rain_prob]])[0]
    risk_score = int((1 - probs[2]) * 100) # (1 - probability of Stable) * 100

    if risk_score < 20: 
        ai = "🟢 Safe Conditions"
    elif risk_score < 60:
        ai = "🟡 Caution Advised"
    else:
        ai = "🔴 High Risk Alert"

    # Map condition for UI Skinning
    category = "clear"
    desc_low = weather_desc.lower()
    if "rain" in desc_low or "drizzle" in desc_low: category = "rainy"
    elif "cloud" in desc_low: category = "cloudy"
    elif "storm" in desc_low or "thunder" in desc_low: category = "storm"
    elif "snow" in desc_low: category = "snowy"
    elif temp > 30: category = "sunny"

    # AI Recommendation Engine (Gemini)
    rec_prompt = (
        f"Context: {city} weather is {temp}°C, {hum}% humidity, {wind}km/h wind, {weather_desc}. "
        f"Air Quality Index is {aqi} (1=Good, 5=Hazardous) with PM2.5 at {pm25}μg/m3. "
        f"User is a {user_type}. Respond ONLY in {lang}. "
        f"Task: Provide 3 extremely smart, role-specific strategic suggestions for today in {lang}. "
        "Each suggestion MUST be a single short sentence. Format as a bulleted list. "
        "Keep it professional and concise under 40 words. Use emojis."
    )
    
    tips = []
    # 1. Thermal Insight
    if temp > 32: tips.append(f"🌡️ Thermal Alert: {temp}°C detected. Prioritize hydration and shade.")
    elif temp < 15: tips.append(f"🌡️ Chill Factor: {temp}°C detected. Ensure thermal insulation.")
    else: tips.append(f"🌡️ Temperature Stable: {temp}°C is optimal for standard activities.")

    # 2. Environmental Vector Insight
    if "rain" in weather_desc.lower(): tips.append("🌧️ Moisture Sync: Precipitation active. Ensure waterproofing protocols.")
    elif wind > 20: tips.append(f"🌬️ Vector Alert: {wind}km/h wind detected. Secure loose structures.")
    elif hum > 80: tips.append(f"💧 Saturation Alert: {hum}% humidity. High moisture-related risk.")
    else: tips.append("📡 Conditions Clear: No significant atmospheric hazards detected.")

    # 3. Role-Specific Strategic Logic
    if user_type == "farmer":
        tips.append("🌾 Agricultural Strategy: Check soil pH and moisture levels before the next shift.")
        if hum > 75: tips.append("🦠 Fungal Protocol: High humidity increases disease risk for crops.")
    elif user_type == "traveler":
        tips.append("🚗 Transit Strategy: Review local traffic layers for weather-related slowdowns.")
        if wind > 15: tips.append("⚠️ Handling Alert: Crosswinds probable on high-exposure routes.")
    elif user_type == "student":
        tips.append("📚 Focus Strategy: Ideal window for deep-work sessions and cognitive focus.")
    elif user_type == "trekking":
        tips.append("⛰️ Exploration Strategy: Verify emergency beacons and GPS signal strength.")
    elif user_type == "sports":
        tips.append("🏟️ Performance Strategy: Check court/field traction before full-intensity play.")
    else:
        tips.append("👕 Routine Strategy: Maintain standard comfort protocols.")

    ai_tips = []
    try:
        g_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        g_res = requests.post(g_url, json={"contents": [{"parts": [{"text": rec_prompt}]}]}, timeout=10)
        ai_resp = g_res.json()
        if 'candidates' in ai_resp:
            raw_text = ai_resp['candidates'][0]['content']['parts'][0]['text']
            ai_tips = [t.replace('*', '').replace('-', '').strip() for t in raw_text.strip().split("\n") if t.strip()]
    except Exception as e: print("Gemini Rec Error:", e)

    final_tips = tips + ai_tips
    if not final_tips: final_tips = ["✨ Environment Stable.", "🛡 Safety Grid Active."]

    # Localized Telegram Formatting
    labels = {
        "en": {"temp": "Temp", "hum": "Humidity", "wind": "Wind", "risk": "Risk Score", "ai": "AI Verdict", "strat": "AI Strategy", "title": "Weather Update"},
        "hi": {"temp": "तापमान", "hum": "नमी", "wind": "हवा", "risk": "जोखिम स्कोर", "ai": "एआई निर्णय", "strat": "एआई रणनीति", "title": "मौसम अपडेट"},
        "te": {"temp": "ఉష్ణోగ్రత", "hum": "తేమ", "wind": "గాలి", "risk": "ప్రమాద స్కోరు", "ai": "AI తీర్పు", "strat": "AI వ్యూహం", "title": "వాతావరణ అప్‌డేట్"}
    }
    l = labels.get(lang, labels["en"])
    
    msg_body = "\n".join([f"• {t}" for t in final_tips[:6]])
    msg = (f"🌍 {l['title']} for {city}\n\n🌡 {l['temp']}: {temp}°C\n💧 {l['hum']}: {hum}%\n🌬 {l['wind']}: {wind} km/h\n🛡 {l['risk']}: {risk_score}%\n⚠️ {l['ai']}: {ai}\n\n💡 {l['strat']}:\n{msg_body}")
    send_telegram(telegram_token, telegram_chatid, msg)

    return jsonify({
        "temp": temp, "humidity": hum, "wind": wind, "desc": weather_desc,
        "risk_score": risk_score, "ai": ai, "condition_category": category, "tips": final_tips,
        "lat": lat, "lon": lon, "aqi": aqi, "pm25": pm25
    })

@app.route('/forecast')
def forecast():
    city = request.args.get('city')
    api_key = request.args.get('api_key', API_KEY)
    
    try:
        url = f"https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={api_key}&units=metric"
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        full_data = res.json()
        
        # Process for Daily Summary (3 Days)
        daily_summary = {}
        for item in full_data['list']:
            date = item['dt_txt'].split(' ')[0]
            if date not in daily_summary:
                daily_summary[date] = {
                    "temp": item['main']['temp'],
                    "hum": item['main']['humidity'],
                    "wind": item['wind']['speed'],
                    "desc": item['weather'][0]['description']
                }
            else:
                # Keep max temp for the day
                if item['main']['temp'] > daily_summary[date]['temp']:
                    daily_summary[date]['temp'] = item['main']['temp']
        
        # Sorted keys (next 3-4 days)
        sorted_dates = sorted(daily_summary.keys())
        
        return jsonify({
            "daily": [{
                "date": d,
                "label": datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%a"),
                "temp": daily_summary[d]['temp'],
                "hum": daily_summary[d]['hum'],
                "wind": daily_summary[d]['wind']
            } for d in sorted_dates[:4]],
            "full_list": full_data['list'] # For hourly drill-down
        })
    except Exception as e:
        print("Forecast Error:", e)
        return jsonify({"error": "Failed to fetch real-time forecast"})

@app.route('/send_telegram_alert', methods=['POST'])
def send_telegram_alert():
    data = request.json
    token = data.get('token')
    chatid = data.get('chatid')
    msg = data.get('message')
    
    if not token or not chatid or not msg:
        return jsonify({"error": "Missing credentials or message content"}), 400
        
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        res = requests.post(url, data={"chat_id": chatid, "text": msg}, timeout=10)
        if res.status_code == 200:
            return jsonify({"success": True})
        else:
            return jsonify({"error": f"Telegram API error: {res.text}"}), res.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------------------
# CHATBOT API
# -------------------------------
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_msg = data.get("message", "")
    weather_context = data.get("context", "")
    lang = data.get("lang", "en")
    is_voice = data.get("is_voice", False)
    user_type = data.get("user_type", "general")
    previous_query = data.get("previous", "")
    user_gemini_key = data.get("gemini_key", "") # Optional user-provided key
    
    # Response Caching handled at start
    cache_key = f"{user_msg}_{weather_context}_{user_type}_{is_voice}_{previous_query}".lower()
    if cache_key in chat_cache:
        return jsonify(chat_cache[cache_key])

    # Prioritize user's Gemini key, fallback to system key if provided key is empty/absent
    active_gemini_key = user_gemini_key if user_gemini_key else GEMINI_API_KEY
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={active_gemini_key}"
    
    if is_voice:
        if lang == 'te':
            prompt = (
                f"You are WeatherAI. Respond ONLY in Telugu (తెలుగు). "
                "Use simple conversational Telugu words like daily conversation. "
                "Break long words into smaller words. "
                "Avoid formal Telugu and avoid Sanskrit words. "
                "Write in short sentences (max 6 words per sentence). "
                "Do not mix English. "
                f"Context: {weather_context}. Question: {user_msg}."
            )
        elif lang == 'hi':
            prompt = (
                f"You are WeatherAI. Respond ONLY in Hindi (हिंदी). "
                "Use simple spoken Hindi (Hinglish/Common Hindi), but in PURE Devanagari script only. "
                "Do not use English words. Make it sound natural for synthesis. "
                f"User type: {user_type}. Context: {weather_context}. Question: {user_msg}. "
                "Keep it under 60 words."
            )
        else:
            prompt = (
                f"You are WeatherAI, a calm and intelligent weather assistant. Respond ONLY in {lang}. "
                f"User type: {user_type}. Context: {weather_context}. Question: {user_msg}. "
                f"\n\nSpeak naturally like a human assistant in {lang}. Use simple words but not robotic. Use correct grammar for {lang}. "
                "\n\nStructure your response like this:"
                "\n1. Direct answer"
                "\n2. Small explanation"
                "\n3. One helpful suggestion"
                "\n\nKeep it under 60 words. No emojis. No markdown. Make it sound smooth when spoken aloud."
            )
    else:
        # Enhanced prompt for well-structured text responses
        prompt = (
            f"You are a professional AI weather assistant catering to a {user_type}. Respond ONLY in {lang}. "
            f"Context: {weather_context}. User Query: {user_msg}. "
            f"\n\nFormat your response using Markdown in {lang} with the following structure:"
            "\n### 📊 Summary"
            "\nA brief 1-2 sentence overview."
            "\n### 🔍 Detailed Analysis"
            "\nKey points relevant to the user's specific role (traveler, farmer, etc.). Use bullet points."
            "\n### 💡 Advice & Safety"
            "\nActionable recommendations and safety warnings."
            "\n\nKeep it professional yet engaging with emojis. Use correct grammar for {lang}."
        )
    
    # Response Caching handled at start
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    try:
        # --- Attempt 1 ---
        res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=30)
        result = res.json()
        
        # Detect Overload / High Demand
        err_msg = result.get("error", {}).get("message", "")
        if "high demand" in err_msg.lower() or "overloaded" in err_msg.lower():
            print("Gemini High Demand detected. Retrying in 2 seconds...")
            time.sleep(2)
            
            # --- Attempt 2 (Retry) ---
            res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=30)
            result = res.json()
            err_msg = result.get("error", {}).get("message", "")

        if "error" in result:
            if "high demand" in err_msg.lower() or "overloaded" in err_msg.lower():
                return jsonify({"reply": "🚀 The Weather AI is currently handling a massive spike in requests. Please wait a moment and try again!"})
            return jsonify({"reply": f"⚠️ Gemini API Error: {err_msg}"})
        
        # Robust extraction
        candidates = result.get("candidates", [])
        if not candidates:
            return jsonify({"reply": "I'm sorry, I couldn't generate a response. Please try again."})
            
        first_candidate = candidates[0]
        content = first_candidate.get("content", {})
        parts = content.get("parts", [])
        
        if not parts:
            reason = first_candidate.get("finishReason", "Unknown")
            return jsonify({"reply": f"Response blocked by AI safety filters. Reason: {reason}"})

        reply_text = parts[0].get("text", "No response text found.")
        
        # Generate Voice for AI responses
        audio_url = None
        if is_voice:
            audio_url = generate_voice(reply_text, lang)

        # Save to cache
        chat_cache[cache_key] = {"reply": reply_text, "audio": audio_url}
        
        return jsonify({"reply": reply_text, "audio": audio_url})
        
    except Exception as e:
        print("Gemini Exception:", e)
        return jsonify({"reply": "Sorry, I am having trouble connecting to my AI brain. Please try again in a moment."})

# -------------------------------
# AUTOMATED DAILY BRIEFINGS (APScheduler)
# -------------------------------
import json
import os

SUBSCRIPTIONS_FILE = "subscriptions.json"

def load_subscriptions():
    if os.path.exists(SUBSCRIPTIONS_FILE):
        with open(SUBSCRIPTIONS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_subscriptions(subs):
    with open(SUBSCRIPTIONS_FILE, "w") as f:
        json.dump(subs, f)

@app.route('/subscribe_daily', methods=['POST'])
def subscribe_daily():
    data = request.json
    uid = data.get("uid")
    if not uid:
        return jsonify({"error": "Missing UID"}), 400
        
    subs = load_subscriptions()
    subs[uid] = {
        "city": data.get("city", "London"),
        "telegram_token": data.get("telegram_token"),
        "telegram_chatid": data.get("telegram_chatid"),
        "lang": data.get("lang", "en"),
        "user_type": data.get("user_type", "general"),
        "gemini_key": data.get("gemini_key", GEMINI_API_KEY),
        "enabled": data.get("enabled", True)
    }
    save_subscriptions(subs)
    return jsonify({"success": True, "message": "Subscription updated"})

def send_daily_briefings():
    subs = load_subscriptions()
    print(f"[{datetime.datetime.now()}] Running Daily Briefings for {len(subs)} users...")
    for uid, s in subs.items():
        if not s.get("enabled") or not s.get("telegram_token") or not s.get("telegram_chatid"):
            continue
            
        city = s["city"]
        lang = s["lang"]
        user_type = s["user_type"]
        token = s["telegram_token"]
        chatid = s["telegram_chatid"]
        api_key = s.get("gemini_key", GEMINI_API_KEY)
        if not api_key: api_key = GEMINI_API_KEY
        
        # 1. Fetch Weather
        w_data = get_weather(city, API_KEY)
        if "main" not in w_data: continue
        
        temp = w_data["main"]["temp"]
        hum = w_data["main"]["humidity"]
        desc = w_data["weather"][0]["description"]
        
        # 2. Get AI Prompt
        prompt = (
            f"You are WeatherAI. This is a daily morning briefing for a {user_type}. "
            f"The weather in {city} is {temp}°C, {hum}% humidity, and {desc}. "
            f"Provide a short, motivating 3-sentence daily strategy in {lang}. Use emojis."
        )
        try:
            g_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            g_res = requests.post(g_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
            ai_text = g_res.json()['candidates'][0]['content']['parts'][0]['text']
        except:
            ai_text = "Have a great and safe day ahead!"
            
        # 3. Send Telegram
        msg = f"🌅 *Good Morning! Daily Briefing for {city}*\n\n🌡 Temp: {temp}°C\n💧 Humidity: {hum}%\n☁ Cond: {desc}\n\n🤖 *AI Strategy:*\n{ai_text}"
        try:
            t_url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(t_url, data={"chat_id": chatid, "text": msg, "parse_mode": "Markdown"})
        except Exception as e:
            print("Daily Telegram Error:", e)

@app.route('/trigger_daily')
def trigger_daily():
    send_daily_briefings()
    return jsonify({"success": True, "message": "Manual trigger executed."})

# Initialize APScheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=send_daily_briefings, trigger="cron", hour=7, minute=0)
scheduler.start()

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    app.run(debug=False)
