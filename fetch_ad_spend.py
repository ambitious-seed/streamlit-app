import os
from datetime import datetime, timedelta
from google.ads.googleads.client import GoogleAdsClient
from supabase import create_client

# 1. Инициализация Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Дата за вчера
yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

# 2. Конфигурация Google Ads API из GitHub Secrets
google_config = {
    "developer_token": os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN"),
    "client_id": os.getenv("GOOGLE_ADS_CLIENT_ID"),
    "client_secret": os.getenv("GOOGLE_ADS_CLIENT_SECRET"),
    "refresh_token": os.getenv("GOOGLE_ADS_REFRESH_TOKEN"),
    "login_customer_id": os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID"),
    "token_uri": "https://oauth2.googleapis.com/token",
    "use_proto_plus": True
}

def fetch_google_ads_spend(date_str):
    records = []
    try:
        client = GoogleAdsClient.load_from_dict(google_config)
        ga_service = client.get_service("GoogleAdsService")
        
        # ID рекламного аккаунта Ambitious Seed (709-670-5231 -> 7096705231)
        customer_id = "7096705231" 
        
        # Запрос расхода и названий кампаний по GAQL
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
            # cost_micros делим на 1 000 000, чтобы получить сумму в USD
            spend_usd = round(row.metrics.cost_micros / 1000000.0, 4)
            records.append({
                "date": date_str,
                "ad_network": "googleadwords_int",
                "campaign_name": row.campaign.name,
                "spend": spend_usd
            })
            
    except Exception as e:
        print(f"Ошибка при запросе к Google Ads API: {e}")
        
    return records

def main():
    print(f"Сбор расходов за {yesterday_str}...")
    spend_data = fetch_google_ads_spend(yesterday_str)
    
    if spend_data:
        # Upsert данных в таблицу Supabase
        res = supabase.table("ad_spend").upsert(
            spend_data, 
            on_conflict="date,ad_network,campaign_name"
        ).execute()
        print(f"Успешно записано {len(spend_data)} записей в Supabase!")
    else:
        print("За вчерашний день расходов не найдено или возникла ошибка.")

if __name__ == "__main__":
    main()
