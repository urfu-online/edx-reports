import pandas as pd
import streamlit as st
from awesome_table import AwesomeTable
from awesome_table.column import Column, ColumnDType
import os

# Создадим тестовые данные
data = [{
    "id": 1,
    "name": "Test Course",
    "file_path": "../../data/openedx-media/grades/UrFU_test_2025_grade_report_2025-10-07-2042.csv"
}]

st.set_page_config(page_title='Test AwesomeTable', layout='wide')
st.title('Test AwesomeTable with Local Files')

df = pd.DataFrame(data)
AwesomeTable(df, columns=[
    Column(name='id', label='ID'),
    Column(name='name', label='Name'),
    Column(name='file_path', label='Download', dtype=ColumnDType.DOWNLOAD),
])