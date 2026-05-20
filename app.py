from flask import Flask, request, jsonify
import json, os, aiohttp, asyncio, requests, binascii
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
import like_pb2, like_count_pb2, uid_generator_pb2
from google.protobuf.message import DecodeError

app = Flask(__name__)

ACCOUNTS_FILE = 'accounts.json'

# ✅ लोड अकाउंट्स
def load_accounts():
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, 'r') as f:
            return json.load(f)
    return {}

# ✅ नया टोकन फंक्शन - 2 स्टेप्स में
async def fetch_token(session, uid, password):
    try:
        # STEP 1: UID + Password से सिर्फ access_token लेना है
        url1 = f"https://uid-pass-to-jwt-token.onrender.com/api/token?uid={uid}&pass={password}"
        
        async with session.get(url1, timeout=10) as res1:
            if res1.status != 200:
                print(f"Step 1 failed for {uid}: {res1.status}")
                return None
            
            data1 = await res1.json()
            
            # पहली API से access_token निकालो
            access_token = None
            if data1.get("success") and "tokens" in data1:
                access_token = data1["tokens"].get("access_token")
            elif "access_token" in data1:
                access_token = data1["access_token"]
            
            if not access_token:
                print(f"No access_token found for {uid}")
                return None
            
            # STEP 2: access_token से real jwt_token लेना है
            url2 = f"https://zainu-acesstoken.onrender.com/rizer?access_token={access_token}"
            
            async with session.get(url2, timeout=10) as res2:
                if res2.status != 200:
                    print(f"Step 2 failed for {uid}: {res2.status}")
                    return None
                
                data2 = await res2.json()
                jwt_token = data2.get("jwt")
                
                if jwt_token:
                    return jwt_token
                else:
                    print(f"No jwt_token in response for {uid}")
                    return None
                    
    except Exception as e:
        print(f"Error fetching token for {uid}: {e}")
        return None

# ✅ सारे टोकन लाइव लेना - FIXED (ab region parameter hai)
async def get_tokens_live(region="ME"):
    accounts = load_accounts()
    tokens = []
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_token(session, uid, password) for uid, password in accounts.items()]
        results = await asyncio.gather(*tasks)
        tokens = [token for token in results if token]
    return tokens

# ✅ एन्क्रिप्शन फंक्शन
def encrypt_message(plaintext):
    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return binascii.hexlify(cipher.encrypt(pad(plaintext, AES.block_size))).decode()

def create_uid_proto(uid):
    pb = uid_generator_pb2.uid_generator()
    pb.saturn_ = int(uid)
    pb.garena = 1
    return pb.SerializeToString()

def create_like_proto(uid):
    pb = like_pb2.like()
    pb.uid = int(uid)
    return pb.SerializeToString()

def decode_protobuf(binary):
    try:
        pb = like_count_pb2.Info()
        pb.ParseFromString(binary)
        return pb
    except DecodeError:
        return None

def make_request(enc_uid, token):
    url = "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"
    headers = {
        'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'Authorization': f"Bearer {token}",
        'Content-Type': "application/x-www-form-urlencoded",
        'Expect': "100-continue",
        'X-Unity-Version': "2018.4.11f1",
        'X-GA': "v1 1",
        'ReleaseVersion': "OB53"
    }
    try:
        res = requests.post(url, data=bytes.fromhex(enc_uid), headers=headers, verify=False)
        return decode_protobuf(res.content)
    except:
        return None

# ✅ लाइक रिक्वेस्ट भेजना
async def send_request(enc_uid, token):
    url = "https://clientbp.ggpolarbear.com/LikeProfile"
    headers = {
        'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'Authorization': f"Bearer {token}",
        'Content-Type': "application/x-www-form-urlencoded",
        'Expect': "100-continue",
        'X-Unity-Version': "2018.4.11f1",
        'X-GA': "v1 1",
        'ReleaseVersion': "OB53"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=bytes.fromhex(enc_uid), headers=headers, ssl=False) as r:
                return r.status
    except Exception as e:
        print(f"Error in send_request: {e}")
        return None

# ✅ सारे टोकन से लाइक भेजना
async def send_likes(uid, tokens):
    enc_uid = encrypt_message(create_like_proto(uid))
    tasks = [send_request(enc_uid, token) for token in tokens]
    return await asyncio.gather(*tasks)

# ✅ मुख्य एंडपॉइंट - FIXED (pura response)
@app.route('/like', methods=['GET'])
def like_handler():
    uid = request.args.get("uid")
    region = request.args.get("region", "ME")
    
    if not uid:
        return jsonify({"error": "Missing UID"}), 400

    try:
        # टोकन लो
        tokens = asyncio.run(get_tokens_live(region))
        if not tokens:
            return jsonify({"error": "No valid tokens available"}), 401

        # पहले की जानकारी लो
        enc_uid = encrypt_message(create_uid_proto(uid))
        before = make_request(enc_uid, tokens[0])
        if not before:
            return jsonify({"error": "Failed to retrieve player info"}), 500

        before_data = json.loads(MessageToJson(before))
        likes_before = int(before_data.get("AccountInfo", {}).get("Likes", 0))
        nickname = before_data.get("AccountInfo", {}).get("PlayerNickname", "Unknown")

        # लाइक भेजो
        responses = asyncio.run(send_likes(uid, tokens))
        success_count = sum(1 for r in responses if r == 200)

        # बाद की जानकारी लो
        after = make_request(enc_uid, tokens[0])
        likes_after = likes_before
        if after:
            after_data = json.loads(MessageToJson(after))
            likes_after = int(after_data.get("AccountInfo", {}).get("Likes", 0))

        return jsonify({
            "PlayerNickname": nickname,
            "UID": uid,
            "Region": region,
            "LikesBefore": likes_before,
            "LikesAfter": likes_after,
            "LikesGivenByAPI": likes_after - likes_before,
            "SuccessfulRequests": success_count,
            "TotalRequests": len(tokens),
            "status": 1 if likes_after > likes_before else 2
        })

    except Exception as e:
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route('/')
def home():
    return jsonify({"status": "online", "message": "Like API is running ✅"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)