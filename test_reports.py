import unittest
from unittest.mock import patch, Mock
import requests
import pandas as pd
from course_reports import get_all_courses, BASE_URL, extract_course_short_id, extract_course_run, parse_filename, scan_grade_reports
import logging
import os

# Отключаем логирование во время тестов
logging.disable(logging.CRITICAL)

class TestGetAllCourses(unittest.TestCase):
    """Тесты для функции get_all_courses"""
    
    def setUp(self):
        """Инициализация перед каждым тестом"""
        self.base_url = f"{BASE_URL}/api/courses/v1/courses/"
        
    @patch('course_reports.requests.Session')
    def test_get_all_courses_single_page(self, mock_session):
        """Тест получения курсов с одной страницы"""
        # Создаем моковые данные
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            'results': [
                {'id': 'course-v1:UrFU+PYTHON+2025_fall', 'name': 'Python Course'},
                {'id': 'course-v1:UrFU+MATH+2025_fall', 'name': 'Math Course'}
            ],
            'next': None
        }
        
        mock_session_instance = Mock()
        mock_session_instance.get.return_value = mock_response
        mock_session.return_value = mock_session_instance

        # Вызываем тестируемую функцию
        courses = get_all_courses()

        # Проверяем результаты
        self.assertEqual(len(courses), 2)
        self.assertEqual(courses[0]['id'], 'course-v1:UrFU+PYTHON+2025_fall')
        self.assertEqual(courses[1]['id'], 'course-v1:UrFU+MATH+2025_fall')
        
        # Проверяем, что был сделан один запрос
        mock_session_instance.get.assert_called_once_with(
            self.base_url,
            params={"page": 1, "page_size": 100},
            timeout=15
        )

    @patch('course_reports.requests.Session')
    def test_get_all_courses_multiple_pages(self, mock_session):
        """Тест получения курсов с нескольких страниц"""
        # Создаем моковые данные для двух страниц
        mock_response_page1 = Mock()
        mock_response_page1.raise_for_status.return_value = None
        mock_response_page1.json.return_value = {
            'results': [
                {'id': 'course-v1:UrFU+PYTHON+2025_fall', 'name': 'Python Course'}
            ],
            'next': f"{self.base_url}?page=2"
        }
        
        mock_response_page2 = Mock()
        mock_response_page2.raise_for_status.return_value = None
        mock_response_page2.json.return_value = {
            'results': [
                {'id': 'course-v1:UrFU+MATH+2025_fall', 'name': 'Math Course'}
            ],
            'next': None
        }
        
        mock_session_instance = Mock()
        mock_session_instance.get.side_effect = [mock_response_page1, mock_response_page2]
        mock_session.return_value = mock_session_instance

        # Вызываем тестируемую функцию
        courses = get_all_courses()

        # Проверяем результаты
        self.assertEqual(len(courses), 2)
        self.assertEqual(courses[0]['id'], 'course-v1:UrFU+PYTHON+2025_fall')
        self.assertEqual(courses[1]['id'], 'course-v1:UrFU+MATH+2025_fall')
        
        # Проверяем, что были сделаны два запроса
        expected_calls = [
            unittest.mock.call(
                self.base_url,
                params={"page": 1, "page_size": 100},
                timeout=15
            ),
            unittest.mock.call(
                self.base_url,
                params={"page": 2, "page_size": 100},
                timeout=15
            )
        ]
        mock_session_instance.get.assert_has_calls(expected_calls)

    @patch('course_reports.requests.Session')
    def test_get_all_courses_http_error(self, mock_session):
        """Тест обработки HTTP ошибки"""
        # Настраиваем мок, чтобы он выбрасывал исключение
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("HTTP Error")
        
        mock_session_instance = Mock()
        mock_session_instance.get.return_value = mock_response
        mock_session.return_value = mock_session_instance

        # Проверяем, что функция выбрасывает исключение при HTTP ошибке
        with self.assertRaises(requests.HTTPError):
            get_all_courses()

    @patch('course_reports.requests.Session')
    def test_get_all_courses_json_error(self, mock_session):
        """Тест обработки ошибки парсинга JSON"""
        # Настраиваем мок, чтобы json() вызвал исключение
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("JSON parse error")
        
        mock_session_instance = Mock()
        mock_session_instance.get.return_value = mock_response
        mock_session.return_value = mock_session_instance

        # Проверяем, что функция выбрасывает исключение при ошибке JSON
        with self.assertRaises(ValueError):
            get_all_courses()

    @patch('course_reports.requests.Session')
    def test_get_all_courses_timeout(self, mock_session):
        """Тест обработки таймаута"""
        # Настраиваем мок, чтобы get() вызвал исключение таймаута
        mock_session_instance = Mock()
        mock_session_instance.get.side_effect = requests.Timeout("Connection timeout")
        mock_session.return_value = mock_session_instance

        # Проверяем, что функция выбрасывает исключение при таймауте
        with self.assertRaises(requests.Timeout):
            get_all_courses()

class TestExtractCourseShortId(unittest.TestCase):
    """Тесты для функции extract_course_short_id"""
    
    def test_extract_course_short_id_valid(self):
        """Тест извлечения короткого ID курса из валидного course_id"""
        course_id = "course-v1:UrFU+PYTHON+2025_fall"
        expected = "UrFU_PYTHON_2025_fall"
        result = extract_course_short_id(course_id)
        self.assertEqual(result, expected)
        
    def test_extract_course_short_id_invalid(self):
        """Тест извлечения короткого ID курса из невалидного course_id"""
        course_id = "invalid_course_id"
        expected = "invalid_course_id"
        result = extract_course_short_id(course_id)
        self.assertEqual(result, expected)

class TestExtractCourseRun(unittest.TestCase):
    """Тесты для функции extract_course_run"""
    
    def test_extract_course_run_valid(self):
        """Тест извлечения запуска курса из валидного course_id"""
        course_id = "course-v1:UrFU+PYTHON+2025_fall"
        expected = "2025_fall"
        result = extract_course_run(course_id)
        self.assertEqual(result, expected)

class TestParseFilename(unittest.TestCase):
    """Тесты для функции parse_filename"""
    
    def test_parse_filename_valid_grade_report(self):
        """Тест парсинга валидного имени файла с отчетом об оценках"""
        filename = "UrFU_PYTHON_2025_fall_grade_report_2025-10-14-2015.csv"
        result = parse_filename(filename)
        self.assertIsNotNone(result)
        self.assertEqual(result["course_id"], "UrFU_PYTHON_2025_fall")
        self.assertEqual(result["report_type"], "grade_report")
        self.assertEqual(result["date"].year, 2025)
        self.assertEqual(result["date"].month, 10)
        self.assertEqual(result["date"].day, 14)
        self.assertEqual(result["date"].hour, 20)
        self.assertEqual(result["date"].minute, 15)
        
    def test_parse_filename_valid_student_profile_info(self):
        """Тест парсинга валидного имени файла с информацией о студентах"""
        filename = "UrFU_PYTHON_2025_fall_student_profile_info_2025-10-14-2015.csv"
        result = parse_filename(filename)
        self.assertIsNotNone(result)
        self.assertEqual(result["course_id"], "UrFU_PYTHON_2025_fall")
        self.assertEqual(result["report_type"], "student_profile_info")
        self.assertEqual(result["date"].year, 2025)
        self.assertEqual(result["date"].month, 10)
        self.assertEqual(result["date"].day, 14)
        self.assertEqual(result["date"].hour, 20)
        self.assertEqual(result["date"].minute, 15)
        
    def test_parse_filename_invalid(self):
        """Тест парсинга невалидного имени файла"""
        filename = "invalid_filename.csv"
        result = parse_filename(filename)
        self.assertIsNone(result)

class TestScanGradeReports(unittest.TestCase):
    """Тесты для функции scan_grade_reports"""
    
    @patch('course_reports.os.walk')
    def test_scan_grade_reports_with_files(self, mock_walk):
        """Тест сканирования директории с файлами отчетов"""
        # Настраиваем мок для os.walk
        mock_walk.return_value = [
            ('/test/path', (), ['UrFU_PYTHON_2025_fall_grade_report_2025-10-14-2015.csv', 'invalid_file.txt'])
        ]
        
        # Вызываем тестируемую функцию
        df = scan_grade_reports('/test/path')
        
        # Проверяем результаты
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['course_id'], 'UrFU_PYTHON_2025_fall')
        self.assertEqual(df.iloc[0]['report_type'], 'grade_report')
        
    @patch('course_reports.os.walk')
    def test_scan_grade_reports_empty(self, mock_walk):
        """Тест сканирования пустой директории"""
        # Настраиваем мок для os.walk
        mock_walk.return_value = [('/test/path', (), [])]
        
        # Вызываем тестируемую функцию
        df = scan_grade_reports('/test/path')
        
        # Проверяем результаты
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 0)

if __name__ == '__main__':
    unittest.main()
