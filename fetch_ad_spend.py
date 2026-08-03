import os
from datetime import datetime, timedelta
from google.ads.googleads.client import GoogleAdsClient
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights
from supabase import create_client

# --- ДИАГНОСТИКА SECRETS ---
print("--- ДИАГНОСТИКА SECRETS ---")
print("GOOGLE_ADS_DEVELOPER_TOKEN:", "ЗАДАН" if os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN") else "ПУСТО / ОТСУТСТВУЕТ")
print("GOOGLE_ADS_CLIENT_ID:", "ЗАДАН" if os.getenv("GOOGLE_ADS_CLIENT_ID") else "ПУСТО / ОТСУТСТВУЕТ")
print("GOOGLE_ADS_CLIENT_SECRET:", "ЗАДАН" if os.getenv("GOOGLE_ADS_CLIENT_SECRET") else "ПУСТО / ОТСУТСТВУЕТ")
print("GOOGLE_ADS_REFRESH_TOKEN:", "ЗАДАН" if os.getenv("GOOGLE_ADS_REFRESH_TOKEN") else "ПУСТО / ОТСУТСТВУЕТ")
print("GOOGLE_ADS_LOGIN_CUSTOMER_ID:", "ЗАДАН" if os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID") else "ПУСТО / ОТСУТСТВУЕТ")
print("META_APP_ID:", "ЗАДАН" if os.getenv("META_APP_ID") else "ПУСТО / ОТСУТСТВУЕТ")
print("META_APP_SECRET:", "ЗАДАН" if os.getenv("META_APP_SECRET") else "ПУСТО / ОТСУТСТВУЕТ")
print("META_ACCESS_TOKEN:", "ЗАДАН" if os.getenv("META_ACCESS_TOKEN") else "ПУСТО / ОТСУТСТВУЕТ")
print("META_AD_ACCOUNT_ID:", "ЗАДАН" if os.getenv("META_AD_ACCOUNT_ID") else "ПУСТО / ОТСУТСТВУЕТ")
print("---------------------------")

# 1. Инициализация Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

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
        print(f"⚠️ Ошибка при запросе к Google Ads API: {e}")
        
    return records

def fetch_facebook_ads_spend(date_str):
    records = []
    app_id = os.getenv("META_APP_ID")
    app_secret = os.getenv("META_APP_SECRET")
    access_token = os.getenv("META_ACCESS_TOKEN")
    ad_account_id = os.getenv("META_AD_ACCOUNT_ID")

    if not all([app_id, app_secret, access_token, ad_account_id]):
        print("⚠️ Пропущены некоторые секреты Meta Ads — сбор FB отменен.")
        return records

    try:
        FacebookAdsApi.init(app_id, app_secret, access_token)
        account = AdAccount(ad_account_id)
        
        params = {
            'time_range': {'since': date_str, 'until': date_str},
            'level': 'campaign',
        }
        fields = [
            AdsInsights.Field.campaign_name,
            AdsInsights.Field.spend,
        ]
        
        insights = account.get_insights(fields=fields, params=params)
        
        for item in insights:
            spend_val = float(item.get('spend', 0))
            if spend_val > 0:
                records.append({
                    "date": date_str,
                    "ad_network": "facebook",
                    "campaign_name": item.get('campaign_name', 'Unknown'),
                    "spend": spend_val
                })
                
    except Exception as e:
        print(f"⚠️ Ошибка при запросе к Meta Ads API: {e}")
        
    return records

def main():
    print(f"Сбор расходов за {yesterday_str}...")
    
    google_data = fetch_google_ads_spend(yesterday_str)
    meta_data = fetch_facebook_ads_spend(yesterday_str)
    
    all_spend_data = google_data + meta_data
    
    if all_spend_data:
        supabase.table("ad_spend").upsert(
            all_spend_data, 
            on_conflict="date,ad_network,campaign_name"
        ).execute()
        print(f"🎉 Успешно записано {len(all_spend_data)} записей в Supabase! (Google: {len(google_data)}, Meta: {len(meta_data)})")
    else:
        print("За вчерашний день расходов не найдено или возникли ошибки.")

if __name__ == "__main__":
    main()