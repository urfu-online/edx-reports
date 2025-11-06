#!/usr/bin/env python3
"""
Скрипт для генерации отчетов об оценках через OpenEdX Instructor API
Использует рабочую авторизацию как в connect.py
"""

import os
import requests
import logging
import time
import json
import urllib.parse
from typing import List, Dict, Any, Tuple
from dotenv import load_dotenv
from requests.exceptions import RequestException

# -----------------------------
# Настройка логгера
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# -----------------------------
# Загрузка переменных окружения
# -----------------------------
load_dotenv()

# -----------------------------
# Глобальные переменные
# -----------------------------
BASE_URL = os.getenv("OPENEDU_BASE_URL", "https://courses.openedu.urfu.ru").rstrip("/")
USERNAME = os.getenv("OPENEDU_USERNAME")
PASSWORD = os.getenv("OPENEDU_PASSWORD")

# Проверка обязательных переменных
missing_vars = []
if not BASE_URL:
    missing_vars.append("OPENEDU_BASE_URL")
if not USERNAME or not PASSWORD:
    missing_vars.append("OPENEDU_USERNAME/OPENEDU_PASSWORD")
if missing_vars:
    raise ValueError(f"Не заданы обязательные переменные окружения: {', '.join(missing_vars)}")

# -----------------------------
# Вспомогательные функции
# -----------------------------

def log_request_details(request: requests.PreparedRequest):
    """Логирование деталей запроса для отладки"""
    logger.debug(f"URL: {request.url}")
    logger.debug(f"Method: {request.method}")
    logger.debug(f"Headers: {json.dumps(dict(request.headers), indent=2)}")
    if request.body:
        body_content = request.body.decode() if isinstance(request.body, bytes) else request.body
        logger.debug(f"Body: {body_content[:500]}{'...' if len(body_content) > 500 else ''}")

def log_response_details(response: requests.Response):
    """Логирование деталей ответа для отладки"""
    logger.debug(f"Status Code: {response.status_code}")
    logger.debug(f"Response Headers: {json.dumps(dict(response.headers), indent=2)}")
    logger.debug(f"Response Text: {response.text[:500]}{'...' if len(response.text) > 500 else ''}")

def sanitize_course_id(course_id: str) -> str:
    """Очищает ID курса от пробелов и некорректных символов"""
    if not course_id:
        return course_id
    
    # Удаляем все пробелы и лишние символы
    cleaned = ''.join(course_id.split())
    
    # Исправляем формат
    cleaned = cleaned.replace("::", ":").replace("coursev1", "course-v1")
    
    # URL encode для безопасности
    cleaned = urllib.parse.quote(cleaned, safe=':/+')
    
    return cleaned

def create_session_with_login() -> requests.Session:
    """
    Создает сессию с аутентификацией через /login_ajax как в connect.py
    ИСПРАВЛЕНО: теперь использует email, а не username для аутентификации
    """
    logger.info("Создание сессии с аутентификацией через /login_ajax")
    
    # Создаем новую сессию
    session = requests.Session()
    
    # Устанавливаем базовые заголовки, имитирующие браузер
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    })
    
    try:
        # Шаг 1: Получаем главную страницу для установки начальных cookies
        logger.debug("Получение главной страницы для установки cookies")
        homepage_response = session.get(BASE_URL, timeout=30)
        
        # Извлекаем CSRF-токен из cookies
        csrftoken = session.cookies.get('csrftoken')
        if not csrftoken:
            logger.warning("CSRF-токен не найден в cookies после загрузки главной страницы")
            # Попытка получить CSRF через API
            csrf_url = f"{BASE_URL}/csrf/api/v1/token"
            csrf_response = session.get(csrf_url, headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": BASE_URL + "/"
            }, timeout=30)
            
            if csrf_response.status_code == 200:
                csrf_data = csrf_response.json()
                csrftoken = csrf_data.get("csrf_token") or csrf_data.get("csrfToken")
                if csrftoken:
                    session.cookies.set('csrftoken', csrftoken, domain='courses.openedu.urfu.ru', path='/')
                    logger.info(f"✅ CSRF-токен получен через API: {csrftoken[:10]}...")
                else:
                    raise Exception("CSRF-токен не найден в ответе API")
            else:
                raise Exception(f"Ошибка получения CSRF через API. Статус: {csrf_response.status_code}")
        
        logger.info(f"✅ CSRF-токен получен: {csrftoken[:10]}...")
        
        # Шаг 2: Отправляем данные для входа как в connect.py
        logger.debug("Отправка данных для аутентификации через /login_ajax")
        login_post_url = f"{BASE_URL}/login_ajax"
        
        # КРИТИЧЕСКИЙ ИСПРАВЛЕНИЕ: используем email вместо username
        # В OpenEdX с Keycloak требуется email для аутентификации
        email = USERNAME
        if '@' not in USERNAME:
            # Если в USERNAME нет @, добавляем домен
            email = f"{USERNAME}@urfu.online"
            logger.info(f"ℹ️ Используем email для аутентификации: {email}")
        
        # Подготовка данных для входа
        login_data = {
            "email": email,  # ИСПРАВЛЕНО: используем email вместо username
            "password": PASSWORD,
            "remember": False
        }
        
        # Заголовки для запроса входа (как в connect.py)
        login_headers = {
            "Referer": f"{BASE_URL}/login",
            "X-CSRFToken": csrftoken,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE_URL
        }
        
        login_response = session.post(
            login_post_url,
            data=login_data,
            headers=login_headers,
            timeout=30
        )
        
        logger.debug(f"Статус ответа входа: {login_response.status_code}")
        logger.debug(f"Тело ответа входа: {login_response.text[:500]}")
        
        if login_response.status_code not in [200, 201]:
            error_msg = login_response.text
            try:
                error_json = login_response.json()
                error_msg = error_json.get("value", error_json.get("error", login_response.text))
            except:
                pass
            logger.error(f"❌ Ошибка входа. Статус: {login_response.status_code}, Ошибка: {error_msg}")
            # Дополнительная отладка для ошибки "Unknown user email or username"
            if "Unknown user email or username" in error_msg:
                logger.error("❗ В OpenEdX с Keycloak требуется использовать email-адрес для входа")
                logger.error(f"❗ Попробуйте использовать email вместо username: {USERNAME}@urfu.online")
            raise Exception(f"Не удалось выполнить вход: {error_msg}")
        
        try:
            login_result = login_response.json()
            if not login_result.get("success", False):
                error_value = login_result.get("value", "Неизвестная ошибка аутентификации")
                logger.error(f"❌ Ошибка входа: {error_value}")
                # Дополнительная проверка для ошибки с email
                if "неверный адрес электронной почты" in error_value.lower():
                    logger.error("❗ Требуется использовать email-адрес вместо имени пользователя")
                    logger.error(f"❗ Используйте: {USERNAME}@urfu.online")
                raise Exception(f"Ошибка входа: {error_value}")
        except json.JSONDecodeError:
            logger.warning("⚠️ Не удалось распарсить ответ о входе как JSON, но статус 200")
        
        logger.info("✅ Успешный вход в систему")
        
        # Проверяем наличие критически важных cookie
        required_cookies = ['edx-jwt-cookie-header-payload', 'edx-jwt-cookie-signature', 'sessionid', 'csrftoken']
        missing_cookies = [cookie for cookie in required_cookies if cookie not in session.cookies]
        
        if missing_cookies:
            logger.warning("⚠️ Отсутствуют критически важные cookie для instructor API:")
            for cookie in missing_cookies:
                logger.warning(f"  - {cookie}")
        else:
            logger.info("✅ Все необходимые cookie получены")
        
        # Шаг 3: Обновляем заголовки для API запросов (как в connect.py)
        session.headers.update({
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",  # ИСПРАВЛЕНО: правильный Content-Type
            "USE-JWT-COOKIE": "true",  # Критически важный заголовок для JWT cookie авторизации
            "Origin": BASE_URL,
            "X-CSRFToken": csrftoken
        })
        
        # Удаляем Authorization заголовок, так как используем cookie авторизацию
        if "Authorization" in session.headers:
            del session.headers["Authorization"]
            logger.debug("🗑️ Удален заголовок Authorization (используется cookie-авторизация)")
        
        logger.info("✅ Сессия с аутентификацией успешно создана")
        return session
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания сессии с аутентификацией: {str(e)}", exc_info=True)
        raise

def get_user_info(session: requests.Session) -> Dict[str, Any]:
    """
    Получает информацию о пользователе из API
    """
    try:
        # Попытка 1: Стандартный endpoint
        user_url = f"{BASE_URL}/api/user/v1/me"
        response = session.get(user_url, timeout=30)
        
        if response.status_code == 200:
            try:
                user_info = response.json()
                logger.info(f"✅ Информация о пользователе получена: {user_info.get('username')}")
                logger.info(f"Права пользователя: staff={user_info.get('is_staff', False)}, superuser={user_info.get('is_superuser', False)}")
                return user_info
            except json.JSONDecodeError:
                logger.warning("⚠️ Не удалось распарсить ответ о пользователе")
        
        # Попытка 2: Страница профиля
        profile_url = f"{BASE_URL}/u/{USERNAME}"
        profile_response = session.get(profile_url, timeout=30)
        if profile_response.status_code == 200:
            logger.info("✅ Пользователь имеет доступ к странице профиля, вероятно имеет права staff")
            return {"username": USERNAME, "is_staff": True, "is_superuser": False}
        
        # Попытка 3: Админка
        admin_url = f"{BASE_URL}/admin/"
        admin_response = session.get(admin_url, timeout=30)
        if admin_response.status_code == 200:
            logger.info("✅ Пользователь имеет доступ к админке - права подтверждены")
            return {"username": USERNAME, "is_staff": True, "is_superuser": True}
        
        logger.warning("⚠️ Не удалось определить права пользователя, предполагаем базовые права")
        return {"username": USERNAME, "is_staff": False, "is_superuser": False}
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения информации о пользователе: {str(e)}", exc_info=True)
        return {"username": USERNAME, "is_staff": False, "is_superuser": False}

def get_all_courses(session: requests.Session) -> List[Dict[str, Any]]:
    """
    Получает список всех курсов
    """
    logger.info("📚 Получение списка всех курсов")
    
    try:
        courses = []
        page = 1
        has_more = True
        
        while has_more:
            url = f"{BASE_URL}/api/courses/v1/courses/"
            params = {
                "page": page,
                "page_size": 100
            }
            
            logger.debug(f"Запрос курсов, страница {page}")
            response = session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    results = data.get("results", [])
                    if not results:
                        break
                    
                    courses.extend(results)
                    logger.info(f"✅ Добавлено {len(results)} курсов. Всего: {len(courses)}")
                    
                    # Проверяем, есть ли следующая страница
                    next_page = data.get("next")
                    if not next_page or page >= 10:  # Максимум 10 страниц
                        has_more = False
                    else:
                        page += 1
                except json.JSONDecodeError:
                    logger.error("❌ Не удалось распарсить ответ с курсами")
                    break
            else:
                logger.warning(f"⚠️ Не удалось получить курсы. Статус: {response.status_code}")
                break
        
        logger.info(f"✅ Итоговое количество курсов для обработки: {len(courses)}")
        return courses
    
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при получении списка курсов: {str(e)}", exc_info=True)
        return []

def generate_grade_report(session: requests.Session, course_id: str, course_name: str = "") -> Dict[str, Any]:
    """
    Генерирует отчет об оценках для указанного курса
    """
    # Очищаем ID курса
    clean_course_id = sanitize_course_id(course_id)
    logger.info(f"📊 Генерация отчёта об оценках для курса: {course_name} ({clean_course_id})")
    
    try:
        # Убеждаемся, что у нас есть свежий CSRF-токен
        csrftoken = session.cookies.get('csrftoken')
        if not csrftoken:
            logger.warning("⚠️ CSRF-токен отсутствует в сессии, выполняем повторный GET запрос")
            session.get(BASE_URL, timeout=30)
            csrftoken = session.cookies.get('csrftoken')
        
        if not csrftoken:
            raise Exception("❌ CSRF-токен недоступен даже после обновления сессии")
        
        # URL для генерации отчета
        url = f"{BASE_URL}/courses/{clean_course_id}/instructor/api/calculate_grades_csv"
        
        # Заголовки для запроса (как в connect.py)
        headers = {
            "X-CSRFToken": csrftoken,
            "Referer": f"{BASE_URL}/courses/{clean_course_id}/instructor",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",  # ИСПРАВЛЕНО
            "USE-JWT-COOKIE": "true",
            "Origin": BASE_URL
        }
        
        logger.debug(f"📤 Отправка запроса на генерацию отчета для курса {clean_course_id}")
        logger.debug(f"🔗 URL: {url}")
        
        # Выполняем POST запрос для генерации отчета
        response = session.post(url, headers=headers, data={}, timeout=300)
        
        # Логируем детали для отладки
        log_request_details(response.request)
        log_response_details(response)
        
        # Проверяем статус ответа
        if response.status_code != 200:
            logger.error(f"❌ Ошибка при генерации отчёта для {clean_course_id}. Статус: {response.status_code}")
            if response.status_code == 403:
                logger.error("🔍 Детальная диагностика ошибки 403 Forbidden:")
                logger.error(f"- URL запроса: {response.request.url}")
                logger.error(f"- Заголовки запроса: {dict(response.request.headers)}")
                logger.error(f"- Cookies сессии: {list(session.cookies.keys())}")
                logger.error(f"- Наличие необходимых cookie:")
                logger.error(f"  * csrftoken: {'csrftoken' in session.cookies}")
                logger.error(f"  * edx-jwt-cookie-header-payload: {'edx-jwt-cookie-header-payload' in session.cookies}")
                logger.error(f"  * edx-jwt-cookie-signature: {'edx-jwt-cookie-signature' in session.cookies}")
                logger.error(f"  * sessionid: {'sessionid' in session.cookies}")
                
                # Проверяем права пользователя
                user_info = get_user_info(session)
                logger.error(f"- Права пользователя: staff={user_info.get('is_staff', False)}, superuser={user_info.get('is_superuser', False)}")
                
                logger.error("ℹ️  Для работы с instructor API необходимы права инструктора или администратора курса")
            
            response.raise_for_status()
        
        try:
            result = response.json()
            task_status = result.get("task_status", "unknown")
            task_id = result.get("task_id", "unknown")
            logger.info(f"✅ Успешная генерация отчёта для {clean_course_id}. Статус задачи: {task_status}, ID задачи: {task_id}")
            return result
        except json.JSONDecodeError:
            logger.warning("⚠️ Ответ не является JSON, но запрос был успешным")
            return {"status": "success", "message": "Отчет успешно поставлен в очередь на генерацию"}
    
    except RequestException as e:
        if e.response is not None:
            status_code = e.response.status_code
            error_text = e.response.text[:500]
            logger.error(f"❌ Ошибка при генерации отчёта для {clean_course_id}. "
                         f"Статус: {status_code}, Тело ответа: {error_text}")
        else:
            logger.error(f"❌ Сетевая ошибка при генерации отчёта для {clean_course_id}: {str(e)}")
        
        raise
    
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при генерации отчёта для {clean_course_id}: {str(e)}", exc_info=True)
        raise

def retry_operation(operation, max_retries=2, delay=5):
    """
    Повторяет операцию при возникновении ошибок
    """
    for attempt in range(max_retries):
        try:
            return operation()
        except Exception as e:
            logger.warning(f"🔄 Попытка {attempt + 1}/{max_retries} не удалась: {str(e)}")
            if attempt < max_retries - 1:
                logger.info(f"⏱️ Повтор через {delay} секунд...")
                time.sleep(delay)
                delay *= 2  # Экспоненциальная задержка
            else:
                logger.error("❌ Все попытки исчерпаны")
                raise

def main():
    """
    Основная функция скрипта
    """
    try:
        logger.info("=" * 70)
        logger.info("🚀 ЗАПУСК СКРИПТА ГЕНЕРАЦИИ ОТЧЕТОВ ОБ ОЦЕНКАХ")
        logger.info("=" * 70)
        logger.info(f"🌐 Базовый URL: {BASE_URL}")
        logger.info(f"👤 Пользователь: {USERNAME}")
        logger.info(f"📧 Для аутентификации будет использован email: {USERNAME}@urfu.online")
        
        # Шаг 1: Аутентификация через /login_ajax
        logger.info("\n" + "-" * 70)
        logger.info("🔐 Шаг 1: Аутентификация через /login_ajax")
        logger.info("-" * 70)
        
        session = create_session_with_login()
        logger.info("✅ Сессия успешно создана")
        
        # Шаг 2: Получение информации о пользователе
        logger.info("\n" + "-" * 70)
        logger.info("👤 Шаг 2: Получение информации о пользователе")
        logger.info("-" * 70)
        
        user_info = get_user_info(session)
        username = user_info.get("username", "unknown")
        is_staff = user_info.get("is_staff", False)
        is_superuser = user_info.get("is_superuser", False)
        
        logger.info(f"✅ Аутентифицирован пользователь: {username}")
        logger.info(f"🔑 Права пользователя: staff={is_staff}, superuser={is_superuser}")
        
        if not (is_staff or is_superuser):
            logger.warning("⚠️ ПРЕДУПРЕЖДЕНИЕ: Пользователь не имеет прав staff/superuser. Некоторые операции могут завершиться ошибкой.")
            logger.warning("ℹ️  Для генерации отчетов об оценках требуются права инструктора или администратора курса")
        
        # Шаг 3: Получение списка курсов
        logger.info("\n" + "-" * 70)
        logger.info("📚 Шаг 3: Получение списка курсов")
        logger.info("-" * 70)
        
        courses = get_all_courses(session)
        
        if not courses:
            logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: Не найдено ни одного курса для обработки")
            return 1
        
        logger.info(f"✅ Найдено курсов для обработки: {len(courses)}")
        
        # Шаг 4: Генерация отчетов для каждого курса
        logger.info("\n" + "-" * 70)
        logger.info("📊 Шаг 4: Генерация отчетов для каждого курса")
        logger.info("-" * 70)
        
        success_count = 0
        failure_count = 0
        
        for i, course in enumerate(courses, 1):
            course_id = course.get("id")
            course_name = course.get("name", "Безымянный курс")
            
            if not course_id:
                logger.warning(f"⚠️ Пропуск курса без ID: {course_name}")
                continue
            
            logger.info(f"\n📖 Курс {i}/{len(courses)}: {course_name} ({course_id})")
            
            try:
                # Генерация отчета
                result = retry_operation(
                    lambda cid=course_id, cname=course_name: generate_grade_report(session, cid, cname),
                    max_retries=2,
                    delay=5
                )
                success_count += 1
                logger.info(f"✅ Отчет успешно сгенерирован для курса: {course_name}")
                
                # Пауза между запросами
                if i < len(courses):
                    time.sleep(2)
                    
            except Exception as e:
                failure_count += 1
                logger.error(f"❌ Не удалось сгенерировать отчет для курса {course_name} ({course_id}): {str(e)}")
                continue
        
        # Итоговая статистика
        logger.info("\n" + "=" * 70)
        logger.info("✅ ГЕНЕРАЦИЯ ОТЧЕТОВ ЗАВЕРШЕНА")
        logger.info("=" * 70)
        logger.info(f"✅ Успешно обработано курсов: {success_count}")
        logger.info(f"❌ Не удалось обработать курсов: {failure_count}")
        logger.info(f"📊 Всего курсов: {len(courses)}")
        logger.info("=" * 70)
        
        # Если все операции завершились неудачей, выходим с ошибкой
        if failure_count == len(courses) and courses:
            return 1
        
        return 0
    
    except Exception as e:
        logger.critical(f"❌ КРИТИЧЕСКАЯ ОШИБКА выполнения скрипта: {str(e)}", exc_info=True)
        return 1
    
    finally:
        logger.info("🛑 Скрипт завершил работу")

if __name__ == "__main__":
    # Запускаем скрипт и выходим с соответствующим кодом
    exit(main())