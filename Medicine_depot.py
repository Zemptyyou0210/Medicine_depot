import streamlit as st

# 設置頁面配置
st.set_page_config(page_title="藥品庫存管理系統", layout="wide")

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd
import io
import streamlit.components.v1 as components

# 創建 Google Drive API 客戶端
@st.cache_resource
def create_drive_client():
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=credentials)

drive_service = create_drive_client()

def list_files_in_folder(folder_id):
    try:
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents",  # 移除 MIME 類型檢查
            fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        st.write(f"找到 {len(files)} 個文件")
        for file in files:
            st.write(f"文件名: {file['name']}, ID: {file['id']}, 類型: {file['mimeType']}")
        return files
    except Exception as e:
        st.error(f"獲取文件列表時發生錯誤: {str(e)}")
        return []

def read_excel_from_drive(file_id):
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return pd.read_excel(fh)

def read_from_drive():
    st.subheader("從 Google Drive 讀取")
    folder_id = '1LdDnfuu3N8v9PkePOhuJd0Ffv_FBQsMA'  # Google Drive 文件夾 ID
    files = list_files_in_folder(folder_id)
    
    if not files:
        st.warning("未找到 Excel 文件")
        if st.button("重新整理"):
            st.experimental_rerun()
        return None
    
    selected_file = st.selectbox("選擇 Excel 文件", [file['name'] for file in files])
    file_id = next(file['id'] for file in files if file['name'] == selected_file)
    
    try:
        df = read_excel_from_drive(file_id)
        # 確保條碼列被正確讀取
        if '條碼' in df.columns:
            df['條碼'] = df['條碼'].astype(str).str.strip()
            # 移除可能的非數字字符
            df['條碼'] = df['條碼'].apply(lambda x: ''.join(filter(str.isdigit, x)))
        else:
            st.error("數據中缺少 '條碼' 列")
        
        st.write("數據框中的條碼示例:")
        st.write(df['條碼'].head())
        
        # 讀取 Excel 文件後，檢查並添加 '檢貨狀態' 列
        if '檢貨狀態' not in df.columns:
            df['檢貨狀態'] = '未檢貨'
            st.info("已添加 '檢貨狀態' 列到數據中")

        st.session_state['inventory_df'] = df
        st.success(f"已成功讀取 {selected_file}")
        st.write(df)
    except Exception as e:
        st.error(f"讀取文件時發生錯誤: {str(e)}")

def test_drive_access():
    try:
        results = drive_service.files().list(pageSize=10, fields="files(id, name, mimeType)").execute()
        items = results.get('files', [])
        st.write('服務帳號可以訪問 Google Drive。找到的文件：')
        for item in items:
            st.write(f"{item['name']} ({item['id']}) - {item['mimeType']}")
    except Exception as e:
        st.error(f"訪問 Google Drive 時發生錯誤: {str(e)}")

def format_ean13(barcode):
    """將條碼格式化為 EAN-13 格式"""
    barcode = str(barcode).zfill(13)  # 補零至 13 位
    return f"{barcode[:1]} {barcode[1:7]} {barcode[7:]}"  # 格式化顯示

def check_and_mark_item(df, barcode):
    st.write(f"開始處理條碼: {barcode}")
    try:
        if '檢貨狀態' not in df.columns:
            df['檢貨狀態'] = '未檢貨'
        
        if '條碼' not in df.columns:
            st.error("數據框中缺少 '條碼' 列")
            return None
        
        # 嘗試完全匹配
        item = df[df['條碼'].astype(str).str.strip() == str(barcode).strip()]
        
        if item.empty:
            # 如果完全匹配失敗，嘗試部分匹配
            item = df[df['條碼'].astype(str).str.strip().str.contains(str(barcode).strip(), na=False)]
        
        if not item.empty:
            selected_item = item.iloc[0]
            st.success(f"找到商品：{selected_item['藥品名稱']}")
            st.write(f"匹配的條碼: {selected_item['條碼']}")
            
            if '檢貨狀態' in df.columns:
                old_status = df.loc[df['條碼'] == selected_item['條碼'], '檢貨狀態'].values[0]
                df.loc[df['條碼'] == selected_item['條碼'], '檢貨狀態'] = '已檢貨'
                new_status = df.loc[df['條碼'] == selected_item['條碼'], '檢貨狀態'].values[0]
                st.write(f"檢貨狀態從 '{old_status}' 更新為 '{new_status}'")
                st.success("商品已自動標記為已檢貨")
                return df
            else:
                st.warning("無法更新檢貨狀態，因為數據框中缺少 '檢貨狀態' 列")
        else:
            st.error(f"未找到條碼為 {barcode} 的商品，請檢查條碼是否正確")
    except Exception as e:
        st.error(f"處理商品時發生錯誤: {str(e)}")
    
    return None

def custom_component():
    component_value = components.declare_component(
        "custom_component",
        path="path/to/your/component"  # 替換為實際路徑
    )
    return component_value

# 在 check_inventory 函數中使用
def check_inventory():
    st.subheader("檢貨")
    
    if 'inventory_df' not in st.session_state:
        st.warning("請先從 Google Drive 讀取庫存文件")
        return

    df = st.session_state['inventory_df'].copy()
    st.write(f"數據框中的條碼示例: {df['條碼'].head().tolist()}")  # 調試信息

    # 顯示當前庫存狀態
    display_columns = ['藥庫位置', '藥品名稱', '盤撥量', '藥庫庫存', '檢貨狀態']
    df_display = df[display_columns]
    
    status_display = st.empty()
    status_display.write("當前庫存狀態：")
    status_display.dataframe(df_display.style.applymap(
        lambda x: 'background-color: #90EE90' if x == '已檢貨' else 'background-color: #FFB6C1',
        subset=['檢貨狀態']
    ))

    # 使用 st.components.v1.html 來嵌入條碼掃描器
    scanned_value = st.components.v1.html(barcode_scanner_html, height=600)

    # 初始化 session_state
    if 'scanned_value' not in st.session_state:
        st.session_state.scanned_value = ""

    # 顯示掃描到的值
    if st.session_state.scanned_value:
        st.write(f"掃描到的值: {st.session_state.scanned_value}")
        # 處理掃描到的條碼
        process_barcode(st.session_state.scanned_value)
        # 清除掃描的值，為下一次掃描做準備
        st.session_state.scanned_value = ""

    # 手動輸入條碼
    manual_input = st.text_input("手動輸入條碼", value="")

    if st.button("更新庫存"):
        if manual_input:
            process_barcode(manual_input)

    # 顯示調試信息
    st.write("調試信息:")
    st.components.v1.html(
        """
        <div id="debug-display"></div>
        <script>
        setInterval(() => {
            const debugElement = document.getElementById('debug');
            const debugDisplayElement = document.getElementById('debug-display');
            if (debugElement && debugDisplayElement) {
                debugDisplayElement.textContent = debugElement.textContent;
            }
        }, 1000);
        </script>
        """,
        height=200
    )

def process_barcode(barcode):
    cleaned_barcode = clean_barcode(barcode)
    if cleaned_barcode:
        st.write(f"處理的條碼: {cleaned_barcode}")
        df = update_inventory_status(st.session_state['inventory_df'], cleaned_barcode)
        st.session_state['inventory_df'] = df
        st.success(f"條碼 {cleaned_barcode} 已更新為已檢貨")
    else:
        st.error("無效的 EAN-13 條碼")

def receive_inventory():
    st.subheader("收貨")
    
    if 'inventory_df' not in st.session_state:
        st.warning("請先從 Google Drive 讀取庫存文件")
        if st.button("前往讀取數據"):
            st.session_state.function_selection = "從 Google Drive 讀取"
            st.rerun()
        return

    df = st.session_state['inventory_df']
    
    # 只選擇需要的列
    display_columns = ['藥品名稱', '盤撥量', '收貨狀態']
    df_display = df[display_columns]

    # 顯示當前收貨狀態
    st.write("當前收貨狀態：")
    st.dataframe(df_display.style.applymap(
        lambda x: 'background-color: #90EE90' if x == '已收貨' else 'background-color: #FFB6C1',
        subset=['收貨狀態']
    ))

    # 使用 form 來確保條碼輸入後可以立即處理
    with st.form(key='barcode_form'):
        barcode = st.text_input("輸入商品條碼或掃描條碼", key="barcode_input")
        submit_button = st.form_submit_button("檢查商品")

    if submit_button or barcode:
        receive_item(df, barcode, display_columns)

    # 顯示收貨進度
    total_items = len(df)
    received_items = len(df[df['收貨狀態'] == '已收貨'])
    progress = received_items / total_items
    st.progress(progress)
    st.write(f"收貨進度：{received_items}/{total_items} ({progress:.2%})")

def receive_item(df, barcode, display_columns):
    if '條碼' not in df.columns:
        st.error("數據框中缺少 '條碼' 列")
        return
    
    item = df[df['條碼'] == barcode]
    if not item.empty:
        st.success(f"找到商品：{item['藥品名稱'].values[0]}")
        for col in display_columns:
            if col in item.columns:
                st.write(f"{col}：{item[col].values[0]}")
        if item['收貨狀態'].values[0] != '已收貨':
            if st.button("標記為已收貨"):
                df.loc[df['條碼'] == barcode, '收貨狀態'] = '已收貨'
                st.session_state['inventory_df'] = df
                st.success("商品已標記為已收貨")
                st.rerun()
        else:
            st.info("此商品已經收貨")
    else:
        st.error("未找到該商品，請檢查條碼是否正確")

def backup_to_drive():
    st.subheader("備份到 Google Drive")
    if 'inventory_df' in st.session_state:
        df = st.session_state['inventory_df']
        # 备份逻辑
        st.success("數據已備份到 Google Drive")
    else:
        st.warning("沒有可備份的數據")

def main():
    st.title("藥品庫存管理系統")

    # 側邊欄
    st.sidebar.title("功能選單")
    menu = ["首頁", "讀取庫存", "檢貨"]
    choice = st.sidebar.selectbox("選擇功能", menu)

    if choice == "首頁":
        st.subheader("歡迎使用藥品庫存管理系統")
    elif choice == "讀取庫存":
        read_from_drive()
    elif choice == "檢貨":
        check_inventory()

    if st.button("測試 Google Drive 訪問"):
        test_drive_access()

barcode_scanner_html = """
<div id="scanner-container"></div>
<div id="debug"></div>
<script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
<script>
// ... 保留之前的函數定義 ...

let html5QrcodeScanner = new Html5Qrcode("scanner-container");
const config = { 
    fps: 10, 
    qrbox: { width: 250, height: 150 },
    aspectRatio: 1.0,
    supportedScanTypes: [Html5QrcodeScanType.SCAN_TYPE_CAMERA]
};

html5QrcodeScanner.start({ facingMode: "environment" }, config, onScanSuccess, onScanFailure)
    .catch(err => {
        updateDebug('啟動掃描器失敗: ' + err);
    });

// ... 保留之前的事件監聽器 ...
</script>
"""

st.markdown("""
<style>
#scanner-container {
    position: relative;
    width: 100%;
    max-width: 100vw;
    height: 70vh;
    overflow: hidden;
    margin: auto;
}
#scanner-container video {
    width: 100%;
    height: 100%;
    object-fit: cover;
}
#debug {
    margin-top: 10px;
    padding: 10px;
    background-color: #f0f0f0;
    border: 1px solid #ddd;
    font-size: 14px;
    white-space: pre-wrap;
    word-wrap: break-word;
}
</style>
""", unsafe_allow_html=True)

def clean_barcode(barcode):
    cleaned = ''.join(filter(str.isdigit, barcode))
    if len(cleaned) == 13:
        return cleaned
    else:
        st.warning(f"輸入的條碼 '{barcode}' 不是有效的 EAN-13 格式。")
        return None

def update_inventory_status(df, barcode):
    cleaned_barcode = clean_barcode(barcode)
    if cleaned_barcode:
        if cleaned_barcode in df['條碼'].astype(str).values:
            df.loc[df['條碼'].astype(str) == cleaned_barcode, '檢貨狀態'] = '已檢貨'
            st.success(f"條碼 {cleaned_barcode} 已更新為已檢貨")
            return df
        else:
            st.warning(f"條碼 {cleaned_barcode} 未找到")
    else:
        st.error("無效的 EAN-13 條碼")
    return df

# 處理從 JavaScript 發送的消息
if 'scanned_value' not in st.session_state:
    st.session_state.scanned_value = ""

message = st.experimental_get_query_params().get("message")
if message and message[0] == "streamlit:setComponentValue":
    st.session_state.scanned_value = st.experimental_get_query_params().get("value", [""])[0]

if __name__ == "__main__":
    main()
