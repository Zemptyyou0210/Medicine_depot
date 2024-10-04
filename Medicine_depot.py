import streamlit as st
import pandas as pd
import datetime
import io
import os
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
import streamlit.components.v1 as components

# 設置頁面
st.set_page_config(page_title="庫存管理系統", layout="wide")

# 設置憑證路徑
# client_secrets_file = 'D:\python\client_secret_728177167304-eukd0t8rrba1q0o746alihr884ihqjfh.apps.googleusercontent.com.json'

# 設置 OAUTHLIB_INSECURE_TRANSPORT 為 1 (僅用於本地測試，生產環境中不要這樣做)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# 標題
st.title("庫存管理系統")

# 功能選擇
function = st.sidebar.radio("選擇功能", ("從 Google Drive 讀取", "檢貨", "收貨", "備份到 Google Drive"))

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
    
    function = create_sidebar()
    
    if function == "從 Google Drive 讀取":
        read_from_drive()
    elif function == "檢貨":
        check_inventory()
    elif function == "收貨":
        receive_goods()
    elif function == "備份到 Google Drive":
        backup_to_drive()
    
    # 添加一個隱藏的按鈕來觸發重新運行
    if st.button('Refresh', key='refresh_button', help='Click to refresh'):
        st.experimental_rerun()

def create_sidebar():
    return st.sidebar.radio(
        "選擇功能",
        ("從 Google Drive 讀取", "檢貨", "收貨", "備份到 Google Drive"),
        key="function_selection"
    )

def read_from_drive():
    st.subheader("從 Google Drive 讀取")
    folder_id = '1LdDnfuu3N8v9PkePOhuJd0Ffv_FBQsMA'  # Google Drive 文件夾 ID
    files = list_files_in_folder(folder_id)
    
    if not files:
        st.warning("未找到 Excel 文件")
        return None
    
    selected_file = st.selectbox("選擇 Excel 文件", [file['name'] for file in files])
    file_id = next(file['id'] for file in files if file['name'] == selected_file)
    
    df = read_excel_from_drive(file_id)
    st.session_state['inventory_df'] = df
    st.success(f"已成功讀取 {selected_file}")
    return df

def check_inventory():
    st.subheader("檢貨")
    if 'inventory_df' not in st.session_state:
        st.warning("請先從 Google Drive 讀取庫存文件")
        return

    df = st.session_state['inventory_df']
    
    # 顯示當前庫存狀態
    st.write("當前庫存狀態：")
    st.dataframe(df.style.applymap(lambda x: 'background-color: #90EE90' if x == '已檢貨' else 'background-color: #FFB6C1', subset=['狀態']))

    # 條碼掃描區域
    barcode = st.text_input("輸入條碼或使用掃描器")
    
    if barcode:
        # 查找並更新產品狀態
        mask = df['條碼'] == barcode
        if mask.any():
            df.loc[mask, '狀態'] = '已檢貨'
            st.success(f"已更新條碼 {barcode} 的狀態為已檢貨")
        else:
            st.error(f"未找到條碼 {barcode} 的產品")

    # 更新 session state
    st.session_state['inventory_df'] = df

    # 添加條碼掃描的 JavaScript 代碼
    components.html(
        """
        <script src="https://unpkg.com/html5-qrcode"></script>
        <div id="reader" width="600px"></div>
        <script>
            function onScanSuccess(decodedText, decodedResult) {
                // 將掃描結果發送到 Streamlit
                window.parent.postMessage({type: 'streamlit:setComponentValue', value: decodedText}, '*');
            }
            var html5QrcodeScanner = new Html5QrcodeScanner(
                "reader", { fps: 10, qrbox: 250 });
            html5QrcodeScanner.render(onScanSuccess);
        </script>
        """,
        height=300,
    )

def receive_goods():
    # 實現收貨邏輯
    st.subheader("收貨")
    # ... 收貨相關代碼 ...

def backup_to_drive():
    # 實現備份到 Google Drive 的邏輯
    st.subheader("備份到 Google Drive")
    # ... 備份相關代碼 ...

if __name__ == "__main__":
    main()
