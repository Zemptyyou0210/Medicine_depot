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

# 寫入 Excel 文件
def write_excel_to_drive(df, filename, folder_id):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    file_metadata = {'name': filename, 'parents': [folder_id]}
    media = MediaIoBaseUpload(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return file.get('id')

# Streamlit 應用程式主函數
def main():
    st.title("藥品庫存管理系統")

    # 從 Google Drive 讀取庫存數據
    inventory_file_id = 'YOUR_INVENTORY_FILE_ID'  # 替換為您的庫存文件 ID
    df = read_excel_from_drive(inventory_file_id)

    # 顯示庫存數據
    st.write(df)

    # 這裡添加您的其他應用邏輯
    # ...

    # 保存更新後的庫存數據
    if st.button('保存更新'):
        folder_id = 'YOUR_FOLDER_ID'  # 替換為您要保存文件的文件夾 ID
        new_file_id = write_excel_to_drive(df, 'updated_inventory.xlsx', folder_id)
        st.success(f'庫存已更新，新文件 ID: {new_file_id}')

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"發生錯誤: {str(e)}")
        st.exception(e)