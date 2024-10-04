import streamlit as st
import pandas as pd
import datetime
import io
import os
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

# 設置頁面
st.set_page_config(page_title="庫存管理系統", layout="wide")

# 設置憑證路徑
# client_secrets_file = 'D:\python\client_secret_728177167304-eukd0t8rrba1q0o746alihr884ihqjfh.apps.googleusercontent.com.json'

# 設置 OAUTHLIB_INSECURE_TRANSPORT 為 1 (僅用於本地測試，生產環境中不要這樣做)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# 標題
st.title("庫存管理系統")

# 功能選擇
function = st.sidebar.radio("選擇功能", ("上傳清單", "從 Google Drive 讀取", "檢貨", "收貨", "備份到 Google Drive"))

# 加載數據
@st.cache_data
def load_data():
    try:
        return pd.read_excel("inventory.xlsx")
    except FileNotFoundError:
        return pd.DataFrame(columns=["商品編號", "商品名稱", "數量", "檢貨狀態", "收貨狀態"])

data = load_data()

# 條碼掃描 JavaScript
barcode_scanner_js = """
<script src="https://cdn.jsdelivr.net/npm/quagga@0.12.1/dist/quagga.min.js"></script>
<div id="interactive" class="viewport"></div>
<script>
    var lastResult = null;
    Quagga.init({
        inputStream : {
            name : "Live",
            type : "LiveStream",
            target: document.querySelector('#interactive')
        },
        decoder : {
            readers : ["ean_reader", "ean_8_reader", "code_128_reader"]
        }
    }, function(err) {
        if (err) {
            console.log(err);
            return
        }
        console.log("Initialization finished. Ready to start");
        Quagga.start();
    });

    Quagga.onDetected(function(result) {
        var code = result.codeResult.code;
        if (code !== lastResult) {
            lastResult = code;
            console.log("Barcode detected and processed : [" + code + "]", result);
            Streamlit.setComponentValue(code);
            Quagga.stop();
        }
    });
</script>
<style>
    .viewport {
        max-width: 100%;
        max-height: 50vh;
    }
</style>
"""

# 創建憑證
credentials = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=['https://www.googleapis.com/auth/drive.file']
)

# 創建 Drive API 客戶端
drive_service = build('drive', 'v3', credentials=credentials)

# 獲取文件夾中的文件列表
def list_files_in_folder(folder_id):
    results = drive_service.files().list(
        q=f"'{folder_id}' in parents and mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'",
        fields="files(id, name)").execute()
    return results.get('files', [])

# 讀取 Excel 文件
def read_excel_from_drive(file_id):
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return pd.read_excel(fh)

# Streamlit 應用程式主函數
def main():
    st.title("藥品庫存管理系統")

    # 指定的文件夾 ID
    folder_id = '1LdDnfuu3N8v9PkePOhuJd0Ffv_FBQsMA'

    # 獲取文件夾中的文件列表
    files = list_files_in_folder(folder_id)

    # 創建文件選擇下拉菜單
    file_names = [file['name'] for file in files]
    selected_file = st.selectbox("選擇一個文件", file_names)

    if selected_file:
        # 獲取選中文件的 ID
        file_id = next(file['id'] for file in files if file['name'] == selected_file)

        try:
            # 讀取選中的文件
            df = read_excel_from_drive(file_id)

            # 顯示庫存數據
            st.write(df)

            # 這裡添加您的其他應用邏輯
            # ...

        except Exception as e:
            st.error(f"讀取文件時發生錯誤: {str(e)}")
            st.exception(e)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"發生錯誤: {str(e)}")
        st.exception(e)
