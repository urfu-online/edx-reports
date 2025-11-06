import pandas as pd
import streamlit as st
from awesome_table import AwesomeTable
from awesome_table.column import Column, ColumnDType

# Создадим тестовые данные с веб-ссылками
data = [{
    "id": 1,
    "name": "Test Course",
    "download_url": "https://example.com/file1.csv"
}, {
    "id": 2,
    "name": "Another Course",
    "download_url": "https://example.com/file2.csv"
}]

st.set_page_config(page_title='Test AwesomeTable', layout='wide')
st.title('Test AwesomeTable with Web URLs')

df = pd.DataFrame(data)
AwesomeTable(df, columns=[
    Column(name='id', label='ID'),
    Column(name='name', label='Name'),
    Column(name='download_url', label='Download', dtype=ColumnDType.DOWNLOAD),
], show_search=True, show_order=True)