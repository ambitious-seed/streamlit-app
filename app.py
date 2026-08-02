import streamlit as st
import pandas as pd
import json
from supabase import create_client

# Настройки страницы Streamlit
st.set_page_config(page_title="Custom Analytics Report", layout="wide")

st.title("📊 Конструктор отчетов (User Acquisition & Attribution)")

# 1. Подключение к Supabase
SUPABASE_URL = "https://zxzcywphwkviqbbfgkpr.supabase.co"
SUPABASE_KEY = "sb_publishable_K-PXcgoZCnW_Vemg8Q_baQ_Wn7YAblg" 

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 2. Фильтры в панели слева
st.sidebar.header("⚙️ Настройки отчета")

# Выбор периода
date_range = st.sidebar.date_input("Дата установки", [])

# 3. Выбор Группировки (Разделение)
DIMENSIONS_MAP = {
    "Рекламная сеть": "ad_network",
    "Кампания": "campaign_name",
    "Креатив": "creative_name",
    "Дата установки": "install_date"
}

selected_dimensions_labels = st.sidebar.multiselect(
    "Разделение (Dimensions)",
    options=list(DIMENSIONS_MAP.keys()),
    default=["Рекламная сеть", "Кампания"]
)
selected_dimensions = [DIMENSIONS_MAP[label] for label in selected_dimensions_labels]

# 4. Выбор Метрик
AVAILABLE_METRICS = ["Installs", "Ad Revenue ($)", "IAP Revenue ($)", "Total Revenue ($)", "Avg Sessions"]
selected_metrics = st.sidebar.multiselect(
    "Метрики (Metrics)",
    options=AVAILABLE_METRICS,
    default=["Installs", "Ad Revenue ($)", "Total Revenue ($)"]
)

if len(date_range) == 2:
    start_date, end_date = date_range
    start_str = f"{start_date} 00:00:00"
    end_str = f"{end_date} 23:59:59"
    
    try:
        # Запрос установок из таблицы mmp_rows
        mmp_res = supabase.table("mmp_rows") \
            .select("*") \
            .gte("created_at", start_str) \
            .lte("created_at", end_str) \
            .execute()
        
        # Запрос доходов из таблицы mmp_ad_revenue_events
        ad_res = supabase.table("mmp_ad_revenue_events").select("*").execute()
        
        if mmp_res.data:
            df_mmp = pd.DataFrame(mmp_res.data)
            df_ad = pd.DataFrame(ad_res.data) if ad_res.data else pd.DataFrame()
            
            # Подготовка вспомогательных полей
            df_mmp['install_date'] = pd.to_datetime(df_mmp['created_at']).dt.date
            df_mmp['ad_network'] = df_mmp['ad_network'].fillna('Organic')
            df_mmp['campaign_name'] = df_mmp['campaign_name'].fillna('None')
            df_mmp['creative_name'] = df_mmp['creative_name'].fillna('None')
            
            # Подтягиваем Ad Revenue по каждому iid из событий
            if not df_ad.empty:
                ad_by_iid = df_ad.groupby('iid')['revenue'].sum().reset_index()
                ad_by_iid.rename(columns={'revenue': 'Ad Revenue ($)'}, inplace=True)
                df_mmp = df_mmp.merge(ad_by_iid, on='iid', how='left')
                df_mmp['Ad Revenue ($)'] = df_mmp['Ad Revenue ($)'].fillna(0)
            else:
                df_mmp['Ad Revenue ($)'] = 0.0
                
            # Парсим IAP Revenue
            def parse_iap(val):
                if isinstance(val, dict):
                    return float(sum(val.values())) if val else 0.0
                try:
                    d = json.loads(val)
                    return float(sum(d.values())) if d else 0.0
                except:
                    return 0.0

            df_mmp['IAP Revenue ($)'] = df_mmp['iap_revenue_by_currency'].apply(parse_iap)
            df_mmp['Total Revenue ($)'] = df_mmp['Ad Revenue ($)'] + df_mmp['IAP Revenue ($)']
            df_mmp['Installs'] = 1
            df_mmp['Avg Sessions'] = df_mmp['session_count']
            
            # 5. Динамическая группировка
            if selected_dimensions:
                agg_rules = {
                    'Installs': 'sum',
                    'Ad Revenue ($)': 'sum',
                    'IAP Revenue ($)': 'sum',
                    'Total Revenue ($)': 'sum',
                    'Avg Sessions': 'mean'
                }
                
                active_agg = {k: agg_rules[k] for k in selected_metrics if k in agg_rules}
                
                grouped_df = df_mmp.groupby(selected_dimensions).agg(active_agg).reset_index()
                
                # Округление финансовых показателей
                for col in ['Ad Revenue ($)', 'IAP Revenue ($)', 'Total Revenue ($)']:
                    if col in grouped_df.columns:
                        grouped_df[col] = grouped_df[col].round(4)
                if 'Avg Sessions' in grouped_df.columns:
                    grouped_df['Avg Sessions'] = grouped_df['Avg Sessions'].round(1)

                st.subheader("Результаты анализа")
                st.dataframe(grouped_df, use_container_width=True)
            else:
                st.warning("Выберите хотя бы один параметр для группировки в панели слева.")
        else:
            st.info("За выбранный период установок не найдено.")
            
    except Exception as e:
        st.error(f"Ошибка выполнения запроса: {e}")
