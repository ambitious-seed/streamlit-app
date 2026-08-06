import streamlit as st
import pandas as pd
import json
from supabase import create_client

st.set_page_config(page_title="Tiny Friends Analytics", layout="wide")
st.title("📊 Tiny Friends (User Acquisition & Attribution)")

# 1. Подключение к Supabase
SUPABASE_URL = "https://zxzcywphwkviqbbfgkpr.supabase.co"
SUPABASE_KEY = "sb_publishable_K-PXcgoZCnW_Vemg8Q_baQ_Wn7YAblg"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 2. Фильтры
st.sidebar.header("⚙️ Настройки отчета")
date_range = st.sidebar.date_input("Дата установки", [])

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

AVAILABLE_METRICS = [
    "Installs", 
    "Spend ($)",
    "CPI ($)",
    "ROAS (%)",
    "RR D1 (%)", 
    "RR D3 (%)", 
    "RR D7 (%)", 
    "Ad Revenue ($)", 
    "IAP Revenue ($)", 
    "Total Revenue ($)", 
    "Avg Sessions"
]

selected_metrics = st.sidebar.multiselect(
    "Метрики (Metrics)",
    options=AVAILABLE_METRICS,
    default=["Installs", "Spend ($)", "CPI ($)", "ROAS (%)", "RR D1 (%)", "Ad Revenue ($)", "Total Revenue ($)"]
)

if len(date_range) == 2:
    start_date, end_date = date_range
    
    # Расширяем границу конца дня на +1 день для корректного перекрытия времени
    next_day = end_date + pd.Timedelta(days=1)
    
    start_str = start_date.strftime("%Y-%m-%dT00:00:00Z")
    end_str = next_day.strftime("%Y-%m-%dT00:00:00Z")
    
    try:
        # Запрос установок из mmp с запасом по времени
        mmp_res = (
            supabase.table("mmp")
            .select("*")
            .gte("first_session_date", start_str)
            .lt("first_session_date", end_str)  # lt вместо lte исключает следующую полночь
            .execute()
        )
        
        # 2. Запрос ad revenue
        ad_res = supabase.table("mmp_ad_revenue_events").select("*").execute()
        
        # 3. Запрос расходов из ad_spend (перенесено внутрь условия проверки дат!)
        spend_res = supabase.table("ad_spend") \
            .select("campaign_name, ad_network, spend") \
            .gte("date", str(start_date)) \
            .lte("date", str(end_date)) \
            .execute()

        if mmp_res.data:
            df_mmp = pd.DataFrame(mmp_res.data)
            df_ad = pd.DataFrame(ad_res.data) if ad_res.data else pd.DataFrame()
            df_spend = pd.DataFrame(spend_res.data) if spend_res.data else pd.DataFrame()
            
            # Подготовка полей
            df_mmp['install_date'] = pd.to_datetime(df_mmp['first_session_date']).dt.date
            df_mmp['ad_network'] = df_mmp['ad_network'].fillna('Organic')
            df_mmp['campaign_name'] = df_mmp['campaign_name'].fillna('Organic')
            df_mmp['creative_name'] = df_mmp['creative_name'].fillna('None') if 'creative_name' in df_mmp.columns else 'None'
            
            # Расчет Retention Rate
            install_dt = pd.to_datetime(df_mmp['first_session_date'], errors='coerce')
            last_sess_dt = pd.to_datetime(df_mmp['last_session_date'], errors='coerce').fillna(install_dt)
            
            days_diff = (last_sess_dt.dt.date - install_dt.dt.date).apply(lambda x: x.days if pd.notnull(x) else 0)
            
            df_mmp['RR D1 (%)'] = (days_diff >= 1).astype(int) * 100
            df_mmp['RR D3 (%)'] = (days_diff >= 3).astype(int) * 100
            df_mmp['RR D7 (%)'] = (days_diff >= 7).astype(int) * 100
            
            # Привязка Ad Revenue
            if not df_ad.empty and 'iid' in df_ad.columns:
                ad_by_iid = df_ad.groupby('iid')['revenue'].sum().reset_index()
                ad_by_iid.rename(columns={'revenue': 'Ad Revenue ($)'}, inplace=True)
                df_mmp = df_mmp.merge(ad_by_iid, on='iid', how='left')
                df_mmp['Ad Revenue ($)'] = df_mmp['Ad Revenue ($)'].fillna(0)
            else:
                df_mmp['Ad Revenue ($)'] = 0.0
                
            # Парсинг IAP Revenue
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
            
            # Группировка MMP
            if selected_dimensions:
                agg_rules = {
                    'Installs': 'sum',
                    'RR D1 (%)': 'mean',
                    'RR D3 (%)': 'mean',
                    'RR D7 (%)': 'mean',
                    'Ad Revenue ($)': 'sum',
                    'IAP Revenue ($)': 'sum',
                    'Total Revenue ($)': 'sum',
                    'Avg Sessions': 'mean'
                }
                
                grouped_df = df_mmp.groupby(selected_dimensions).agg(agg_rules).reset_index()
                
                # Привязка расходов из ad_spend
                if not df_spend.empty:
                    spend_dims = [d for d in selected_dimensions if d in ['ad_network', 'campaign_name']]
                    if spend_dims:
                        spend_grouped = df_spend.groupby(spend_dims)['spend'].sum().reset_index()
                        spend_grouped.rename(columns={'spend': 'Spend ($)'}, inplace=True)
                        grouped_df = grouped_df.merge(spend_grouped, on=spend_dims, how='left')
                    else:
                        grouped_df['Spend ($)'] = 0.0
                else:
                    grouped_df['Spend ($)'] = 0.0
                
                grouped_df['Spend ($)'] = grouped_df['Spend ($)'].fillna(0.0)

                # Вычисление CPI и ROAS
                grouped_df['CPI ($)'] = grouped_df.apply(
                    lambda r: round(r['Spend ($)'] / r['Installs'], 2) if r['Installs'] > 0 else 0.0, axis=1
                )
                grouped_df['ROAS (%)'] = grouped_df.apply(
                    lambda r: round((r['Total Revenue ($)'] / r['Spend ($)'] * 100), 1) if r['Spend ($)'] > 0 else 0.0, axis=1
                )
                
                # Финальное форматирование выводных колонок
                for col in ['Ad Revenue ($)', 'IAP Revenue ($)', 'Total Revenue ($)', 'Spend ($)']:
                    grouped_df[col] = grouped_df[col].round(2)
                
                for col in ['RR D1 (%)', 'RR D3 (%)', 'RR D7 (%)', 'ROAS (%)']:
                    grouped_df[col] = grouped_df[col].round(1).astype(str) + " %"
                    
                if 'Avg Sessions' in grouped_df.columns:
                    grouped_df['Avg Sessions'] = grouped_df['Avg Sessions'].round(1)

                # Фильтрация только по выбранным пользователем метрикам
                final_cols = selected_dimensions + [c for c in selected_metrics if c in grouped_df.columns]
                
                st.subheader("Результаты анализа")
                st.dataframe(grouped_df[final_cols], use_container_width=True)
            else:
                st.warning("Выберите хотя бы один параметр для группировки в панели слева.")
        else:
            st.info("За выбранный период установок не найдено.")
            
    except Exception as e:
        st.error(f"Ошибка выполнения запроса: {e}")
else:
    st.info("Пожалуйста, выберите диапазон дат в левой панели.")
