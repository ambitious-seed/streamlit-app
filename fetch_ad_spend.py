import os
from datetime import datetime, timedelta
from google.ads.googleads.client import GoogleAdsClient
from supabase import create_client

# 1. Проверка Secrets перед запуском
required_secrets = {
    "GOOGLE_ADS_DEVELOPER_TOKEN": os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN"),
    "GOOGLE_ADS_CLIENT_ID": os.getenv("GOOGLE_ADS_CLIENT_ID"),
    "GOOGLE_ADS_CLIENT_SECRET": os.getenv("GOOGLE_ADS_CLIENT_SECRET"),
    "GOOGLE_ADS_REFRESH_TOKEN": os.getenv("GOOGLE_ADS_REFRESH_TOKEN"),
    "GOOGLE_ADS_LOGIN_CUSTOMER_ID": os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID"),
}

missing_secrets = [key for key, val in required_secrets.items() if not val]

if missing_secrets:
    print(f"❌ ОШИБКА: В GitHub Secrets не найдены (или пустые): {missing_secrets}")
    exit(1)
else:
    print("✅ Все секреты успешно прочитаны!")

# 2. Конфигурация Google Ads API
google_config = {
    "developer_token": os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN"),
    "client_id": os.getenv("GOOGLE_ADS_CLIENT_ID"),
    "client_secret": os.getenv("GOOGLE_ADS_CLIENT_SECRET"),
    "refresh_token": os.getenv("GOOGLE_ADS_REFRESH_TOKEN"),
    "login_customer_id": os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID"),
    "token_uri": "https://oauth2.googleapis.com/token",
    "use_proto_plus": True
}

# 3. Инициализация Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

def fetch_google_ads_spend(date_str):
    records = []
    try:
        client = GoogleAdsClient.load_from_dict(google_config)
        ga_service = client.get_service("GoogleAdsService")
        customer_id = "7096705231"
        
        query = f"""
            SELECT 
                campaign.name, 
                metrics.cost_micros 
            FROM campaign 
            WHERE segments.date = '{date_str}'
              AND metrics.cost_micros > 0
        """
        
        response = ga_service.search(customer_id=customer_id, query=query)
        
        for row in response:
            spend_usd = round(row.metrics.cost_micros / 1000000.0, 4)
            records.append({
                "date": date_str,
                "ad_network": "googleadwords_int",
                "campaign_name": row.campaign.name,
                "spend": spend_usd
            })
            
    except Exception as e:
        print(f"❌ Ошибка при запросе к Google Ads API: {e}")
        
    return records

def main():
    print(f"Сбор расходов за {yesterday_str}...")
    spend_data = fetch_google_ads_spend(yesterday_str)
    
    if spend_data:
        res = supabase.table("ad_spend").upsert(
            spend_data, 
            on_conflict="date,ad_network,campaign_name"
        ).execute()
        print(f"🎉 Успешно записано {len(spend_data)} записей в Supabase!")
    else:
        print("За вчерашний день расходов с > $0 не найдено.")

if __name__ == "__main__":
    main()