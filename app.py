import streamlit as st
import pandas as pd
from supabase import create_client

# Подключение к Supabase
SUPABASE_URL = "https://zxzcywphwkviqbbfgkpr.supabase.co"
SUPABASE_KEY = "sb_publishable_K-PXcgoZCnW_Vemg8Q_baQ_Wn7YAblg"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("📊 Аналитика приложения")

# Фильтр по датам
date_range = st.date_input("Выберите период", [])

if len(date_range) == 2:
    start_date, end_date = date_range
    
    # Запрос данных из таблицы рекламы
    response = supabase.table("mmp_ad_revenue_events") \
        .select("*") \
        .gte("created_at", start_date) \
        .lte("created_at", end_date) \
        .execute()
        
    df = pd.DataFrame(response.data)

    if not df.empty:
        # График дохода по дням
        df['created_at'] = pd.to_datetime(df['created_at'])
        daily_rev = df.groupby(df['created_at'].dt.date)['revenue'].sum()
        
        st.subheader("Доход от рекламы по дням")
        st.line_chart(daily_rev)
        
        # Таблица с сырыми данными
        st.subheader("Детализация")
        st.dataframe(df)