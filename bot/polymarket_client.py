import requests

GAMMA_URL = "https://gamma-api.polymarket.com"

def get_markets(limit=20, offset=0):
    params = {"limit": limit, "offset": offset, "active": "true", "closed": "false"}
    r = requests.get(f"{GAMMA_URL}/markets", params=params)
    r.raise_for_status()
    return r.json()

def parse_market(m):
    return {
        "id":       m.get("id"),
        "question": m.get("question"),
        "category": m.get("category", ""),
        "volume":   float(m.get("volume", 0)),
        "outcomes": m.get("outcomes", []),
        "prices":   m.get("outcomePrices", []),
    }

if __name__ == "__main__":
    raw = get_markets(limit=5)
    markets = [parse_market(m) for m in raw]
    for mkt in markets:
        print(f"\n📌 {mkt['question']}")
        print(f"   Catégorie : {mkt['category']}")
        print(f"   Volume    : ${mkt['volume']:,.0f}")
        for outcome, price in zip(mkt['outcomes'], mkt['prices']):
            print(f"   {outcome:10s} → {float(price)*100:.1f}%")