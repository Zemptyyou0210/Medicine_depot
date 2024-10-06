import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd
import io
import cv2
from pyzbar import pyzbar
import time
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase
import av

# 設置頁面
st.set_page_config(page_title="藥品庫存管理系統", layout="wide")

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
            q=f"'{folder_id}' in parents and mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'",
            pageSize=1000,
            fields="nextPageToken, files(id, name)"
        ).execute()
        return results.get('files', [])
    except Exception as e:
        st.error(f"列出文件時發生錯誤: {str(e)}")
        return []

def read_excel_from_drive(file_id):
    request = drive_service.files().get_media(fileId=file_id)
    file = io.BytesIO()
    downloader = MediaIoBaseDownload(file, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    file.seek(0)
    return pd.read_excel(file)

def read_from_drive():
    st.subheader("從 Google Drive 讀取資料")
    folder_id = "1LdDnfuu3N8v9PkePOhuJd0Ffv_FBQsMA"  # 直接使用固定的資料夾 ID
    
    try:
        files = list_files_in_folder(folder_id)
        if not files:
            st.warning("未找到 Excel 文件")
            if st.button("重新整理"):
                st.experimental_rerun()
            return None
        
        # 使用下拉式選單選擇 Excel 文件
        file_names = [file['name'] for file in files]
        if not file_names:
            st.warning("資料夾中沒有 Excel 文件")
            return None
        
        selected_file = st.selectbox("選擇 Excel 文件", file_names)
        
        if selected_file:
            file_id = next(file['id'] for file in files if file['name'] == selected_file)
            df = read_excel_from_drive(file_id)
            # 確保條碼列被正確讀取
            if '條碼' in df.columns:
                df['條碼'] = df['條碼'].astype(str).str.strip()
                df['條碼'] = df['條碼'].apply(lambda x: ''.join(filter(str.isdigit, x)))
            else:
                st.error("數據中缺少 '條碼' 列")
            
            # 添加 '檢貨狀態' 列
            if '檢貨狀態' not in df.columns:
                df['檢貨狀態'] = '未檢貨'
                st.info("已添加 '檢貨狀態' 列到數據中")

            st.session_state['inventory_df'] = df
            st.success(f"已成功讀取 {selected_file}")
            st.write(df)
        else:
            st.warning("請選擇一個 Excel 文件")
    except Exception as e:
        st.error(f"讀取文件時發生錯誤: {str(e)}")

class BarcodeVideoProcessor(VideoProcessorBase):
    def __init__(self):
        self.last_barcode = None
        self.last_scan_time = 0

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        barcodes = pyzbar.decode(img)
        
        for barcode in barcodes:
            barcode_data = barcode.data.decode('utf-8')
            current_time = time.time()
            if current_time - self.last_scan_time > 2 and barcode_data != self.last_barcode:
                self.last_scan_time = current_time
                self.last_barcode = barcode_data
                if 'scanned_barcodes' not in st.session_state:
                    st.session_state['scanned_barcodes'] = []
                st.session_state['scanned_barcodes'].append(barcode_data)

        return av.VideoFrame.from_ndarray(img, format="bgr24")

def update_inventory_status(df, barcode):
    if barcode in df['條碼'].values:
        df.loc[df['條碼'] == barcode, '檢貨狀態'] = '已檢貨'
        st.success(f"成功標記商品: {barcode}")
        return True
    else:
        st.error(f"未找到商品: {barcode}")
        return False

def display_progress(df):
    total_items = len(df)
    checked_items = len(df[df['檢貨狀態'] == '已檢貨'])
    progress = checked_items / total_items
    st.progress(progress)
    st.write(f"檢貨進度：{checked_items}/{total_items} ({progress:.2%})")

def check_inventory():
    st.subheader("檢貨")
    
    if 'inventory_df' not in st.session_state:
        st.warning("請先從 Google Drive 讀取庫存文件")
        if st.button("前往讀取數據"):
            st.session_state.function_selection = "從 Google Drive 讀取"
            st.rerun()
        return

    df = st.session_state['inventory_df'].copy()
    
    # 顯示當前庫存狀態
    display_columns = ['藥庫位置', '藥品名稱', '盤撥量', '藥庫庫存', '檢貨狀態']
    inventory_display = st.empty()
    progress_display = st.empty()

    def update_displays():
        with inventory_display.container():
            st.dataframe(df[display_columns].style.applymap(
                lambda x: 'background-color: #90EE90' if x == '已檢貨' else 'background-color: #FFB6C1',
                subset=['檢貨狀態']
            ))
        with progress_display.container():
            display_progress(df)

    update_displays()

    # 使用 streamlit-webrtc 進行條碼掃描
    webrtc_ctx = webrtc_streamer(
        key="barcode-scanner",
        video_processor_factory=BarcodeVideoProcessor,
        async_processing=True,
    )

    # 手動輸入表單
    with st.form(key='barcode_form', clear_on_submit=True):
        barcode = st.text_input("輸入商品條碼或掃描條碼", key="barcode_input")
        submit_button = st.form_submit_button("檢查商品")

    if submit_button and barcode:
        if update_inventory_status(df, barcode):
            st.session_state['inventory_df'] = df
            update_displays()

    # 處理掃描到的條碼
    if 'scanned_barcodes' in st.session_state and st.session_state['scanned_barcodes']:
        for scanned_barcode in st.session_state['scanned_barcodes']:
            if update_inventory_status(df, scanned_barcode):
                st.session_state['inventory_df'] = df
                update_displays()
        st.session_state['scanned_barcodes'] = []  # 清空已處理的條碼

    if st.button("完成檢貨"):
        st.success("檢貨完成！數據已更新。")
        # 這裡可以添加將更新後的數據保存回 Google Drive 的邏輯

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

# 保留其他原有的函數...

def main():
    st.title("藥品庫存管理系統")

    function = st.sidebar.radio("選擇功能", ("從 Google Drive 讀取", "檢貨", "收貨", "備份到 Google Drive"))

    if function == "從 Google Drive 讀取":
        read_from_drive()
    elif function == "檢貨":
        check_inventory()
    elif function == "收貨":
        receive_inventory()
    elif function == "備份到 Google Drive":
        backup_to_drive()

if __name__ == "__main__":
    main()
