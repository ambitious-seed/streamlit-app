import streamlit as st
import pandas as pd
import json
from supabase import create_client

# Настройки страницы Streamlit
st.set_page_config(page_title="Tiny Friends Analytics", layout="wide")

st.title("📊 Tiny Friends (User Acquisition & Attribution)")

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
    default=["Installs", "Spend ($)", "CPI ($)", "RR D1 (%)", "Total Revenue ($)", "ROAS (%)"]
)

if len(date_range) == 2:
    start_date, end_date = date_range
    start_str = f"{start_date} 00:00:00"
    end_str = f"{end_date} 23:59:59"
    
    try:
        # --- 1. Запросы к БД ---
        mmp_res = supabase.table("mmp") \
            .select("*") \
            .gte("created_at", start_str) \
            .lte("created_at", end_str) \
            .execute()
            
        ad_res = supabase.table("mmp_ad_revenue_events").select("*").execute()
        
        spend_res = supabase.table("ad_spend") \
            .select("campaign_name, ad_network, spend") \
            .gte("date", str(start_date)) \
            .lte("date", str(end_date)) \
            .execute()

        df_mmp = pd.DataFrame(mmp_res.data) if mmp_res.data else pd.DataFrame()
        df_ad = pd.DataFrame(ad_res.data) if ad_res.data else pd.DataFrame()
        df_spend = pd.DataFrame(spend_res.data) if spend_res.data else pd.DataFrame()

        if df_mmp.empty and df_spend.empty:
            st.info("За выбранный период нет данных ни по установкам, ни по расходам.")
        else:
            # --- 2. Обработка данных MMP ---
            if not df_mmp.empty:
                df_mmp['install_date'] = pd.to_datetime(df_mmp['created_at']).dt.date
                df_mmp['ad_network'] = df_mmp['ad_network'].fillna('Organic')
                df_mmp['campaign_name'] = df_mmp['campaign_name'].fillna('Organic')
                
                if 'creative_name' in df_mmp.columns:
                    df_mmp['creative_name'] = df_mmp['creative_name'].fillna('None')
                else:
                    df_mmp['creative_name'] = 'None'
                
                # Retention Rate
                install_dt = pd.to_datetime(df_mmp['created_at'], errors='coerce')
                last_sess_dt = pd.to_datetime(df_mmp['last_session_date'], errors='coerce').fillna(install_dt)
                days_diff = (last_sess_dt.dt.date - install_dt.dt.date).apply(lambda x: x.days if pd.notnull(x) else 0)
                
                df_mmp['RR D1 (%)'] = (days_diff >= 1).astype(int) * 100
                df_mmp['RR D3 (%)'] = (days_diff >= 3).astype(int) * 100
                df_mmp['RR D7 (%)'] = (days_diff >= 7).astype(int) * 100
                
                # Ad Revenue
                if not df_ad.empty:
                    ad_by_iid = df_ad.groupby('iid')['revenue'].sum().reset_index().rename(columns={'revenue': 'Ad Revenue ($)'})
                    df_mmp = df_mmp.merge(ad_by_iid, on='iid', how='left')
                    df_mmp['Ad Revenue ($)'] = df_mmp['Ad Revenue ($)'].fillna(0.0)
                else:
                    df_mmp['Ad Revenue ($)'] = 0.0

                # IAP Revenue
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

                # Полная агрегация MMP ВСЕГДА всех полей
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
                grouped_mmp = df_mmp.groupby(selected_dimensions, as_index=False).agg(agg_rules)
            else:
                grouped_mmp = pd.DataFrame(columns=selected_dimensions + ['Installs', 'RR D1 (%)', 'RR D3 (%)', 'RR D7 (%)', 'Ad Revenue ($)', 'IAP Revenue ($)', 'Total Revenue ($)', 'Avg Sessions'])

            # --- 3. Обработка Расходов (Ad Spend) ---
            spend_dims = [d for d in selected_dimensions if d in ['ad_network', 'campaign_name']]
            
            if not df_spend.empty and spend_dims:
                spend_grouped = df_spend.groupby(spend_dims, as_index=False)['spend'].sum().rename(columns={'spend': 'Spend ($)'})
            else:
                spend_grouped = pd.DataFrame(columns=spend_dims + ['Spend ($)'])

            # --- 4. Объединение MMP и Расходов через outer join ---
            if spend_grouped.empty or not spend_dims:
                grouped_df = grouped_mmp
                grouped_df['Spend ($)'] = 0.0
            elif grouped_mmp.empty:
                grouped_df = spend_grouped
                for col in ['Installs', 'Ad Revenue ($)', 'IAP Revenue ($)', 'Total Revenue ($)', 'RR D1 (%)', 'RR D3 (%)', 'RR D7 (%)', 'Avg Sessions']:
                    grouped_df[col] = 0.0
            else:
                grouped_df = pd.merge(grouped_mmp, spend_grouped, on=spend_dims, how='outer')
                grouped_df['Spend ($)'] = grouped_df['Spend ($)'].fillna(0.0)

            # Восстановление пропущенных значении
            for dim in selected_dimensions:
                if dim in grouped_df.columns:
                    grouped_df[dim] = grouped_df[dim].fillna('Organic')

            numeric_cols = ['Installs', 'Ad Revenue ($)', 'IAP Revenue ($)', 'Total Revenue ($)', 'RR D1 (%)', 'RR D3 (%)', 'RR D7 (%)', 'Avg Sessions']
            for col in numeric_cols:
                if col in grouped_df.columns:
                    grouped_df[col] = grouped_df[col].fillna(0.0)

            # --- 5. Вычисление CPI и ROAS ---
            grouped_df['CPI ($)'] = grouped_df.apply(
                lambda r: round(r['Spend ($)'] / r['Installs'], 2) if r['Installs'] > 0 else 0.0, axis=1
            )
            
            grouped_df['ROAS (%)'] = grouped_df.apply(
                lambda r: round((r['Total Revenue ($)'] / r['Spend ($)']) * 100, 1) if r['Spend ($)'] > 0 else 0.0, axis=1
            )

            # --- 6. Форматирование вывода ---
            display_df = grouped_df.copy()
            
            for col in ['Ad Revenue ($)', 'IAP Revenue ($)', 'Total Revenue ($)', 'Spend ($)']:
                if col in display_df.columns:
                    display_df[col] = display_df[col].round(2)

            for col in ['RR D1 (%)', 'RR D3 (%)', 'RR D7 (%)', 'ROAS (%)']:
                if col in display_df.columns:
                    display_df[col] = display_df[col].round(1).astype(str) + " %"

            if 'Avg Sessions' in display_df.columns:
                display_df['Avg Sessions'] = display_df['Avg Sessions'].round(1)

            if 'Installs' in display_df.columns:
                display_df['Installs'] = display_df['Installs'].astype(int)

            # Пересечение выбранных столбцов для отображения
            final_cols = [c for c in selected_dimensions + selected_metrics if c in display_df.columns]
            
            st.subheader("Результаты анализа")
            st.dataframe(display_df[final_cols], use_container_width=True)

    except Exception as e:
        st.error(f"Ошибка выполнения запроса: {e}")
else:
    st.info("Выберите диапазон дат в левой панели для загрузки отчета.")