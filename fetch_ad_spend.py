import os
import io
import csv
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta
from google.ads.googleads.client import GoogleAdsClient
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights
from supabase import create_client

# --- ДИАГНОСТИКА SECRETS ---
print("--- ДИАГНОСТИКА SECRETS ---")
def check_secret(name):
    val = os.getenv(name)
    if val is None:
        return "ОТСУТСТВУЕТ (None)"
    elif len(val.strip()) == 0:
        return "ПУСТАЯ СТРОКА"
    else:
        return f"ЗАДАН (длина: {len(val.strip())})"

for secret_name in [
    "GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET",
    "GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_LOGIN_CUSTOMER_ID", "META_APP_ID",
    "META_APP_SECRET", "META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID",
    "UNITY_ORGANIZATION_ID", "UNITY_API_KEY"
]:
    print(f"{secret_name}: {check_secret(secret_name)}")
print("---------------------------")

# 1. Инициализация Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

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

    if not ad_account_id.startswith("act_"):
        ad_account_id = f"act_{ad_account_id}"

    try:
        FacebookAdsApi.init(app_id, app_secret, access_token)
        account = AdAccount(ad_account_id)
        
        params = {
            'time_range': {'since': date_str, 'until': date_str},
            'level': 'adset',
        }
        fields = [
            AdsInsights.Field.adset_name,
            AdsInsights.Field.spend,
        ]
        
        insights = account.get_insights(fields=fields, params=params)
        
        for item in insights:
            spend_val = float(item.get('spend', 0))
            if spend_val > 0:
                records.append({
                    "date": date_str,
                    "ad_network": "facebook",
                    "campaign_name": item.get('adset_name', 'Unknown Adset'),
                    "spend": spend_val
                })
                
        print(f"✅ Meta Ads: Найдено {len(records)} групп объявлений с расходами.")
                
    except Exception as e:
        print(f"⚠️ Ошибка при запросе к Meta Ads API: {e}")
        
    return records

def fetch_unity_ads_spend(date_str):
    records = []
    org_id = os.getenv("UNITY_ORGANIZATION_ID")
    api_key = os.getenv("UNITY_API_KEY")

    if not all([org_id, api_key]):
        print("⚠️ Пропущены секреты Unity Ads — сбор Unity отменен.")
        return records

    url = f"https://services.api.unity.com/advertise/stats/v2/organizations/{org_id}/reports/acquisitions"
    
    headers = {}
    auth = None
    if ":" in api_key:
        key_id, secret_key = api_key.split(":", 1)
        auth = HTTPBasicAuth(key_id, secret_key)
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    
    params = {
        "start": date_str,
        "end": date_str,
        "scale": "day",
        "breakdowns": "campaign",
        "metrics": "spend"
    }

    try:
        response = requests.get(url, headers=headers, auth=auth, params=params, timeout=60)
        if response.status_code == 204:
            print("Unity Ads: РґР°РЅРЅС‹С… Р·Р° РґР°С‚Сѓ РЅРµС‚.")
            return records
        response.raise_for_status()
        
        # Stats API v2.0 возвращает ответ в CSV
        csv_reader = csv.DictReader(io.StringIO(response.text))
        
        for row in csv_reader:
            spend_val = float(row.get("spend", 0))
            campaign_name = row.get("campaign name") or row.get("campaign_name") or "Unknown Unity Campaign"
            
            if spend_val > 0:
                records.append({
                    "date": date_str,
                    "ad_network": "unity",
                    "campaign_name": campaign_name,
                    "spend": spend_val
                })
                
        print(f"✅ Unity Ads: Найдено {len(records)} кампаний с расходами.")
        
    except Exception as e:
        print(f"⚠️ Ошибка при запросе к Unity Stats API v2.0: {e}")

    return records

def main():
    today = datetime.now()
    
    for i in range(1, 4):
        target_date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        print(f"--- Сбор расходов за {target_date} ---")
        
        google_data = fetch_google_ads_spend(target_date)
        meta_data = fetch_facebook_ads_spend(target_date)
        unity_data = fetch_unity_ads_spend(target_date)
        
        all_spend_data = google_data + meta_data + unity_data
        
        if all_spend_data:
            supabase.table("ad_spend").upsert(
                all_spend_data, 
                on_conflict="date,ad_network,campaign_name"
            ).execute()
            print(f"🎉 Записано {len(all_spend_data)} записей за {target_date}!")
        else:
            print(f"За {target_date} расходов не найдено.")

if __name__ == "__main__":
    main()
