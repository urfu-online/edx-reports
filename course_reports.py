# course_reports.py
import os
import re
import logging
import requests
import pandas as pd
from datetime import datetime, timezone
from typing import List, Dict, Any

# === НАСТРОЙКИ ===
BASE_URL = "https://courses.openedu.urfu.ru"
GRADES_DIR = os.path.join(os.environ.get("TUTOR_ROOT", "../.."), "data/openedx-media/grades")
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

# === API ===
def get_all_courses() -> List[Dict[str, Any]]:
    """Получает список всех курсов с платформы"""
    logger.info("Начало загрузки списка курсов")
    courses = []
    page = 1
    session = requests.Session()
    while True:
        params = {"page": page, "page_size": 100}
        r = session.get(f"{BASE_URL}/api/courses/v1/courses/", params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        logger.debug(f"Получена страница {page} с {len(data.get('results', []))} курсами")
        courses.extend(data.get("results", []))
        if not data.get("next"):
            logger.info(f"Загрузка курсов завершена. Всего курсов: {len(courses)}")
            break
        page += 1
    return courses

def extract_course_short_id(course_id: str) -> str:
    """Приводим course_id к формату файлов, например course-v1:UrFU+PYTHON+2025_fall -> UrFU_PYTHON_2025_fall"""
    logger.debug(f"Извлечение короткого ID для курса: {course_id}")
    m = re.match(r"course-v1:(.*?)\+(.*?)\+(.*)", course_id)
    if not m:
        logger.warning(f"Не удалось извлечь короткий ID для курса: {course_id}")
        return course_id
    short_id = f"{m[1]}_{m[2]}_{m[3]}"
    logger.debug(f"Короткий ID курса: {short_id}")
    return short_id

def extract_course_run(course_id: str) -> str:
    """Извлекаем запуск курса (RUN), например 2025_fall"""
    logger.debug(f"Извлечение запуска курса: {course_id}")
    run = course_id.split("+")[-1]
    logger.debug(f"Запуск курса: {run}")
    return run

# === Локальный разбор файлов ===
def parse_filename(filename: str):
    """Парсит имя файла отчета"""
    logger.debug(f"Парсинг имени файла: {filename}")
    m = re.match(r"(.*?)_(grade_report|student_profile_info|may_enroll_info|anonymized_ids|ORA_data)_(\d{4}-\d{2}-\d{2}-\d{4})\.csv", filename)
    if not m:
        logger.warning(f"Не удалось распарсить имя файла: {filename}")
        return None
    course, report_type, date_str = m.groups()
    try:
        report_dt = datetime.strptime(date_str, "%Y-%m-%d-%H%M").replace(tzinfo=timezone.utc)
        logger.info(f"Файл {filename} успешно распарсен: курс={course}, тип={report_type}, дата={report_dt}")
    except Exception as e:
        logger.error(f"Ошибка при парсинге даты из файла {filename}: {e}")
        report_dt = None
    return {
        "course_id": course,
        "report_type": report_type,
        "date": report_dt,
    }

def scan_grade_reports(base_dir: str):
    logger.info(f"Начало сканирования директории отчетов: {base_dir}")
    rows = []
    file_count = 0
    for root, _, files in os.walk(base_dir):
        for f in files:
            file_count += 1
            parsed = parse_filename(f)
            if parsed:
                parsed["path"] = os.path.join(root, f)
                rows.append(parsed)
    logger.info(f"Сканирование завершено. Обработано файлов: {file_count}, найдено отчетов: {len(rows)}")
    # Если отчеты не найдены, возвращаем пустой DataFrame с правильными колонками
    if not rows:
        return pd.DataFrame(columns=["course_id", "report_type", "date", "path"])
    return pd.DataFrame(rows)

def process_courses_data(courses, df_reports):
    """Обрабатывает данные курсов и отчетов для отображения в таблице"""
    data = []
    now = datetime.now(timezone.utc)
    
    for course in courses:
        cid_api = course["id"]
        cid_short = extract_course_short_id(cid_api)
        cname = course["name"]
        run = extract_course_run(cid_api)
        
        # все отчеты по курсу
        reports = df_reports[df_reports["course_id"] == cid_short] if not df_reports.empty else pd.DataFrame(columns=["course_id", "report_type", "date", "path"])
        
        for rtype in ["grade_report", "student_profile_info", "may_enroll_info", "anonymized_ids", "ORA_data"]:
            sub = reports[reports["report_type"] == rtype]

            logger.info(f"Обработка курса {cid_short}, тип отчета {rtype}, найдено отчетов: {len(sub)}")
            if not sub.empty:
                sub_sorted = sub.sort_values("date", ascending=False)
                last = sub_sorted.iloc[0]
                date = last["date"]
                days = (now - date).days
                path = last["path"]
                logger.debug(f"Последний отчет для {cid_short} ({rtype}): {date}, {days} дней назад")

                data.append({
                    "Название курса": cname,
                    "Курс": cid_short,
                    "Запуск курса": run,
                    "Тип отчета": rtype,
                    "Последний отчет": date.strftime("%Y-%m-%d %H:%M") if date else "—",
                    "Дней с отчета": days if days is not None else None,
                    "Файл": path,
                })
                
            else:
                date = None
                days = None
                path = None
                logger.debug(f"Для курса {cid_short} ({rtype}) отчеты не найдены")
            
            
    
    return pd.DataFrame(data)