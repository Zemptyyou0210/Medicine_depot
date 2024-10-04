import streamlit as st
import pandas as pd
import datetime
import io
import os
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials

# 設置頁面
st.set_page_config(page_title="庫存管理系統", layout="wide")

# 設置憑證路徑
client_secrets_file = 'D:\python\client_secret_728177167304-eukd0t8rrba1q0o746alihr884ihqjfh.apps.googleusercontent.com.json'

# 設置 OAUTHLIB_INSECURE_TRANSPORT 為 1 (僅用於本地測試，生產環境中不要這樣做)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# 標題
st.title("庫存管理系統")

# 功能選擇
function = st.sidebar.radio("選擇功能", ("上傳清單", "從 Google Drive 讀取", "檢貨", "收貨"))

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

# 上傳清單
if function == "上傳清單":
    st.header("上傳清單")
    uploaded_file = st.file_uploader("選擇 Excel 文件", type="xlsx")
    if uploaded_file is not None:
        data = pd.read_excel(uploaded_file)
        data.to_excel("inventory.xlsx", index=False)
        st.success("清單已成功上傳！")
        st.write(data)

# 從 Google Drive 讀取
elif function == "從 Google Drive 讀取":
    st.header("從 Google Drive 讀取文件")

    # 檢查是否已經有存儲的憑證
    if 'credentials' not in st.session_state:
        # 如果沒有，創建授權流程
        flow = Flow.from_client_secrets_file(
            client_secrets_file,
            scopes=['https://www.googleapis.com/auth/drive.readonly'],
            redirect_uri='http://localhost:8501/'
        )
        
        # 使用 st.query_params 來獲取授權碼
        if 'code' in st.query_params:
            flow.fetch_token(code=st.query_params['code'])
            st.session_state.credentials = flow.credentials
            st.rerun()
        else:
            auth_url, _ = flow.authorization_url(prompt='consent')
            st.markdown(f"請點擊此鏈接進行授權: [Authorize]({auth_url})")
            st.stop()

    # 如果有有效的憑證，繼續處理
    if 'credentials' in st.session_state:
        credentials = Credentials(
            token=st.session_state.credentials.token,
            refresh_token=st.session_state.credentials.refresh_token,
            token_uri=st.session_state.credentials.token_uri,
            client_id=st.session_state.credentials.client_id,
            client_secret=st.session_state.credentials.client_secret,
            scopes=st.session_state.credentials.scopes
        )
        drive_service = build('drive', 'v3', credentials=credentials)
        
        # 文件夾 ID
        folder_id = '1LdDnfuu3N8v9PkePOhuJd0Ffv_FBQsMA'

        try:
            # 獲取文件夾中的文件列表
            results = drive_service.files().list(
                q=f"'{folder_id}' in parents",
                pageSize=10,
                fields="nextPageToken, files(id, name, mimeType)"
            ).execute()
            items = results.get('files', [])

            if not items:
                st.write('沒有找到文件。')
            else:
                # 創建文件選擇下拉菜單
                file_names = [item['name'] for item in items]
                selected_file = st.selectbox('選擇要查看的文件', file_names)

                # 獲取選中文件的 ID
                selected_file_id = next(item['id'] for item in items if item['name'] == selected_file)

                if st.button('查看文件'):
                    # 從 Google Drive 下載文件
                    request = drive_service.files().get_media(fileId=selected_file_id)
                    file = io.BytesIO()
                    downloader = MediaIoBaseDownload(file, request)
                    done = False
                    while done is False:
                        status, done = downloader.next_chunk()

                    # 重置文件指針到開始位置
                    file.seek(0)

                    # 讀取文件（假設是 Excel 格式）
                    data = pd.read_excel(file)
                    data.to_excel("inventory.xlsx", index=False)

                    # 顯示數據
                    st.write(data)
                    st.success("文件已成功讀取並保存為本地庫存！")

        except Exception as e:
            st.error(f'發生錯誤：{str(e)}')
    else:
        st.warning("請先完成授權流程。")

# 檢貨
elif function == "檢貨":
    st.header("檢貨")
    
    col1, col2 = st.columns(2)
    with col1:
        st.components.v1.html(barcode_scanner_js, height=300)
    with col2:
        manual_input = st.text_input("或手動輸入商品編號")
    
    scanned_code = st.session_state.get('scanned_code', None)
    
    if scanned_code or manual_input:
        code = scanned_code or manual_input
        if code in data["商品編號"].values:
            data.loc[data["商品編號"] == code, "檢貨狀態"] = "已檢查"
            data.to_excel("inventory.xlsx", index=False)
            st.success(f"商品 {code} 已檢查！")
            st.session_state.scanned_code = None  # 重置掃描的代碼
        else:
            st.error(f"找不到商品 {code}")
    
    st.write(data.style.applymap(lambda x: 'background-color: lightgreen' if x == '已檢查' else '', subset=['檢貨狀態']))

# 收貨
elif function == "收貨":
    st.header("收貨")
    
    col1, col2 = st.columns(2)
    with col1:
        st.components.v1.html(barcode_scanner_js, height=300)
    with col2:
        manual_input = st.text_input("或手動輸入商品編號")
    
    scanned_code = st.session_state.get('scanned_code', None)
    
    if scanned_code or manual_input:
        code = scanned_code or manual_input
        if code in data["商品編號"].values:
            data.loc[data["商品編號"] == code, "收貨狀態"] = "已收貨"
            data.to_excel("inventory.xlsx", index=False)
            st.success(f"商品 {code} 已收貨！")
            st.session_state.scanned_code = None  # 重置掃描的代碼
        else:
            st.error(f"找不到商品 {code}")
    
    st.write(data.style.applymap(lambda x: 'background-color: lightyellow' if x == '已收貨' else '', subset=['收貨狀態']))

# 顯示當前庫存
st.header("當前庫存")
st.write(data)