# reports.py (Streamlit interface)
import os
import logging
import pandas as pd
import streamlit as st
from datetime import datetime, timezone
from course_reports import (
    get_all_courses, 
    scan_grade_reports, 
    process_courses_data,
    GRADES_DIR
)

# === НАСТРОЙКИ ===
DAYS_OK = 5

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('reports.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# === STREAMLIT ===
st.set_page_config("Отчеты по курсам Open edX", layout="wide")
st.title("📊 Отчеты по курсам Open edX")

# Получаем курсы
with st.spinner("Загружаем список курсов..."):
    try:
        courses = get_all_courses()
        logger.info(f"Успешно загружено {len(courses)} курсов")
    except Exception as e:
        logger.error(f"Ошибка загрузки курсов: {e}")
        st.error(f"Ошибка загрузки курсов: {e}")
        st.stop()

df_reports = scan_grade_reports(GRADES_DIR)
logger.info(f"Сканирование завершено. Обработано файлов: {len(df_reports)}, найдено отчетов: {len(df_reports)}")

# Обрабатываем данные курсов и отчетов
df_all = process_courses_data(courses, df_reports)

# === Фильтры ===
st.sidebar.header("🔍 Фильтры")
course_options = ["Все"] + sorted(df_all["Название курса"].unique().tolist())
selected_course = st.sidebar.selectbox("Курс", course_options)

type_options = ["Все"] + sorted(df_all["Тип отчета"].unique().tolist())
selected_type = st.sidebar.selectbox("Тип отчета", type_options)

run_options = ["Все"] + sorted(df_all["Запуск курса"].unique().tolist())
selected_run = st.sidebar.selectbox("Запуск курса", run_options)

max_days = int(df_all["Дней с отчета"].max() if df_all["Дней с отчета"].dropna().any() else 0)
selected_days = st.sidebar.slider("Макс. дней с отчета", 0, max_days if max_days>0 else 30, max_days if max_days>0 else 100)

# Применяем фильтры
filtered = df_all.copy()
if selected_course != "Все":
    filtered = filtered[filtered["Название курса"] == selected_course]
if selected_type != "Все":
    filtered = filtered[filtered["Тип отчета"] == selected_type]
if selected_run != "Все":
    filtered = filtered[filtered["Запуск курса"] == selected_run]

filtered = filtered[
    filtered["Дней с отчета"].apply(lambda x: x is None or x <= selected_days)
]
logger.info(f"Применены фильтры. Отобрано записей: {len(filtered)}")

# === Таблица с информацией и кнопками скачивания ===
st.markdown("### 📋 Сводная информация по отчетам")

# Подготовка данных для таблицы
# Создадим копию данных и добавим столбец для отображения цвета дней
table_data = filtered.copy()

# Функция для определения цвета ячейки "Дней с отчета"
def color_days(days):
    if pd.isna(days):
        return "—"
    elif days <= DAYS_OK:
        return f"<span style='color: green; font-weight: bold;'>{int(days)} дн.</span>"
    else:
        return f"<span style='color: red; font-weight: bold;'>{int(days)} дн.</span>"

# Функция для генерации HTML кнопки скачивания
def create_download_button(file_path):
    if file_path and os.path.exists(file_path):
        # Создаем уникальный ключ для кнопки
        button_key = f"download_{hash(file_path) % 1000000}"
        file_name = os.path.basename(file_path)
        return f'<a href="?file={file_path}" target="_blank" download="{file_name}"><button style="background-color: #4CAF50; color: white; padding: 8px 16px;border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">📥 Скачать</button></a>'
    else:
        return "<span style='color: gray;'>Нет файла</span>"

# Применяем функцию к столбцу "Дней с отчета"
table_data["Дней с отчета"] = table_data["Дней с отчета"].apply(color_days)

# Добавляем столбец с кнопками скачивания
table_data["Скачать"] = table_data["Файл"].apply(create_download_button)

# Отображение таблицы
st.write(
    table_data[["Название курса", "Курс", "Запуск курса", "Тип отчета", "Последний отчет", "Дней с отчета", "Скачать"]].to_html(escape=False),
    unsafe_allow_html=True,
)

st.caption(f"🟢 Зелёный — отчёт моложе {DAYS_OK} дней. 🔴 Красный — старше.")
