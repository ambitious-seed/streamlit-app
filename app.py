import streamlit as st
import pandas as pd
from supabase import create_client

# 1. Подключение к Supabase
SUPABASE_URL = "https://zxzcywphwkviqbbfgkpr.supabase.co"
# Убедитесь, что тут вставлен service_role key или настроен GRANT SELECT
SUPABASE_KEY = "sb_publishable_K-PXcgoZCnW_Vemg8Q_baQ_Wn7YAblg"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("📊 Аналитика приложения")

# 2. Фильтр по датам
date_range = st.date_input("Выберите период", [])

if len(date_range) == 2:
    start_date, end_date = date_range
    
    # Преобразуем даты в формат ISO (с началом и концом суток)
    start_str = f"{start_date}T00:00:00.000Z"
    end_str = f"{end_date}T23:59:59.999Z"
    
    st.info(f"Запрос данных с {start_date} по {end_date}...")
    
    try:
        # Запрос к базе Supabase
        response = supabase.table("mmp_ad_revenue_events") \
            .select("*") \
            .gte("created_at", start_str) \
            .lte("created_at", end_str) \
            .execute()
        
        data = response.data
        
        if data:
            df = pd.DataFrame(data)
            
            # Отрисовываем общее количество записей и доход
            st.success(f"Найдено записей: {len(df)}")
            
            if 'revenue' in df.columns:
                total_rev = df['revenue'].sum()
                st.metric("Общий доход от рекламы", f"${total_rev:.4f}")
            
            # Таблица с данными
            st.subheader("Сырые данные")
            st.dataframe(df)
            
            # График по дням (если есть колонка revenue)
            if 'revenue' in df.columns and 'created_at' in df.columns:
                df['created_at'] = pd.to_datetime(df['created_at'])
                daily_rev = df.groupby(df['created_at'].dt.date)['revenue'].sum()
                st.subheader("График дохода по дням")
                st.line_chart(daily_rev)
        else:
            st.warning("В базе нет данных за выбранный период времени.")
            
    except Exception as e:
        st.error(f"Ошибка при запросе к Supabase: {e}")
