# nicegui_reports_fixed.py
import os
import logging
import pandas as pd
from datetime import datetime, timezone
from nicegui import ui, run
from course_reports import (
    get_all_courses,
    scan_grade_reports,
    process_courses_data,
    GRADES_DIR,
)
import math

# === НАСТРОЙКИ ===
DAYS_OK = 5
DEFAULT_DAYS_MAX = 30

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("reports.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class ReportsApp:
    def __init__(self):
        # Данные
        self.courses: list = []
        self.df_reports: pd.DataFrame = pd.DataFrame()
        self.df_all: pd.DataFrame = pd.DataFrame()
        self.filtered: pd.DataFrame = pd.DataFrame()

        # Фильтры (связываются с UI через .bind_value)
        self.selected_course: str = "Все"
        self.selected_type: str = "Все"
        self.selected_run: str = "Все"
        self.selected_days: int = DEFAULT_DAYS_MAX

        # UI widgets
        self.status_label = None
        self.course_select = None
        self.type_select = None
        self.run_select = None
        self.days_slider = None
        self.table = None

        self.setup_routes()
        self.setup_ui()

    # --- Роут для скачивания (регистрируем ОДИН раз) ---
    def setup_routes(self):
        @ui.page("/download/{filename}")
        async def download_file(filename: str):
            file_path = os.path.join(GRADES_DIR, filename)
            if os.path.exists(file_path):
                # Возвращаем download напрямую
                return await ui.download(file_path, filename)
            ui.label("Файл не найден")

    # --- Главная страница ---
    def setup_ui(self):
        @ui.page("/")
        def main_page():
            with ui.column().classes("w-full p-4"):
                ui.label("📊 Отчеты по курсам Open edX").classes("text-xl font-bold")

                # Статус
                self.status_label = ui.label("Загрузка данных...").classes("text-lg")

                # Отложенная загрузка
                ui.timer(0.1, self.load_data, once=True)

                # Фильтры
                with ui.row().classes("w-full items-center gap-4 mt-4"):
                    self.course_select = (
                        ui.select(options=["Все"], label="Курс")
                        .classes("min-w-64")
                        .bind_value(self, "selected_course")
                        .on("update:model-value", lambda e: self.apply_filters())
                    )
                    self.type_select = (
                        ui.select(options=["Все"], label="Тип отчета")
                        .classes("min-w-48")
                        .bind_value(self, "selected_type")
                        .on("update:model-value", lambda e: self.apply_filters())
                    )
                    self.run_select = (
                        ui.select(options=["Все"], label="Запуск курса")
                        .classes("min-w-48")
                        .bind_value(self, "selected_run")
                        .on("update:model-value", lambda e: self.apply_filters())
                    )
                    with ui.column().classes("min-w-64"):
                        self.days_slider = (
                            ui.slider(
                                min=0, max=DEFAULT_DAYS_MAX, value=self.selected_days
                            )
                            .classes("w-64")
                            .bind_value(self, "selected_days")
                            .on("update:model-value", lambda e: self.apply_filters())
                        )
                        ui.label("Макс. дней с отчета")

                # Таблица
                self.table = ui.table(columns=[], rows=[]).classes("w-full mt-4")

    # --- Загрузка данных ---
    async def load_data(self):
        try:
            self.status_label.set_text("Загружаем список курсов...")
            self.courses = await run.io_bound(get_all_courses)
            logger.info("Успешно загружено %d курсов", len(self.courses))

            self.status_label.set_text("Сканируем отчеты...")
            self.df_reports = await run.io_bound(scan_grade_reports, GRADES_DIR)
            logger.info("Сканирование завершено. Файлов: %d", len(self.df_reports))

            # Сводная таблица
            self.df_all = await run.io_bound(
                process_courses_data, self.courses, self.df_reports
            )

            # Гарантируем корректные типы для числовых полей
            if not self.df_all.empty and "Дней с отчета" in self.df_all.columns:
                self.df_all["Дней с отчета"] = pd.to_numeric(
                    self.df_all["Дней с отчета"], errors="coerce"
                )

            # Обновляем фильтры и таблицу
            self.update_filters()
            self.apply_filters()
            self.status_label.set_text("")
        except Exception as e:
            logger.exception("Ошибка загрузки данных: %s", e)
            self.status_label.set_text(f"Ошибка загрузки данных: {e}")

    # --- Обновление значений фильтров и слайдера ---
    def update_filters(self):
        if self.df_all.empty:
            # Нечего обновлять
            for sel in (self.course_select, self.type_select, self.run_select):
                if sel:
                    sel.set_options(["Все"])
            if self.days_slider:
                self.days_slider.min = 0
                self.days_slider.max = DEFAULT_DAYS_MAX
                self.days_slider.value = DEFAULT_DAYS_MAX
            self.selected_days = DEFAULT_DAYS_MAX
            return

        def safe_options(column: str):
            values = (
                self.df_all[column].dropna().astype(str).unique().tolist()
                if column in self.df_all.columns
                else []
            )
            return ["Все"] + sorted(values)

        self.course_select.set_options(safe_options("Название курса"))
        self.type_select.set_options(safe_options("Тип отчета"))
        self.run_select.set_options(safe_options("Запуск курса"))

        # Слайдер дней: учитываем максимум по данным, но ставим разумный минимум
        series = pd.to_numeric(self.df_all["Дней с отчета"], errors="coerce")
        if series.empty or series.dropna().empty:
            min_days_in_data, max_days_in_data = 0, 0
        else:
            min_days_in_data = int(series.min())
            max_val = series.max()
            max_days_in_data = int(max_val) if not math.isnan(max_val) else 0
        new_max = max(max_days_in_data, DEFAULT_DAYS_MAX)

        # Сохраняем текущее значение в пределах нового диапазона
        if self.days_slider:
            self.days_slider.min = 0
            self.days_slider.max = new_max
            self.days_slider.value = min(max(self.selected_days, 0), new_max)
        self.selected_days = min(max(self.selected_days, 0), new_max)

    # --- Применение фильтров ---
    def apply_filters(self):
        if self.df_all.empty:
            self.filtered = pd.DataFrame()
        else:
            df = self.df_all.copy()

            # Текстовые фильтры
            if (
                self.selected_course
                and self.selected_course != "Все"
                and "Название курса" in df.columns
            ):
                df = df[df["Название курса"] == self.selected_course]
            if (
                self.selected_type
                and self.selected_type != "Все"
                and "Тип отчета" in df.columns
            ):
                df = df[df["Тип отчета"] == self.selected_type]
            if (
                self.selected_run
                and self.selected_run != "Все"
                and "Запуск курса" in df.columns
            ):
                df = df[df["Запуск курса"] == self.selected_run]

            # Числовой фильтр по дням: пропуски пропускаем (считаем подходящими)
            if "Дней с отчета" in df.columns:
                days = pd.to_numeric(df["Дней с отчета"], errors="coerce")
                df = df[days.isna() | (days <= int(self.selected_days or 0))]

            # Фильтр: не отрисовывать строки без файла отчета
            if "Файл" in df.columns:
                df = df[df["Файл"].notna() & (df["Файл"] != "")]

            self.filtered = df

        logger.info("Применены фильтры. Отобрано записей: %d", len(self.filtered))
        self.update_table()

    # --- Обновление таблицы ---
    def update_table(self):
        table_data = self.filtered.copy()

        columns = [
            {
                "name": "course_name",
                "label": "Название курса",
                "field": "Название курса",
                "align": "left",
            },
            {"name": "course_id", "label": "Курс", "field": "Курс"},
            {"name": "course_start", "label": "Запуск курса", "field": "Запуск курса"},
            {"name": "report_type", "label": "Тип отчета", "field": "Тип отчета"},
            {
                "name": "last_report",
                "label": "Последний отчет",
                "field": "Последний отчет",
                "sortable": True,
            },
            {
                "name": "days_since_report",
                "label": "Дней с отчета",
                "field": "Дней с отчета",
                "sortable": True,
            },
            {"name": "download", "label": "Скачать", "field": "Скачать"},
        ]

        self.table.columns = columns
        self.table.rows = table_data.to_dict("records") if not table_data.empty else []
        self.table.add_slot(
            "body-cell-days_since_report",
            """
            <q-td key="days_since_report" :style="props.value > 5 ? 'background-color:pink' : 'background-color:inherit'" :props="props">
                <q-badge>
                    {{ props.value }}
                </q-badge>
            </q-td>
        """,
        )
        self.table.add_slot(
            "body-cell-download",
            """
            <q-td :props="props">
                <q-btn label="Скачать" @click="() => $parent.$emit('download', props.row)" flat />
            </q-td>
        """,
        )
        self.table.on("download", lambda e: ui.download.file(e.args["Файл"]))


# --- Запуск приложения ---
if __name__ in {"__main__", "__mp_main__"}:
    app = ReportsApp()
    ui.run(title="Отчеты по курсам Open edX", dark=True, reload=True, port=8080)
